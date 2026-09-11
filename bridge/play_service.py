import asyncio
import json
import math
import re
import time
from typing import Optional, Dict, List, Any, Tuple

from bridge.play_types import Card, PlayState, PlayPhase, POSITION_ORDER, PARTNERS
from bridge.play_engine import PlayEngine
from llm.prompts import PLAY_COMMON_RULES, PLAY_COMMON_SITUATION, PLAY_DECLARER_PROMPT, PLAY_DEFENDER_PROMPT
from bridge.mcts import DDSearch
from bridge.mcts.direct_dds import is_dds_available
from bridge.mcts.constraints import BidConstraint, validate_sample
from bridge.mcts.signals import format_partner_signals_for_prompt
from bridge.mcts.sampler import compute_played_stats, compute_remaining_counts, _reduce_constraint_for_played
from config import (
    DD_NUM_SAMPLES, DD_MIN_SAMPLES, DD_TIME_LIMIT,
    DD_ENDGAME_CARD_THRESHOLD, DD_ENDGAME_MAX_ENUMERATIONS,
    DD_ALPHAMU_SWITCH_CARDS,
    ALPHA_MU_ENABLE, ALPHA_MU_ENDGAME_CARDS, ALPHA_MU_NUM_WORLDS,
    ALPHA_MU_MAX_DEPTH, ALPHA_MU_TIME_LIMIT, ALPHA_MU_M,
    ALPHAMU_LLM_GAP_CAP,
    FINESSE_DEFER_ENABLE, FINESSE_EIGHT_NINE_ENABLE,
    FINESSE_RATIO, FINESSE_NEC_MAKE, FINESSE_NEC_MAKE_HIGH,
    FINESSE_NEC_RATIO, FINESSE_NEC_SLACK, FINESSE_SAFE_PCT,
)


class PlayService:

    def __init__(self, llm_client):
        self.llm_client = llm_client
        self.engine = PlayEngine()
        # 做庄计划：庄家和明手之间共享传递（结构化）
        self.declarer_plan = self._empty_plan()
        # 防守计划：每个防守者各自维护，key=位置
        self.defender_plans = {}
        # DD搜索器（纯蒙特卡洛 + 双明手评估）
        self.dd_search = DDSearch(
            num_samples=DD_NUM_SAMPLES,
            min_samples=DD_MIN_SAMPLES,
            time_limit=DD_TIME_LIMIT,
            endgame_card_threshold=DD_ENDGAME_CARD_THRESHOLD,
            max_enumerations=DD_ENDGAME_MAX_ENUMERATIONS,
        )
        # Phase 0a: BeliefTracker 已移除（均匀采样不需要粒子加权）
        # DD 和 αμ 直接通过 sampler.sample_n() 生成无偏样本/world
        self.belief_tracker = None

        # αμ 搜索器：残局多步前瞻，解决 strategy fusion 和 non-locality
        # 共享 dd_search 的 sampler（含叫牌约束）
        self.alpha_mu_search = None
        if ALPHA_MU_ENABLE:
            try:
                from bridge.mcts.alpha_mu import AlphaMuSearch
                self.alpha_mu_search = AlphaMuSearch(
                    sampler=self.dd_search.sampler,
                    num_worlds=ALPHA_MU_NUM_WORLDS,
                    M=ALPHA_MU_M,
                    time_limit=ALPHA_MU_TIME_LIMIT,
                )
            except Exception as e:
                print(f"[PlayService] αμ 搜索器初始化失败: {e}")
                self.alpha_mu_search = None

    @staticmethod
    def _empty_plan() -> dict:
        """空计划结构。"""
        return {
            "steps": [],
            "created_at_trick": 0,
            "last_validated_trick": 0,
            "raw_text": "",
        }

    def _format_plan_for_prompt(self, plan) -> str:
        """把结构化plan格式化为prompt可读文本。"""
        if not plan or not isinstance(plan, dict):
            return ""
        steps = plan.get("steps", [])
        raw = plan.get("raw_text", "")
        if not steps and not raw:
            return ""
        parts = []
        if raw:
            parts.append(raw)
        if steps:
            parts.append("步骤:")
            for i, s in enumerate(steps, 1):
                action = s.get("action", "")
                pre = s.get("precondition", "")
                done = "✓" if s.get("completed") else "○"
                line = f"  {i}. [{done}] {action}"
                if pre:
                    line += f" (前提: {pre})"
                extra = []
                if s.get("play_card"):
                    extra.append(f"出{s.get('play_card')}")
                if s.get("tactic"):
                    extra.append(s.get("tactic"))
                if s.get("target_card"):
                    extra.append(f"目标{s.get('target_card')}")
                if s.get("entry_card"):
                    extra.append(f"进手{s.get('entry_card')}")
                if extra:
                    line += f" [{'/'.join(extra)}]"
                parts.append(line)
        return "\n".join(parts)

    def _is_plan_empty(self, plan) -> bool:
        """判断plan是否为空。"""
        if not plan:
            return True
        if isinstance(plan, str):
            return not plan.strip()
        if isinstance(plan, dict):
            return not plan.get("steps") and not plan.get("raw_text", "").strip()
        return True

    def initialize(
        self,
        hands: Dict[str, dict],
        contract_str: str,
        declarer: str,
        player_roles: Dict[str, str] = None,
        doubled: bool = False,
        redoubled: bool = False,
        bidding_sequence: str = "未提供",
        bid_history: str = "",
        bid_meanings: str = "",
        constraints: Optional[dict] = None,
        vulnerability: str = "NV",
        bid_system: str = "",
    ) -> PlayState:
        from bridge.play_types import Contract

        contract = Contract.from_str(contract_str, declarer)
        contract.doubled = doubled
        contract.redoubled = redoubled

        # 重置做庄和防守计划
        self.declarer_plan = self._empty_plan()
        self.defender_plans = {}
        # 缓存叫牌约束（供MCTS采样器使用）
        self.bid_history = bid_history
        self.bid_meanings = bid_meanings  # 叫牌含义文本（复用LLM已分析信息）
        self.bid_system = bid_system or ""  # 实际叫牌体系（仅存档用，约束不再依赖体系）
        self.bid_constraints = None  # 延迟提取
        self._seed_constraints = constraints or None  # 前端弹窗已生成的家约束，直接seed
        # Phase 0a: BeliefTracker 已移除，粒子缓存不再需要清理

        return self.engine.initialize(hands, contract, player_roles, bidding_sequence, vulnerability)
    
    def get_state(self) -> Optional[PlayState]:
        return self.engine.get_state()
    
    def get_state_dict(self) -> Optional[dict]:
        return self.engine.get_state_dict()
    
    def set_hand(self, position: str, hand: Dict[str, str]) -> tuple:
        return self.engine.set_hand(position, hand)
    
    def play_card(self, position: str, card: Card, is_ai: bool = False, reason: str = None, risk: str = None) -> tuple:
        return self.engine.play_card(position, card, is_ai, reason, risk)
    
    def get_playable_cards(self, position: str = None) -> List[Card]:
        return self.engine.get_playable_cards(position)
    
    def is_human_turn(self) -> bool:
        return self.engine.is_human_turn()
    
    def update_player_roles(self, player_roles: Dict[str, str]) -> bool:
        return self.engine.update_player_roles(player_roles)
    
    def get_current_player(self) -> Optional[str]:
        return self.engine.get_current_player()
    
    def undo_last_card(self) -> tuple:
        """撤销最近一次出牌，同步清理做庄/防守计划"""
        # 记录撤销前的墩数，用于判断是否需要清理全局规划
        state_before = self.engine.get_state()
        tricks_before = len(state_before.tricks) if state_before else 0
        
        success, message = self.engine.undo_last_card()
        
        if success and state_before:
            state_after = self.engine.get_state()
            tricks_after = len(state_after.tricks) if state_after else 0
            
            # 撤销的牌对应的出牌者
            undone_position = state_after.current_player if state_after else None
            
            if undone_position:
                # 如果撤销的是防守方出牌，丢弃该防守者的计划
                declarer = state_after.contract.declarer if state_after else None
                dummy = state_after.dummy if state_after else None
                is_declarer_side = undone_position in (declarer, dummy)
                
                if not is_declarer_side:
                    # 防守方撤销：丢弃该位置的计划
                    self.defender_plans.pop(undone_position, None)
                else:
                    # 庄家方撤销：丢弃做庄进度
                    self.declarer_plan = self._empty_plan()

            # 如果墩数回退（从已完成墩恢复），清空所有计划
            if tricks_after < tricks_before:
                self.declarer_plan = self._empty_plan()
                self.defender_plans.clear()
        
        return success, message
    
    def is_complete(self) -> bool:
        return self.engine.is_complete()
    
    def get_result(self) -> Optional[dict]:
        return self.engine.get_result()
    
    async def get_ai_play(self, use_reasoning: bool = False,
                          use_dd: bool = False,
                          use_perfect: bool = False,
                          use_alphamu: bool = False,
                          use_dd_alphamu_llm: bool = False,
                          enable_llm_review: bool = False,
                          dd_samples: int = None,
                          dd_alphamu_switch_cards: int = None,
                          dd_scoring_mode: str = None) -> Dict[str, Any]:
        state = self.engine.get_state()
        if not state:
            return {"error": "游戏未初始化"}

        current_player = state.current_player
        playable_cards = self.engine.get_playable_cards()

        if not playable_cards:
            return {"error": "没有可出的牌"}

        if len(playable_cards) == 1:
            card = playable_cards[0]
            return {
                "card": card.to_dict(),
                "reasoning": "只有一张牌可出",
                "full_output": {"推荐出牌": str(card), "核心逻辑": "唯一选择"},
                "prompt": ""
            }

        # P0-6 修复：DDS 库不可用时，依赖双明手的引擎（DD/完美DD/αμ/默认 dd_alphamu_llm）
        # 统一降级为规则选牌并明确提示，
        # 避免 DLL 缺失时静默"选第一张牌"或抛异常导致整局卡死
        if use_perfect or use_dd or use_alphamu or use_dd_alphamu_llm:
            if not is_dds_available():
                return self._dds_unavailable_fallback(state)

        # === Perfect DD 引擎分支（全知双明手） ===
        if use_perfect:
            return await asyncio.to_thread(self._perfect_play, state)

        # === DD 引擎分支 ===
        if use_dd:
            return await asyncio.to_thread(self._dd_play, state, dd_samples, dd_scoring_mode)

        # === αμ 纯引擎分支（从开局到残局全覆盖） ===
        if use_alphamu:
            return await asyncio.to_thread(self._alpha_mu_play, state)

        # === DD-αμ-LLM 主力引擎（中盘DD+LLM审查 / 残局αμ+LLM审查） ===
        if use_dd_alphamu_llm:
            return await asyncio.to_thread(
                self._dd_alphamu_llm_play, state, use_reasoning, dd_samples,
                dd_alphamu_switch_cards, enable_llm_review, dd_scoring_mode)

        # === MCTS 引擎分支已移除（2026-09-07，能力弱） ===

        # === LLM 引擎分支 ===
        return await asyncio.to_thread(self._llm_play, state, use_reasoning)

    def _dds_unavailable_fallback(self, state: PlayState) -> Dict[str, Any]:
        """DDS 库缺失时的降级选牌：回退规则引擎并明确提示（P0-6 修复）。"""
        playable = self.engine.get_playable_cards()
        if not playable:
            return {"error": "没有可出的牌"}
        card = self._select_best_card(playable, state)
        return {
            "card": card.to_dict() if hasattr(card, "to_dict") else None,
            "reasoning": "[DDS不可用] 双明手 DDS 库未安装（endplay/dds.dll 缺失），已回退规则选牌。安装 endplay 后恢复完整能力。",
            "full_output": {
                "推荐出牌": str(card),
                "核心逻辑": "DDS 双明手库未安装，回退规则选牌",
                "DDS不可用": True,
            },
            "prompt": "",
        }

    def _llm_play(self, state: PlayState, use_reasoning: bool = False,
                  force_reasoning: bool = False,
                  extra_prompt: str = "") -> Dict[str, Any]:
        """LLM打牌（从 get_ai_play 提取，供分层引擎复用）"""
        current_player = state.current_player
        playable_cards = self.engine.get_playable_cards()
        constraints = self._get_bid_constraints()

        if not playable_cards:
            # _select_best_card 需要 playable，此情况不应出现在正常流程中
            return {"error": "没有可出的牌"}

        hands_info = self._format_hands_info(state)
        missing_info = self._format_missing_key_cards(state)
        completed_tricks = self._format_completed_tricks(state)
        current_trick = self._format_current_trick(state)
        played_cards_info = self._format_played_cards_info(state)

        # 判断当前是庄家方还是防守方出牌
        declarer_partner = PARTNERS.get(state.contract.declarer, "")
        is_declarer_side = current_player in (state.contract.declarer, declarer_partner)
        side = "庄家方" if is_declarer_side else "防守方"

        # 计算剩余所需墩数
        declarer_remaining = max(0, state.contract.tricks_needed - state.declarer_tricks)
        defender_remaining = max(0, (14 - state.contract.tricks_needed) - state.defender_tricks)

        # 判断将牌是否已清完
        trump_cleared = self._check_trump_cleared(state)

        # 当前墩数
        trick_number = len(state.tricks) + 1

        # 当前出牌位置（第几家出牌）
        current_trick_count = len(state.current_trick.cards)
        play_position = current_trick_count + 1
        remaining_players = 4 - play_position

        # 公共局面信息
        common_situation = PLAY_COMMON_SITUATION.format(
            contract=str(state.contract),
            bidding_sequence=state.bidding_sequence,
            declarer=state.contract.declarer,
            dummy=state.dummy or "无",
            current_player=current_player,
            play_position=play_position,
            current_trick_count=current_trick_count,
            remaining_players=remaining_players,
            trick_number=trick_number,
            side=side,
            hands_info=hands_info,
            played_cards_info=played_cards_info,
            completed_tricks=completed_tricks,
            current_trick=current_trick,
            declarer_tricks=state.declarer_tricks,
            defender_tricks=state.defender_tricks,
            tricks_needed=state.contract.tricks_needed,
            declarer_remaining=declarer_remaining,
            defender_remaining=defender_remaining,
            trump_cleared=trump_cleared,
        )

        # 获取上一轮计划
        if is_declarer_side:
            plan_text = self._format_plan_for_prompt(self.declarer_plan)
            previous_plan = f"## 上一轮做庄进度与调整\n{plan_text}" if plan_text else "（首轮出牌，尚无做庄计划）"
        else:
            prev = self.defender_plans.get(current_player, "")
            if isinstance(prev, dict):
                prev = self._format_plan_for_prompt(prev)
            previous_plan = f"## 上一轮防守计划\n{prev}" if prev else "（首次出牌，尚无防守计划）"

        # 根据角色选择不同提示词模板
        if is_declarer_side:
            prompt = PLAY_DECLARER_PROMPT.format(
                common_rules=PLAY_COMMON_RULES,
                play_position=play_position,
                current_trick_count=current_trick_count,
                common_situation=common_situation,
                previous_plan=previous_plan,
            )
        else:
            prompt = PLAY_DEFENDER_PROMPT.format(
                common_rules=PLAY_COMMON_RULES,
                play_position=play_position,
                current_trick_count=current_trick_count,
                common_situation=common_situation,
                previous_plan=previous_plan,
            )

        # 附加额外提示（如DD候选参考）
        if extra_prompt:
            prompt += extra_prompt

        thinking = use_reasoning or force_reasoning
        model_label = "reasoning" if thinking else "chat"
        print(f"[Play] LLM Prompt {len(prompt)} chars, model={self.llm_client.model} ({model_label})")
        try:
            result = self.llm_client.chat_play(prompt, thinking=thinking)

            # 提取推荐出牌：兼容dict嵌套对象（DeepSeek偶发格式偏差）
            recommended = result.get("推荐出牌") or result.get("recommended_card") or result.get("recommended_play")
            if isinstance(recommended, dict):
                recommended = (recommended.get("出牌") or recommended.get("card")
                    or recommended.get("推荐") or recommended.get("牌") or "")
            if not isinstance(recommended, str):
                recommended = ""
            card = self._parse_card_from_str(recommended, playable_cards)

            if not card:
                card = self._select_best_card(playable_cards, state)

            # === LLM 输出校验层 ===
            # 规则校验：推荐牌是否合法、是否犯明显错误
            # 违规时回退到 _select_best_card（DD 回退由调用方处理）
            card, validation_msg = self._validate_and_fallback(
                card, playable_cards, state)
            validation_warning = validation_msg

            reasoning = (
                result.get("核心逻辑") or
                result.get("候选对比") or
                result.get("局面评估") or
                result.get("推理过程") or
                result.get("理由") or
                result.get("reasoning") or
                ""
            )
            if not isinstance(reasoning, str):
                reasoning = json.dumps(reasoning, ensure_ascii=False)

            # 保存候选对比作为下一轮计划参考
            candidate_analysis = result.get("候选对比", "")
            if isinstance(candidate_analysis, str) and candidate_analysis:
                plan_obj = self._empty_plan()
                plan_obj["raw_text"] = candidate_analysis
                if is_declarer_side:
                    self.declarer_plan = plan_obj
                else:
                    self.defender_plans[current_player] = plan_obj

            # 防御：将 full_output 中所有非字符串值转为 JSON 字符串
            safe_output = {}
            for key, value in result.items():
                if isinstance(value, str):
                    safe_output[key] = value
                elif isinstance(value, (dict, list)):
                    safe_output[key] = json.dumps(value, ensure_ascii=False)
                else:
                    safe_output[key] = str(value) if value is not None else ""

            # 校验警告注入 reasoning
            if validation_warning:
                reasoning = f"[校验警告] {validation_warning}\n{reasoning}"
                safe_output["validation_warning"] = validation_warning

            # 注入叫牌约束信息
            safe_output["叫牌约束"] = self._format_constraints_for_display(constraints)
            safe_output["最新约束"] = self._format_latest_constraints_for_display(state, constraints)
            self._inject_played_stats(safe_output, state)

            return {
                "card": card.to_dict() if card else None,
                "reasoning": reasoning,
                "full_output": safe_output,
                "prompt": prompt
            }

        except Exception as e:
            card = self._select_best_card(playable_cards, state)
            return {
                "card": card.to_dict() if card else None,
                "reasoning": f"AI分析出错，自动选择: {str(e)}",
                "error": str(e),
                "prompt": ""
            }

    CONSTRAINT_TRANSLATE_PROMPT = """你是桥牌叫牌约束转换器。输入完整叫牌历史（每行以 [来源] 标注，每手每轮叫品的公开含义，含pass），输出每个叫品对应的"叫牌约束"。

叫牌约束表示该叫品对牌情的**公开承诺**（点力范围、花色长度、牌型、单缺、控制、关键张），只能来自含义文本中明确声明的承诺，禁止编造含义未提及的信息，禁止使用实际手牌（你看不到手牌）。

叫牌历史（格式：[来源] (位置)叫品：含义，来源=XR/JF/AI）：
{bid_history}

对叫牌历史中的**每一个叫品**（含pass）都输出一条，是否提取约束按"来源过滤规则"判断，输出JSON对象：
{{
  "calls": [
    {{"position": "南", "bid": "1C", "constraint": "HCP12-21|C3+"}},
    {{"position": "西", "bid": "pass", "constraint": "HCP≤7"}}
  ]
}}

约束格式（单行紧凑串，按|分段）：
- HCP段：HCP下界[-上界]，如 HCP12-21、HCP16+、HCP≤7
- 花色段：S/H/D/C + 张数（+至少/-至多/裸数字精确），如 S5+、H4
- 牌型段：均型 / 非均
- 单缺段：单缺X（X=花色字母），如 单缺H
- 控制段：控X（承诺该花色有控制=A/K或单/缺），源自扣叫承诺
- 关键张段：关键张N（A、K合计至少N），仅当4NT/5NT问叫答叫时承诺的数量

来源过滤规则（决定哪些行参与约束转译）：
- [XR]/[JF] 行：正常提取其公开承诺约束（含下面pass负面推断）。
- [AI] 行：仅当含义明确属于**约定叫**时提取（如4NT/5NT关键张问叫及其答叫、扣叫承诺某门单缺/控制、含义文字明确指出是该体系某项约定如斯泰曼/转移叫/黑木等）；一般自然叫/自由描述（如"自然叫，5张以上X，不逼叫"）不提取，constraint 输出空字符串。
- [AI] 行不参与 pass 负面推断。

转译规则：
1. 每个叫品：从其"含义"提取公开承诺。含义明确给出的点力区间/花色张数/牌型必须转写；含义未提及的不写；不确定一律不写。
2. HCP 段必须是该叫品对**本家个人大牌点（HCP）**的承诺。含义中"联手点力/联手至少X点/合计X点"表示己方两人总点力：
   - [XR]/[JF] 来源（非AI，约定含义可靠）：若含义明确给出联手下限 X 且含义中已注明同伴的 HCP 区间，可推导本家下限 = X − 同伴区间上限，写成个人 HCP（例：同伴 2NT=20-21、含义"联手≥37点"→ 本家 HCP16+）；同伴区间未知或无法推导时，HCP 段留空。
   - [AI] 来源：一律禁止推导，HCP 段留空。
   - 任何情况都不得把联手总点力直接写成任一家个人 HCP（如"联手≥37点"不得写成 HCP37+）。
3. pass 的负面推断（对方/同伴正常叫牌后仍pass，仅[XR]/[JF]行）：
   - 有开叫机会但未开叫 → HCP≤11
   - 对方1阶开叫后自己未争叫 → 无5张以上套（或HCP过低无法争叫）
   - 对方2阶开叫/争叫后自己未叫 → 无6张以上套（或HCP过低）
4. 扣叫（叫敌方已叫花色/配合将牌后的新花扣叫）→ 承诺该花色有控制，写 控X
5. 4NT/5NT 问关键张后的答叫（如5C/5D/5H/5S）→ 按答叫承诺写 关键张N（标准黑木：5C=1或4个，5D=0或3个，5H=2或5个，5S=2或5个且有将牌Q）
6. 同一位置多次叫牌：各自输出当次的承诺（不累计、不合并），由程序合并
7. pass 若不提供明确上限（如正常跟pass无信息），constraint 可为空字符串

仅输出JSON，不要Markdown代码块："""

    def generate_constraints_from_meanings(self, meanings_text: str) -> Dict[str, BidConstraint]:
        """约束转换主路径：LLM 从完整叫牌含义文本生成每家累计约束。

        每个叫品独立生成承诺约束，同一位置多次叫牌用 _merge_constraints 单调收紧合并。
        返回 {位置(南/西/北/东): BidConstraint}。
        """
        if not meanings_text or not meanings_text.strip():
            return {}
        prompt = self.CONSTRAINT_TRANSLATE_PROMPT.format(bid_history=meanings_text)
        result = self.llm_client.chat_json(system_prompt=prompt, temperature=0, max_tokens=4096)
        if result.get("error") or not result.get("calls"):
            return {}
        pos_map = {"南": "南", "西": "西", "北": "北", "东": "东",
                   "south": "南", "west": "西", "north": "北", "east": "东"}
        merged: Dict[str, BidConstraint] = {}
        for item in result["calls"]:
            if not isinstance(item, dict):
                continue
            pos_cn = pos_map.get(str(item.get("position", "")).strip().lower())
            if pos_cn is None:
                continue
            cstr = (item.get("constraint") or "").strip()
            if not cstr:
                continue
            c = self._build_constraint_from_structured(cstr, pos_cn)
            if pos_cn in merged:
                merged[pos_cn] = self._merge_constraints(merged[pos_cn], c)
            else:
                merged[pos_cn] = c
        return merged

    def _merge_constraints(self, c1: BidConstraint, c2: BidConstraint) -> BidConstraint:
        """合并同一位置的两次叫牌约束：取更严格限制（单调收紧）。

        - HCP：下界取大、上界取小；单边保留
        - 花色张数：suit_min 取大、suit_max 取小、exact_suit 取更大（更精确的长套）
        - balanced：矛盾时保留更明确的（后续叫牌更明确，取后一次非None）
        - min_controls / min_keycards：取大
        - specific_cards / suit_controls：并集（都要求）
        """
        merged = BidConstraint(position=c1.position, inference_source="merged")
        lo = c1.min_hcp if c1.min_hcp is not None else c2.min_hcp
        if c1.min_hcp is not None and c2.min_hcp is not None:
            lo = max(c1.min_hcp, c2.min_hcp)
        hi = c1.max_hcp if c1.max_hcp is not None else c2.max_hcp
        if c1.max_hcp is not None and c2.max_hcp is not None:
            hi = min(c1.max_hcp, c2.max_hcp)
        merged.min_hcp, merged.max_hcp = lo, hi
        if c1.balanced is not None and c2.balanced is not None:
            merged.balanced = c1.balanced if c1.balanced == c2.balanced else None
        else:
            merged.balanced = c1.balanced if c1.balanced is not None else c2.balanced
        for suit in set(list(c1.suit_min.keys()) + list(c2.suit_min.keys())):
            merged.suit_min[suit] = max(c1.suit_min.get(suit, 0), c2.suit_min.get(suit, 0))
        for suit in set(list(c1.suit_max.keys()) + list(c2.suit_max.keys())):
            merged.suit_max[suit] = min(c1.suit_max.get(suit, 13), c2.suit_max.get(suit, 13))
        for suit in set(list(c1.exact_suit.keys()) + list(c2.exact_suit.keys())):
            e1 = c1.exact_suit.get(suit)
            e2 = c2.exact_suit.get(suit)
            if e1 is not None and e2 is not None:
                merged.exact_suit[suit] = max(e1, e2)
            else:
                merged.exact_suit[suit] = e1 if e1 is not None else e2
        if c1.min_controls is not None or c2.min_controls is not None:
            merged.min_controls = max(c1.min_controls or 0, c2.min_controls or 0)
        if c1.min_keycards is not None or c2.min_keycards is not None:
            merged.min_keycards = max(c1.min_keycards or 0, c2.min_keycards or 0)
        merged.specific_cards = c1.specific_cards.union(c2.specific_cards)
        merged.suit_controls = c1.suit_controls.union(c2.suit_controls)
        return merged

    def _format_constraints_for_display(self, constraints: Dict[str, BidConstraint]) -> str:
        """将约束格式化为前端展示用的可读文本。"""
        if not constraints:
            return "无约束（随机采样）"
        lines = []
        order = ["南", "西", "北", "东"]
        for pos in order:
            c = constraints.get(pos)
            if c is None:
                continue
            parts = [f"{pos}:"]
            # HCP 范围
            if c.min_hcp is not None and c.max_hcp is not None:
                parts.append(f"HCP {c.min_hcp}-{c.max_hcp}")
            elif c.min_hcp is not None:
                parts.append(f"HCP ≥{c.min_hcp}")
            elif c.max_hcp is not None:
                parts.append(f"HCP ≤{c.max_hcp}")
            # 均型标记
            if c.balanced is True:
                parts.append("均型")
            elif c.balanced is False:
                parts.append("非均型")
            # 花色张数约束（suit_min/suit_max/exact_suit 合并显示）
            suit_info = []
            all_suits = set(list(c.suit_min.keys()) + list(c.suit_max.keys()) + list(c.exact_suit.keys()))
            for s in ["♠", "♥", "♦", "♣"]:
                if s in c.exact_suit:
                    suit_info.append(f"{s}={c.exact_suit[s]}")
                elif s in c.suit_min and s in c.suit_max:
                    suit_info.append(f"{s}{c.suit_min[s]}-{c.suit_max[s]}")
                elif s in c.suit_min:
                    suit_info.append(f"{s}≥{c.suit_min[s]}")
                elif s in c.suit_max:
                    suit_info.append(f"{s}≤{c.suit_max[s]}")
            if suit_info:
                parts.append(" ".join(suit_info))
            # 控制数
            if c.min_controls is not None:
                parts.append(f"≥{c.min_controls}控")
            # 特定牌
            if c.specific_cards:
                sc = ", ".join(f"{s}{r}" for s, r in c.specific_cards)
                parts.append(f"必持:{sc}")
            # 来源
            src = c.inference_source or ""
            if "convention" in src:
                parts.append("[约定]")
            elif "negative" in src:
                parts.append("[否定推断]")
            elif "conservation" in src:
                parts.append("[HCP守恒]")
            lines.append(" ".join(parts))
        return "\n".join(lines) if lines else "无约束（随机采样）"

    def _format_latest_constraints_for_display(self, state: PlayState, constraints: Dict[str, BidConstraint]) -> str:
        """按当前已出牌把初始约束折算为剩余部分约束，展示约束随出牌的变化。

        与采样器共用同一扣减逻辑（初始约束 = 已出部分 + 剩余部分），
        某家约束已无条件满足（不影响采样）时省略展示。
        """
        if not constraints:
            return "无约束（随机采样）"
        played_stats = compute_played_stats(state)
        remaining_counts = compute_remaining_counts(state)
        reduced: Dict[str, BidConstraint] = {}
        for pos, c in constraints.items():
            played = played_stats.get(pos, {})
            if not any((played.get("suit") or {}).values()):
                reduced[pos] = c
                continue
            rc = _reduce_constraint_for_played(c, played, remaining_counts.get(pos, 0))
            if rc is not None:
                rc.suit_min = {s: n for s, n in rc.suit_min.items() if n > 0}
                reduced[pos] = rc
        if not reduced:
            return "约束已随出牌全部满足"
        return self._format_constraints_for_display(reduced)

    def _inject_played_stats(self, output: dict, state: PlayState) -> None:
        """注入各家已出统计进 full_output（HCP + 四门花色张数，含当前墩），
        供前端"初始/最新约束 + 已出牌"对照表使用。"""
        try:
            stats = compute_played_stats(state)
            output["各家已出统计"] = {
                p: {"hcp": st["hcp"], "♠": st["suit"]["♠"], "♥": st["suit"]["♥"], "♦": st["suit"]["♦"], "♣": st["suit"]["♣"]}
                for p, st in stats.items()
            }
        except Exception as e:
            print(f"[Play] 注入各家已出统计失败: {e}")

    def _format_missing_key_cards(self, state: PlayState) -> str:
        """列出两家手牌中都不出现的关键大牌，提醒LLM这些牌在对方手中。"""
        declarer = state.contract.declarer
        dummy = state.dummy
        if not dummy:
            return ""
        visible_cards = set()
        for pos in [declarer, dummy]:
            for c in state.hands.get(pos, []):
                visible_cards.add(str(c))
        all_key = ["♠A", "♠K", "♠Q", "♠J", "♠T",
                    "♥A", "♥K", "♥Q", "♥J", "♥T",
                    "♦A", "♦K", "♦Q", "♦J", "♦T",
                    "♣A", "♣K", "♣Q", "♣J", "♣T"]
        missing = [c for c in all_key if c not in visible_cards]
        if missing:
            return f"未出现的关键大牌（在对方手中）: {' '.join(missing)}"
        return ""

    def _format_trump_analysis(self, state: PlayState) -> str:
        """程序直接计算将牌统计，避免LLM数错。"""
        trump = state.contract.suit
        if not trump or trump == "NT":
            return "无将定约，无将牌输墩。"

        declarer = state.contract.declarer
        dummy = state.dummy
        if not dummy:
            return ""

        decl_trumps = [c for c in state.hands.get(declarer, []) if c.suit == trump]
        dummy_trumps = [c for c in state.hands.get(dummy, []) if c.suit == trump]

        played_trumps = []
        for trick in state.tricks:
            for pos, card in trick.cards:
                if card.suit == trump:
                    played_trumps.append(card)
        for pos, card in state.current_trick.cards:
            if card.suit == trump:
                played_trumps.append(card)

        decl_count = len(decl_trumps)
        dummy_count = len(dummy_trumps)
        played_count = len(played_trumps)
        our_count = decl_count + dummy_count
        opp_count = 13 - our_count - played_count

        all_ranks = ["A", "K", "Q", "J", "T", "9", "8", "7", "6", "5", "4", "3", "2"]
        known = set(str(c) for c in decl_trumps + dummy_trumps + played_trumps)
        opp_cards = [f"{trump}{r}" for r in all_ranks if f"{trump}{r}" not in known]
        opp_honors = [c for c in opp_cards if c[-1] in ("A", "K", "Q", "J")]

        lines = [
            f"将牌: {trump}",
            f"庄家({declarer})将牌({decl_count}张): {' '.join(str(c) for c in decl_trumps) if decl_trumps else '无'}",
            f"明手({dummy})将牌({dummy_count}张): {' '.join(str(c) for c in dummy_trumps) if dummy_trumps else '无'}",
            f"庄家方现有将牌合计: {our_count}张",
            f"已出过的将牌({played_count}张): {' '.join(str(c) for c in played_trumps) if played_trumps else '无'}",
            f"对方现有将牌: {opp_count}张 (= 13 - {our_count} - {played_count})",
            f"对方将牌具体牌张: {' '.join(opp_cards) if opp_cards else '无'}",
        ]
        if opp_honors:
            lines.append(f"对方将牌大牌(A/K/Q/J): {' '.join(opp_honors)} → {len(opp_honors)}个潜在将牌输墩")
        else:
            lines.append("对方将牌无大牌(A/K/Q/J) → 无将牌输墩")

        return "\n".join(lines)

    def _parse_constraints_from_meanings(self, meanings_text: str) -> Dict[str, BidConstraint]:
        """从叫牌含义文本中解析约束信息（复用叫牌阶段LLM已输出信息，无需二次LLM调用）。

        含义文本格式示例：
            (南)1NT: 15-17HCP均型，无5张高花
            (北)2♥: 雅各比转移叫，5+张♠，0+HCP

        Returns:
            (constraints, structured_homes): 各家约束表，以及走通道A（含结构化约束段）的家集合
        """
        import re
        constraints: Dict[str, BidConstraint] = {}
        structured_homes: set = set()  # 走通道A（结构化约束）的家，作为权威来源

        # 逐行解析
        for line in meanings_text.split('\n'):
            line = line.strip()
            if not line:
                continue

            # 提取位置: (南)1NT: ...
            m = re.match(r'\(([南西北东])\)([^:：]+)[：:]\s*(.+)', line)
            if not m:
                continue
            pos = m.group(1)
            bid = m.group(2).strip()
            meaning = m.group(3).strip()

            # 跳过 pass
            if bid.lower() in ('pass', '不叫'):
                continue

            # 通道A：优先解析结构化"叫品约束"段（[约束:HCP12-21|S5+|...]），
            # 该字段是叫牌阶段LLM输出的该位置累计自身承诺，且按单调收紧不变式生成。
            mseg = re.search(r'\[约束\s*[：:]\s*([^\]]+)\]', meaning)
            if mseg:
                c = self._build_constraint_from_structured(mseg.group(1).strip(), pos)
                structured_homes.add(pos)
            else:
                c = self._build_constraint_from_meaning_free(meaning, pos)

            # 同位置多叫品：与已有约束合并而非覆盖
            if pos in constraints:
                constraints[pos] = self._merge_constraints(constraints[pos], c)
            else:
                constraints[pos] = c

        # 后处理：解析否定表达式（"无N张X" → suit_max = N-1）
        for line in meanings_text.split('\n'):
            m = re.match(r'\(([南西北东])\)([^:：]+)[：:]\s*(.+)', line.strip())
            if not m:
                continue
            pos = m.group(1)
            meaning = m.group(3).strip()
            # "无5张高花" → ♠≤4, ♥≤4
            for nm in re.finditer(r'无\s*(\d+)\s*张\s*高花', meaning):
                cnt = int(nm.group(1))
                if pos in constraints:
                    for s in ('♠', '♥'):
                        constraints[pos].suit_max[s] = min(constraints[pos].suit_max.get(s, 13), cnt - 1)
            # "无单缺" → 均型
            if re.search(r'无单缺|无单张|无缺门', meaning):
                if pos in constraints:
                    constraints[pos].balanced = True

        return constraints, structured_homes

    def _build_constraint_from_structured(self, segs: str, pos: str) -> BidConstraint:
        """解析通道A的结构化"叫品约束"段，返回该段对应的累计约束。

        段格式（单行紧凑串，按|分段）：
        - HCP段：HCP下界[-上界]，如 HCP12-21 / HCP16+ / HCP≤7
        - 花色段：S/H/D/C + 张数[+/-]，+至少，-至多，裸数字精确，如 S5+ / D4
        - 牌型段：均型 / 非均 / 单缺（可选）
        - 单缺段：单缺X（X为该花色字母或花色符），至多1张
        - 控制段：控X / 控X/Y，X为花色字母，承诺该花色有控制（A/K或单/缺）
        - 关键张段：关键张N，承诺关键张（A、K）合计至少N张
        """
        c = BidConstraint(position=pos, inference_source="structured")
        suit_map = {'S': '♠', 'H': '♥', 'D': '♦', 'C': '♣'}
        for seg in segs.split('|'):
            seg = seg.strip()
            if not seg:
                continue
            if seg.startswith('HCP'):
                body = seg[3:].strip().replace('≥', '>=').replace('≤', '<=').replace('，', '').replace(' ', '')
                if not body:
                    continue
                if body.startswith('>='):
                    c.min_hcp = int(body[2:])
                elif body.startswith('<='):
                    c.max_hcp = int(body[2:])
                elif body.startswith('<'):
                    c.max_hcp = int(body[1:]) - 1
                elif body.startswith('>'):
                    c.min_hcp = int(body[1:]) + 1
                elif '-' in body:
                    lo, _, hi = body.partition('-')
                    c.min_hcp = int(lo) if lo else None
                    c.max_hcp = int(hi) if hi else None
                elif body.endswith('+'):
                    c.min_hcp = int(body[:-1])
                elif body.isdigit():
                    c.min_hcp = c.max_hcp = int(body)
            elif seg in ('均型', '非均', '单缺'):
                c.balanced = (seg == '均型')
            elif seg.startswith('单缺'):
                # 单缺X：该花色≤1张
                rest = seg[2:].strip()
                suit = suit_map.get(rest.upper(), rest)
                if suit in ('♠', '♥', '♦', '♣'):
                    c.suit_max[suit] = min(c.suit_max.get(suit, 13), 1)
            elif seg.startswith('控'):
                # 控X / 控X/Y：承诺花色有控制（A/K或单/缺）
                rest = seg[1:].strip().upper()
                for tok in rest.replace('、', '/').replace('，', '/').replace(',', '/').split('/'):
                    tok = tok.strip()
                    suit = suit_map.get(tok)
                    if suit:
                        c.suit_controls.add(suit)
            elif seg.startswith('关键张'):
                # 关键张N：承诺关键张（A、K）合计至少N张
                m_kc = re.search(r'关键张\s*[：:]?\s*([0-9]+)', seg)
                if m_kc:
                    c.min_keycards = int(m_kc.group(1))
            else:
                sm = re.match(r'([SHDC])(\d+)\s*([+-]?)', seg)
                if sm:
                    suit = suit_map.get(sm.group(1))
                    cnt = int(sm.group(2))
                    op = sm.group(3)
                    if op == '+':
                        c.suit_min[suit] = max(c.suit_min.get(suit, 0), cnt)
                    elif op == '-':
                        c.suit_max[suit] = min(c.suit_max.get(suit, 13), cnt)
                    else:
                        c.exact_suit[suit] = cnt
        return c

    def _build_constraint_from_meaning_free(self, meaning: str, pos: str) -> BidConstraint:
        """通道B（含义自由文本）解析：从叫牌含义文本中用正则解析约束。"""
        c = BidConstraint(position=pos, inference_source="meaning_parsed")

        # 解析 HCP 范围: "15-17HCP"、"12+HCP"、"0-16HCP"、"≤7HCP"
        hcp_patterns = [
            (r'(\d+)\s*-\s*(\d+)\s*HCP', lambda m: (int(m.group(1)), int(m.group(2)))),
            (r'HCP\s*(\d+)\s*-\s*(\d+)', lambda m: (int(m.group(1)), int(m.group(2)))),
            (r'(\d+)\+\s*HCP', lambda m: (int(m.group(1)), None)),
            (r'HCP\s*≥\s*(\d+)', lambda m: (int(m.group(1)), None)),
            (r'≤\s*(\d+)\s*HCP', lambda m: (None, int(m.group(1)))),
            (r'(\d+)\s*HCP', lambda m: (int(m.group(1)), int(m.group(1)))),
        ]
        for pat, fn in hcp_patterns:
            hm = re.search(pat, meaning)
            if hm:
                mn, mx = fn(hm)
                c.min_hcp = mn
                c.max_hcp = mx
                break

        # 解析均型/非均型
        if re.search(r'均[型衡]', meaning):
            c.balanced = True
        elif re.search(r'非均[型衡]|不均[型衡]', meaning):
            c.balanced = False

        # 解析花色张数: "5+张♠"、"♠≥5"、"♥≤4"、"♣3-5张"
        # 张数≥: "5+张♠"、"♠≥5"、"5张+♠"
        for sm in re.finditer(r'(\d+)\+?\s*张\s*([♠♥♦♣])', meaning):
            cnt = int(sm.group(1))
            suit = sm.group(2)
            c.suit_min[suit] = max(c.suit_min.get(suit, 0), cnt)
        for sm in re.finditer(r'([♠♥♦♣])\s*≥\s*(\d+)', meaning):
            suit = sm.group(1)
            cnt = int(sm.group(2))
            c.suit_min[suit] = max(c.suit_min.get(suit, 0), cnt)
        # ≤张数: "♥≤4"
        for sm in re.finditer(r'([♠♥♦♣])\s*≤\s*(\d+)', meaning):
            suit = sm.group(1)
            cnt = int(sm.group(2))
            c.suit_max[suit] = min(c.suit_max.get(suit, 13), cnt)
        # 精确张数: "♠=6"
        for sm in re.finditer(r'([♠♥♦♣])\s*=\s*(\d+)', meaning):
            suit = sm.group(1)
            cnt = int(sm.group(2))
            c.exact_suit[suit] = cnt

        return c

    def _apply_constraints(self, constraints: Dict[str, BidConstraint], sampler=None) -> None:
        """将约束应用到采样器"""
        target_sampler = sampler or self.dd_search.sampler
        target_sampler.set_constraints(constraints)

    def _get_bid_constraints(self) -> Dict[str, BidConstraint]:
        """获取各家叫牌约束，结果缓存。

        优先使用前端弹窗生成并传入的家约束 payload；否则将完整叫牌含义文本
        （含pass，公开信息，不含手牌）交给 LLM 转换为各家累计约束。
        含义文本缺失 → 无约束（前端在进入打牌前已保证历史完整）。
        """
        if self.bid_constraints is not None:
            return self.bid_constraints

        if self._seed_constraints:
            self.bid_constraints = self._rebuild_bid_constraints(self._seed_constraints)
            return self.bid_constraints

        meanings_text = getattr(self, 'bid_meanings', '') or ''
        if not meanings_text.strip():
            self.bid_constraints = {}
            return self.bid_constraints

        try:
            constraints = self.generate_constraints_from_meanings(meanings_text)
            print(f"[DD] 约束转换LLM: { {p: f'HCP{c.min_hcp}-{c.max_hcp},keycards={c.min_keycards},controls={sorted(c.suit_controls)}' for p, c in constraints.items()} }")
            self.bid_constraints = constraints
        except Exception as e:
            print(f"[DD] 约束转换LLM失败: {e}")
            self.bid_constraints = {}
        return self.bid_constraints

    @staticmethod
    def _rebuild_bid_constraints(payload: dict) -> Dict[str, BidConstraint]:
        """将接口返回的家约束 payload 重建为 BidConstraint 字典。"""
        result = {}
        for pos_cn, data in (payload or {}).items():
            c = BidConstraint(
                position=pos_cn,
                min_hcp=data.get("min_hcp"),
                max_hcp=data.get("max_hcp"),
                balanced=data.get("balanced"),
                min_controls=data.get("min_controls"),
                min_keycards=data.get("min_keycards"),
                inference_source="structured",
            )
            c.suit_min = dict(data.get("suit_min") or {})
            c.suit_max = dict(data.get("suit_max") or {})
            c.exact_suit = dict(data.get("exact_suit") or {})
            c.suit_controls = set(data.get("suit_controls") or [])
            c.specific_cards = set(tuple(x) for x in (data.get("specific_cards") or []))
            result[pos_cn] = c
        return result

    def _alpha_mu_play(self, state: PlayState) -> Dict[str, Any]:
        """αμ 引擎（论文实现，纯αμ无回退）。

        M 值由 ALPHA_MU_M 配置（默认 2），全程不降级。
        注意：牌数多时 M=2 会非常慢（13 张牌约 30s+），研究用途可接受。
        """
        from bridge.mcts.alpha_mu import AlphaMuSearch

        perspective = state.current_player
        cards = len(state.hands.get(perspective, []))

        # 残局枚举：与 DD 保持一致，固定最后 4 墩时尝试精确枚举所有未知分布。
        # 枚举只是替代采样的世界生成方式，决策算法不变——仍走 αμ 的布尔成功率/Pareto 逻辑。
        _t_alpha_start = time.time()
        enum_worlds = None
        remaining_tricks = 13 - len(state.tricks)
        if remaining_tricks <= 4:
            try:
                enum_worlds = self.dd_search._enumerate_endgame_worlds(state, perspective)
                if enum_worlds:
                    print(f"[αμ] 残局完备世界集: {len(enum_worlds)} 个（枚举替代采样，αμ 决策）")
            except Exception as e:
                print(f"[αμ] 残局枚举异常（回退 αμ 采样搜索）: {e}")
                enum_worlds = None

        # P2-17 修复：世界数优先读取设置面板配置的值（滑块仅在纯 αμ 引擎下修改，
        # 但值在 session 内持久，对 DD-αμ-LLM 残局阶段同样全局生效，与 DD 样本数滑块行为一致）
        base_worlds = (self.alpha_mu_search.num_worlds
                       if self.alpha_mu_search and getattr(self.alpha_mu_search, 'num_worlds', None)
                       else ALPHA_MU_NUM_WORLDS)
        # 世界数随牌数减少而增加（残局越小，采样越精确）
        # 上限随 base_worlds 成比例缩放：默认 20 时与原绝对上限（100/60/30/20）完全一致，
        # 滑块调高时上限同步放大使全区间有效；代价是高世界数时 αμ 单步决策更慢（用户主动选择）
        _world_cap_m = base_worlds / ALPHA_MU_NUM_WORLDS if ALPHA_MU_NUM_WORLDS else 1.0
        if cards <= 4:
            n_worlds = min(int(100 * _world_cap_m), base_worlds * 5)
        elif cards <= 6:
            n_worlds = min(int(60 * _world_cap_m), base_worlds * 3)
        elif cards <= 8:
            n_worlds = min(int(30 * _world_cap_m), base_worlds * 2)
        else:
            n_worlds = min(int(20 * _world_cap_m), base_worlds)
        # 层数 M 优先读取设置面板配置的值（与 num_worlds 同模式：面板修改全局生效，
        # 含 DD-αμ-LLM 残局阶段；未初始化时用 config 默认）
        M_value = (self.alpha_mu_search.M
                   if self.alpha_mu_search and getattr(self.alpha_mu_search, 'M', None)
                   else ALPHA_MU_M)

        if cards <= 4:
            time_lim, dds_budget = 8.0, 5000
        elif cards <= 6:
            time_lim, dds_budget = 18.0, 8000
        elif cards <= 8:
            time_lim, dds_budget = 32.0, 12000
        elif cards <= 10:
            time_lim, dds_budget = 50.0, 15000
        else:
            time_lim, dds_budget = 60.0, 20000

        # P1-2 修复：αμ 搜索预算扣除残局枚举已用时间（共享总 deadline，下限 3s）
        time_lim = max(3.0, time_lim - (time.time() - _t_alpha_start))

        # 创建临时搜索器（复用 dd_search 的 sampler + 约束）
        constraints = self._get_bid_constraints()
        if constraints:
            self._apply_constraints(constraints)

        try:
            search = AlphaMuSearch(
                sampler=self.dd_search.sampler,
                num_worlds=n_worlds,
                M=M_value,
                time_limit=time_lim,
                dds_budget=dds_budget,
            )
            result = search.search(state, worlds=enum_worlds)
        except Exception as e:
            # P0-3 修复：αμ 搜索异常兜底——回退规则选牌，避免整局卡死
            # （AlphaMuSearch.__init__ 的 _load_dll、worlds 生成、搜索均可抛异常）
            print(f"[αμ] 搜索异常（回退规则选牌）: {e}")
            return self._alpha_mu_rule_fallback(state, f"αμ搜索异常: {e}")

        card = result.get("card")
        if card is None:
            # αμ 无结果时选第一张合法牌（不静默回退其他引擎）
            playable = self.engine.get_playable_cards()
            card = playable[0] if playable else None
        full_output = result.get("full_output", {})
        if enum_worlds:
            full_output["引擎阶段"] = "endgame_enum_αμ"
        full_output["叫牌约束"] = self._format_constraints_for_display(constraints)
        full_output["最新约束"] = self._format_latest_constraints_for_display(state, constraints)
        self._inject_played_stats(full_output, state)
        # 飞牌特殊处理（独立于引擎的统一管线，传入 αμ 比值）
        result = self._apply_finesse_tactics(state, result, FINESSE_RATIO)
        card = result.get("card")
        return {
            "card": card.to_dict() if hasattr(card, "to_dict") else None,
            "reasoning": result.get("reasoning", ""),
            "full_output": full_output,
            "prompt": "[αμ] no prompt",
        }

    def _alpha_mu_rule_fallback(self, state: PlayState, reason: str) -> Dict[str, Any]:
        """αμ 引擎异常兜底：回退规则选牌（与其他引擎一致的 _select_best_card，P0-3 修复）。"""
        playable = self.engine.get_playable_cards()
        if not playable:
            return {"error": "没有可出的牌"}
        card = self._select_best_card(playable, state)
        return {
            "card": card.to_dict() if hasattr(card, "to_dict") else None,
            "reasoning": f"[αμ 回退] {reason}",
            "full_output": {
                "推荐出牌": str(card),
                "核心逻辑": f"αμ异常，回退规则选牌: {reason}",
                "αμ回退": reason,
            },
            "prompt": "[αμ] no prompt",
        }

    def _alphamu_llm_play(self, state: PlayState, use_reasoning: bool = False) -> Dict[str, Any]:
        """αμ搜索 + 分组LLM选组打牌。

        αμ处理常规局面；当多个DDS等价组成功率接近且αμ分不清时，
        LLM按组分析战术并选组。LLM打牌计划跨墩传递。

        Step 1: αμ搜索
        Step 2: 按 best_vector 分组（DDS等价=同组）
          - 不满足触发条件 → 保留αμ
          - 满足触发条件 → LLM分析每组战术，选择一组
        Step 3: 应用LLM决策
          - 组内DDS等价：当前玩家自己出组中最大，明手出组中最小
          - 保存plan跨墩传递"""
        # Step 1: αμ搜索
        print(f"[αμ+LLM] use_reasoning={use_reasoning}, model={self.llm_client.model}")
        alpha_result = self._alpha_mu_play(state)
        full_output = alpha_result.get("full_output", {})
        mcts_stats = full_output.get("mcts_stats", {})
        candidates = mcts_stats.get("candidates", [])
        if not candidates:
            full_output["llm_review_status"] = "跳过：无候选牌"
            return alpha_result

        # Step 2: 按 best_vector 分组
        trump_suit = state.contract.suit if state.contract.suit != "NT" else ""
        groups = self._group_candidates_by_vector(candidates, trump_suit=trump_suit)

        # 防守方走独立防守审查（赢墩硬约束下传信号）
        declarer = state.contract.declarer
        dummy = state.dummy
        if state.current_player not in (declarer, dummy):
            return self._run_defender_review(state, alpha_result, candidates, groups,
                                             "αμ", use_reasoning)

        desperation_mode = False
        if not self._should_trigger_llm(groups, candidates, gap_threshold=None):
            all_zero = candidates and all(c.get("success_rate", 0) == 0 for c in candidates)
            if all_zero and len(candidates) >= 2:
                groups = self._build_desperation_groups(candidates, trump_suit=trump_suit, state=state)
                if len(groups) < 2:
                    full_output["llm_review_status"] = "跳过：无成约机会且分组不足"
                    return alpha_result
                desperation_mode = True
                print(f"[αμ+LLM] 绝望模式：αμ认为无成约机会，LLM审查{len(groups)}组、力争多拿墩少宕")
            else:
                full_output["llm_review_status"] = "跳过：成功率差距一边倒，引擎已明确偏好"
                return alpha_result

        # 庄家方：检测plan是否失效，失效则清空（强制LLM重新制定）
        if self._check_plan_invalidation(state):
            print(f"[αμ+LLM] 检测到plan失效，清空旧计划")
            self.declarer_plan = self._empty_plan()

        # Step 3: LLM分组审查
        alpha_card_str = full_output.get("推荐出牌", "")
        full_output["llm_review_status"] = "已激活"
        review = self._llm_group_review(state, candidates, groups,
                                         alpha_card=alpha_card_str,
                                         previous_plan=self._format_plan_for_prompt(self.declarer_plan),
                                         desperation=desperation_mode,
                                         use_reasoning=use_reasoning)
        trick_number = len(state.tricks) + 1
        if review.get("plan"):
            self.declarer_plan = self._build_plan_from_review(review, trick_number)
            plan_preview = self._format_plan_for_prompt(self.declarer_plan)[:60]
            print(f"[αμ+LLM] 打牌计划已{'确认' if review.get('plan_valid') else '制定'}: {plan_preview}...")
        elif review.get("plan_valid") is False and not self._is_plan_empty(self.declarer_plan):
            self.declarer_plan = self._empty_plan()
            print(f"[αμ+LLM] LLM认为现有计划无效，清空")

        # 处理LLM选组
        chosen_group_idx = review.get("group")
        chosen_group = None
        # LLM输出1-based，转0-based
        if isinstance(chosen_group_idx, (int, float)) and not isinstance(chosen_group_idx, bool):
            idx = int(chosen_group_idx) - 1
            if 0 <= idx < len(groups):
                chosen_group = groups[idx]

        if chosen_group:
            # 组内选牌：优先 LLM 指定 card，否则机械 min/max
            target_card_str, target = self._resolve_group_card(
                state, chosen_group, review.get("card", ""), dummy)
            if target:
                self._mark_step_completed(target_card_str, trick_number)
                alpha_result["card"] = target.to_dict()
                group_desc = ", ".join(c.get("card", "") for c in chosen_group["cards"])
                group_reason = review.get("reason", f"选择组{chosen_group_idx}（{group_desc}）")
                review_reasoning = f"[αμ+LLM] 选组{chosen_group_idx}出{target_card_str}（{group_reason}）"
                plan_desc = review.get("plan", "")
                if plan_desc:
                    review_reasoning += f"（计划: {plan_desc[:60]}...）"
                alpha_result["reasoning"] = f"{review_reasoning}\n{alpha_result.get('reasoning', '')}"
                alpha_result["full_output"]["推荐出牌"] = target_card_str
                alpha_result["full_output"]["核心逻辑"] = review_reasoning
                review["card"] = target_card_str
                alpha_result["full_output"]["llm_review"] = review
                return alpha_result

        # 回退：LLM选组失败，保留αμ
        print(f"[αμ+LLM] LLM选组失败(idx={chosen_group_idx})，保留αμ选择")
        if review.get("plan"):
            self.declarer_plan = self._build_plan_from_review(review, trick_number)
        alpha_result["full_output"]["llm_review"] = review
        return alpha_result

    def _dd_alphamu_llm_play(self, state: PlayState, use_reasoning: bool = False,
                              dd_samples: int = None,
                              switch_cards: int = None,
                              enable_llm_review: bool = False,
                              dd_scoring_mode: str = None) -> Dict[str, Any]:
        """DD-αμ-LLM 主力引擎：中盘DD+LLM审查，残局αμ+LLM审查。

        分界点参数化：每手剩余牌数 ≤ switch_cards（默认 DD_ALPHAMU_SWITCH_CARDS）
        时切到 αμ 搜索。enable_llm_review=False（默认）时跳过 LLM 分组审查，
        直接走纯 DD/αμ 引擎，用于与 LLM 审查开关开启时做对比。
        """
        threshold = switch_cards if switch_cards is not None else DD_ALPHAMU_SWITCH_CARDS
        perspective = state.current_player
        cards = len(state.hands.get(perspective, []))
        if not enable_llm_review:
            if cards > threshold:
                return self._dd_play(state, dd_samples, dd_scoring_mode)
            return self._alpha_mu_play(state)
        if cards > threshold:
            return self._dd_llm_play(state, use_reasoning, dd_samples, dd_scoring_mode)
        return self._alphamu_llm_play(state, use_reasoning)

    def _dd_llm_play(self, state: PlayState, use_reasoning: bool = False,
                     dd_samples: int = None, dd_scoring_mode: str = None) -> Dict[str, Any]:
        """中盘 DD 搜索 + LLM 分组审查。

        DD 候选没有 αμ 的 best_vector，改用各 world 赢墩数向量等价分组：
        scores 完全相同 → 各世界表现等价 → 一组；组内按花色+rank区间拆分。
        success_rate = scores 中 ≥ 定约所需墩数的占比（成约率，与 αμ 同义）。
        """
        dd_result = self._dd_play(state, dd_samples, dd_scoring_mode)
        full_output = dd_result.get("full_output", {})
        full_output["engine_phase"] = "midgame_dd"
        candidates = full_output.get("mcts_stats", {}).get("candidates", [])
        if not candidates:
            full_output["llm_review_status"] = "跳过：无候选牌"
            return dd_result

        trump_suit = state.contract.suit if state.contract.suit != "NT" else ""
        groups = self._group_candidates_by_tricks_vec(
            candidates, state.contract.tricks_needed, trump_suit, state)

        # 防守方走独立防守审查（赢墩硬约束下传信号）
        declarer = state.contract.declarer
        dummy = state.dummy
        if state.current_player not in (declarer, dummy):
            return self._run_defender_review(state, dd_result, candidates, groups,
                                             "DD", use_reasoning)

        desperation_mode = False
        dd_iterations = full_output.get("mcts_stats", {}).get("iterations")
        if not self._should_trigger_llm(groups, candidates, n_samples=dd_iterations):
            all_zero = candidates and all(c.get("success_rate", 0) == 0 for c in candidates)
            if all_zero and len(candidates) >= 2:
                groups = self._build_desperation_groups(candidates, trump_suit=trump_suit, state=state)
                if len(groups) < 2:
                    full_output["llm_review_status"] = "跳过：无成约机会且分组不足"
                    return dd_result
                desperation_mode = True
                print(f"[DD-αμ-LLM] 绝望模式：DD认为无成约机会，LLM审查{len(groups)}组、力争多拿墩少宕")
            else:
                full_output["llm_review_status"] = "跳过：成功率差显著，DD已明确偏好"
                return dd_result

        if self._check_plan_invalidation(state):
            print(f"[DD-αμ-LLM] 检测到plan失效，清空旧计划")
            self.declarer_plan = self._empty_plan()

        dd_card_str = full_output.get("推荐出牌", "")
        full_output["llm_review_status"] = "已激活"
        review = self._llm_group_review(state, candidates, groups,
                                        alpha_card=dd_card_str,
                                        previous_plan=self._format_plan_for_prompt(self.declarer_plan),
                                        desperation=desperation_mode,
                                        engine_name="DD",
                                        use_reasoning=use_reasoning)
        trick_number = len(state.tricks) + 1
        if review.get("plan"):
            self.declarer_plan = self._build_plan_from_review(review, trick_number)
            plan_preview = self._format_plan_for_prompt(self.declarer_plan)[:60]
            print(f"[DD-αμ-LLM] 打牌计划已{'确认' if review.get('plan_valid') else '制定'}: {plan_preview}...")
        elif review.get("plan_valid") is False and not self._is_plan_empty(self.declarer_plan):
            self.declarer_plan = self._empty_plan()
            print(f"[DD-αμ-LLM] LLM认为现有计划无效，清空")

        chosen_group_idx = review.get("group")
        chosen_group = None
        if isinstance(chosen_group_idx, (int, float)) and not isinstance(chosen_group_idx, bool):
            idx = int(chosen_group_idx) - 1
            if 0 <= idx < len(groups):
                chosen_group = groups[idx]

        if chosen_group:
            # 组内选牌：优先 LLM 指定 card，否则机械 min/max
            target_card_str, target = self._resolve_group_card(
                state, chosen_group, review.get("card", ""), dummy)
            if target:
                self._mark_step_completed(target_card_str, trick_number)
                dd_result["card"] = target.to_dict()
                group_desc = ", ".join(c.get("card", "") for c in chosen_group["cards"])
                group_reason = review.get("reason", f"选择组{chosen_group_idx}（{group_desc}）")
                review_reasoning = f"[DD-αμ-LLM] 选组{chosen_group_idx}出{target_card_str}（{group_reason}）"
                plan_desc = review.get("plan", "")
                if plan_desc:
                    review_reasoning += f"（计划: {plan_desc[:60]}...）"
                dd_result["reasoning"] = f"{review_reasoning}\n{dd_result.get('reasoning', '')}"
                dd_result["full_output"]["推荐出牌"] = target_card_str
                dd_result["full_output"]["核心逻辑"] = review_reasoning
                review["card"] = target_card_str
                dd_result["full_output"]["llm_review"] = review
                return dd_result

        print(f"[DD-αμ-LLM] LLM选组失败(idx={chosen_group_idx})，保留DD选择")
        if review.get("plan"):
            self.declarer_plan = self._build_plan_from_review(review, trick_number)
        dd_result["full_output"]["llm_review"] = review
        return dd_result

    def _group_candidates_by_tricks_vec(self, candidates: list,
                                        tricks_needed: int,
                                        trump_suit: str = "",
                                        state: PlayState = None) -> list:
        """按计分制决策向量等价分组（DD中盘用）。

        tricks_vec 按 scoring_mode 生成：
        - "imp": IMP分数向量（防守方取负，表示防守方期望IMP）
        - "make_rate": 0/1向量（防守方取反：1=击垮，0=庄家成约）
        - "avg_tricks": 赢墩数向量（现状）
        success_rate 始终为当前方目标达成率（坐庄=成约率，防守=击垮率）。

        返回: [{"cards": [...], "success_rate": float, "group_id": int, "best_vector": str}, ...]
        """
        scoring_mode = getattr(self.dd_search, "scoring_mode", "imp") if self.dd_search else "imp"
        is_defender = False
        if state and state.contract:
            declarer = state.contract.declarer
            dummy = state.dummy
            is_defender = state.current_player not in (declarer, dummy)

        vul_decl = False
        if state and state.contract:
            from bridge.mcts.dd_search import _declarer_side_vulnerable
            vul_decl = _declarer_side_vulnerable(
                state.contract.declarer, getattr(state, "vulnerability", "NV"))

        for c in candidates:
            scores = c.get("scores") or []
            if not scores:
                c["success_rate"] = 0.0
                c["tricks_vec"] = ()
                continue
            n = len(scores)

            # success_rate：坐庄=成约率，防守=击垮率
            if is_defender:
                defender_goal = 14 - tricks_needed
                c["success_rate"] = sum(1 for s in scores if s <= defender_goal) / n
            else:
                c["success_rate"] = sum(1 for s in scores if s >= tricks_needed) / n

            # tricks_vec：按计分制生成，防守方视角取反
            if scoring_mode == "imp":
                if state and state.contract:
                    from bridge.mcts.dd_search import _raw_to_imp, _contract_score
                    imp_scores = tuple(
                        _raw_to_imp(_contract_score(t, state.contract, vul_decl))
                        for t in scores)
                    if is_defender:
                        imp_scores = tuple(-x for x in imp_scores)
                    c["tricks_vec"] = imp_scores
                else:
                    c["tricks_vec"] = tuple(scores)
            elif scoring_mode == "make_rate":
                if is_defender:
                    defender_goal = 14 - tricks_needed
                    c["tricks_vec"] = tuple(1 if t <= defender_goal else 0 for t in scores)
                else:
                    c["tricks_vec"] = tuple(1 if t >= tricks_needed else 0 for t in scores)
            else:
                # avg_tricks：防守方取负，最小化庄家赢墩 = 最大化防守方"负赢墩"
                if is_defender:
                    c["tricks_vec"] = tuple(-t for t in scores)
                else:
                    c["tricks_vec"] = tuple(scores)
        if not candidates:
            return []
        above = [c for c in candidates if c.get("success_rate", 0) > 0]
        if len(above) < 2:
            return []

        by_vec = {}
        for c in above:
            by_vec.setdefault(c["tricks_vec"], []).append(c)

        result = []
        for vec, cards in by_vec.items():
            for sg in self._split_by_rank_tier(cards):
                # 组内取 scoring_val 均值；防守方取负转为防守视角（越大越好）
                scoring_vals = []
                for c in sg:
                    sv = c.get("scoring_val")
                    if sv is not None:
                        scoring_vals.append(-sv if is_defender else sv)
                avg_scoring = sum(scoring_vals) / len(scoring_vals) if scoring_vals else None
                result.append({
                    "cards": sg,
                    "success_rate": max(c.get("success_rate", 0) for c in sg),
                    "avg_scoring_val": avg_scoring,
                    "best_vector": "DD等价",
                })
        # 按计分制和当前方视角排序：
        # - imp: avg_scoring_val（防守方已取负，越大越好）
        # - avg_tricks: avg_tricks（防守方取负后越大越好，即庄家赢墩越少越好）
        # - make_rate: success_rate（击垮率/成约率，越大越好）
        if scoring_mode == "imp" and any(g.get("avg_scoring_val") is not None for g in result):
            result.sort(key=lambda g: g.get("avg_scoring_val", 0), reverse=True)
        elif scoring_mode == "avg_tricks":
            # 组内取 avg_tricks 均值；防守方取负转为防守视角
            for g in result:
                vals = []
                for c in g["cards"]:
                    av = c.get("avg_tricks", 0)
                    vals.append(-av if is_defender else av)
                g["_sort_val"] = sum(vals) / len(vals) if vals else 0
            result.sort(key=lambda g: g["_sort_val"], reverse=True)
        else:
            result.sort(key=lambda g: g["success_rate"], reverse=True)
        for i, g in enumerate(result):
            g["group_id"] = i + 1
        return result

    def _normalize_step(self, s) -> dict:
        """把LLM输出的单步规范化为结构化战术实体，兜底缺失字段。"""
        if not isinstance(s, dict):
            s = {}
        return {
            "step": s.get("step", 1),
            "action": s.get("action", ""),
            "play_card": s.get("play_card", ""),
            "precondition": s.get("precondition", ""),
            "tactic": s.get("tactic", ""),
            "target_card": s.get("target_card", ""),
            "entry_card": s.get("entry_card", ""),
            "ruff_suit": s.get("ruff_suit", ""),
            "completed": bool(s.get("completed", False)),
        }

    def _build_plan_from_review(self, review: dict, trick_number: int) -> dict:
        """从LLM审查结果构建结构化plan。

        LLM输出的plan可能是字符串或含steps的结构。
        统一转为结构化dict存储，每个step经 _normalize_step 兜底缺失字段。
        """
        plan = self._empty_plan()
        plan["created_at_trick"] = trick_number
        plan["last_validated_trick"] = trick_number

        raw = review.get("plan", "")
        steps = review.get("steps", [])

        if isinstance(raw, str) and raw:
            plan["raw_text"] = raw
        if isinstance(steps, list) and steps:
            plan["steps"] = [self._normalize_step(s) for s in steps]
        elif isinstance(raw, str) and raw:
            # 没有结构化steps，尝试简单解析（按句号/分号分割）
            sentences = [s.strip() for s in raw.replace("；", "。").split("。") if s.strip()]
            plan["steps"] = [
                self._normalize_step({"step": i + 1, "action": s})
                for i, s in enumerate(sentences[:6])  # 最多6步
            ]
        return plan

    def _check_plan_invalidation(self, state: PlayState) -> bool:
        """检测当前plan是否失效。

        失效条件：
        0. 所有步骤都已完成 → 计划执行完毕，失效
        1. 结构化字段精确校验：步骤涉及的 play_card/target_card/entry_card 已出
           （如飞牌对象target_card被逼出、进手张entry_card被破坏）
        2. plan创建后已过太多墩（>4墩未更新）
        3. 无结构化字段的旧步骤：回退大牌子串匹配（如"飞♠K"但♠K已出）

        返回True表示plan失效，需要重新制定。
        """
        plan = self.declarer_plan
        if self._is_plan_empty(plan):
            return False

        if not isinstance(plan, dict):
            return False

        trick_number = len(state.tricks) + 1

        steps = plan.get("steps", [])
        if steps:
            all_done = all(s.get("completed") for s in steps)
            if all_done:
                print(f"[αμ+LLM] plan所有步骤已完成，清空")
                return True

        created_at = plan.get("created_at_trick", 0)
        if created_at > 0 and trick_number - created_at > 4:
            return True

        if not steps:
            return False

        played_cards = set()
        for trick in state.tricks:
            for pos, card in trick.cards:
                played_cards.add(str(card))

        key_cards = ["♠A", "♠K", "♠Q", "♠J", "♠T",
                     "♥A", "♥K", "♥Q", "♥J", "♥T",
                     "♦A", "♦K", "♦Q", "♦J", "♦T",
                     "♣A", "♣K", "♣Q", "♣J", "♣T"]

        for s in steps:
            if s.get("completed"):
                continue
            # 结构化字段精确校验
            structured = [c for c in (s.get("play_card", ""),
                                      s.get("target_card", ""),
                                      s.get("entry_card", "")) if c]
            if structured:
                for card in structured:
                    if card in played_cards:
                        print(f"[αμ+LLM] plan失效：步骤涉及的牌张{card}已出")
                        return True
                continue
            # 兜底：无结构化字段时用大牌子串匹配
            action = s.get("action", "")
            precondition = s.get("precondition", "")
            check_text = action + " " + precondition
            for card in key_cards:
                if card in check_text and card in played_cards:
                    return True

        return False

    def _mark_step_completed(self, played_card: str, trick_number: int) -> bool:
        """出牌后标记plan中匹配的步骤为完成。

        优先用 play_card 精确匹配落桌牌张；无 play_card 时回退 action 子串匹配。
        标记第一个未完成的匹配步骤为 completed=True。
        返回True表示有步骤被标记完成。
        """
        plan = self.declarer_plan
        if not isinstance(plan, dict):
            return False
        steps = plan.get("steps", [])
        if not steps:
            return False
        for s in steps:
            if s.get("completed"):
                continue
            play_card = s.get("play_card", "")
            action = s.get("action", "")
            if play_card:
                matched = (play_card == played_card)
            else:
                matched = (played_card in action)
            if matched:
                s["completed"] = True
                plan["last_validated_trick"] = trick_number
                print(f"[αμ+LLM] plan步骤{s.get('step', '?')}完成: {action[:40]}...")
                return True
        return False

    def _should_trigger_llm(self, groups: list, candidates: list = None,
                            gap_threshold: float = 0.15, n_samples: int = None) -> bool:
        """判断是否需要触发LLM分组审查。

        条件：
        1. 至少2组（有选择空间）
        2. 组间成功率差距未达"一边倒"——差距越大越不值得LLM判断。

        gap_threshold=None（αμ阶段）：仅当 top-1 与 top-2 差距达 ALPHAMU_LLM_GAP_CAP
        （默认0.35）才视为一边倒跳过，其余保留（对战术平等敏感，只拦明确一边倒）。
        DD阶段：有 n_samples 时用统计显著阈值（1.645·SE，SE随采样量自适应），
                无 n_samples 时回退固定 gap_threshold（默认0.15）。
        """
        if len(groups) < 2:
            return False
        rates = [g["success_rate"] for g in groups]
        diff = rates[0] - rates[1]
        if diff <= 0:
            return True
        if gap_threshold is None:
            return diff < ALPHAMU_LLM_GAP_CAP
        if n_samples and n_samples > 0:
            se = math.sqrt(rates[0] * (1 - rates[0]) / n_samples)
            if se <= 0:
                return True
            return diff < 1.645 * se
        return diff < gap_threshold

    def _extract_rank(self, card_str: str) -> int:
        """从牌张代码中提取数字等级。♠2→2, ♥J→11, ♣Q→12, ♦K→13, ♠A→14"""
        rank_str = card_str[1:] if len(card_str) >= 2 else ""
        rank_map = {"2": 2, "3": 3, "4": 4, "5": 5, "6": 6, "7": 7,
                    "8": 8, "9": 9, "T": 10, "10": 10, "J": 11, "Q": 12, "K": 13, "A": 14}
        return rank_map.get(rank_str, 0)

    def _resolve_group_card(self, state: PlayState, chosen_group: dict,
                            llm_card: str, dummy: str):
        """在所选组内解析本墩出牌：优先 LLM 指定的 card，否则机械 min/max 回退。

        校验：LLM 的 card 必须落在所选组内 AND 在当前可出牌内，否则丢弃，
        回退机械选牌（明手最小/其他最大）。保证赢墩永不损失。
        返回 (target_card_str, target) 或 (None, None)。
        """
        playable = self.engine.get_playable_cards()
        playable_strs = {str(c): c for c in playable}
        group_cards = {c.get("card", "") for c in chosen_group["cards"]}
        group_playable = [c for c in chosen_group["cards"] if c.get("card", "") in playable_strs]
        if not group_playable:
            return None, None
        target_card_str = None
        if llm_card and llm_card in group_cards and llm_card in playable_strs:
            target_card_str = llm_card
        if target_card_str is None:
            is_dummy_turn = (state.current_player == dummy)
            if is_dummy_turn:
                target_card_str = min(group_playable, key=lambda c: self._extract_rank(c.get("card", "")))["card"]
            else:
                target_card_str = max(group_playable, key=lambda c: self._extract_rank(c.get("card", "")))["card"]
        return target_card_str, playable_strs.get(target_card_str)

    def _is_key_defense_trick(self, state: PlayState, current_player: str) -> bool:
        """判断当前防守墩是否值得触发 LLM 审查（触发克制）。

        关键防守墩：首攻、跟同伴领出、垫牌、将吃抉择。
        首攻是防守方最重要的决策，必须触发 LLM 审查。
        """
        current = state.current_trick.cards
        if not current:
            # 首攻：防守方领出第一墩，触发 LLM 审查
            return True
        lead_pos, lead_card = current[0]
        lead_suit = lead_card.suit
        hand = state.hands.get(current_player, [])
        has_suit = any(c.suit == lead_suit for c in hand)
        if not has_suit:
            return True
        return lead_pos == PARTNERS.get(current_player)

    def _defender_llm_review(self, state: PlayState, candidates: list,
                             groups: list,
                             defender_card: str = "",
                             use_reasoning: bool = False,
                             engine_name: str = "αμ") -> dict:
        """防守方分组审查：在不损失赢墩的前提下选牌并传递信号。

        首攻时明手未摊牌，隐藏明手信息；按标准方案注入信号规则。

        返回dict:
          - group: int, 选择的组号（1-based）
          - card: str, 本墩实际出的牌张（必须在所选组内且可出）
          - reason: str, 推荐理由（含防守分析与信号意图）
          - llm_prompt: str, 完整提示词
        """
        from bridge.play_strategies import signal_scheme

        is_lead = state.phase == PlayPhase.LEAD
        hands_info = self._format_hands_info(state)
        if is_lead:
            missing_info = "明手未摊牌，庄家方关键大牌分布不可知"
            trump_analysis = "明手未摊牌，将牌统计待摊牌后确认"
            played_cards_info = "首攻阶段，无已出牌"
            partner_signals = ""
        else:
            missing_info = self._format_missing_key_cards(state)
            trump_analysis = self._format_trump_analysis(state)
            played_cards_info = self._format_played_cards_info(state)
            partner_signals = format_partner_signals_for_prompt(state, state.current_player)
        completed_tricks = self._format_completed_tricks(state)
        current_trick = self._format_current_trick(state)

        declarer = state.contract.declarer
        dummy = state.dummy
        current_player = state.current_player
        current_trick_count = len(state.current_trick.cards)
        play_position = current_trick_count + 1
        remaining_players = 4 - play_position
        declarer_remaining = max(0, state.contract.tricks_needed - state.declarer_tricks)
        defender_remaining = max(0, (14 - state.contract.tricks_needed) - state.defender_tricks)
        bidding_seq = state.bidding_sequence or "未提供"

        # 按标准方案生成信号规则文本
        sig = signal_scheme()
        signal_rules = f"""## 防守信号（{sig.name}）
**核心原则**：赢墩是硬约束，信号是赢墩等价组内的软选择。绝不能为传信号而损失赢墩。

### 姿态信号
{sig.attitude_rules}

### 张数信号
{sig.count_rules}

### 花色偏好信号
{sig.discard_rules}

### 使用约束
信号只在赢墩等价组内的牌张差异上体现，绝不能为传信号而换组（换组可能丢赢墩）。"""

        if is_lead:
            system_prompt = (
                "你是桥牌防守专家。"
                + f"{engine_name}引擎已完成首攻花色评估，给出多个候选组（按防守视角最优排序）。"
                + "你的任务是：在**不损失赢墩**的前提下，从候选组中选择首攻花色和具体牌张。"
                + "首攻是防守最重要的决策，需综合考虑："
                + "1) 叫牌过程推断的庄家/明手花色长度和大牌位置；"
                + "2) 标准首攻方案（长套首攻/助攻同伴花色/攻定约方未叫花色等）；"
                + "3) 组内牌张按标准首攻表选择。"
                + "赢墩是硬约束，首攻方案是软选择。"
                + "请以JSON格式输出分析结果。"
            )
        else:
            system_prompt = (
                "你是桥牌防守专家。"
                + f"{engine_name}引擎已默认选定第1组出牌（该组在防守视角下最优，最大化防守方期望IMP/击垮率）。"
                + "你的任务是：在**不损失赢墩**的前提下选择最佳出牌，"
                + "并利用赢墩等价组内牌张差异向同伴传递防守信号。"
                + "赢墩是硬约束，信号是赢墩等价组内的软选择。"
                + "除非非第1组有明显更好的防守价值（进张保留/防飞牌/信号意图），否则返回第1组。"
                + "请以JSON格式输出分析结果。"
            )

        group_lines = []
        is_defender = state.current_player not in (state.contract.declarer, state.dummy)
        for g in groups:
            card_strs = [c.get("card", "") for c in g["cards"]]
            rate = f"{g['success_rate']:.0%}"
            dds_eq_label = "DDS等价" if len(card_strs) > 1 else ""
            default_mark = f" ← {engine_name}默认选择" if g["group_id"] == 1 else ""
            if is_defender:
                rate_label = "防守击垮率"
            else:
                rate_label = "庄家成约率"
            group_lines.append(
                f"组{g['group_id']}: {' '.join(card_strs)} "
                f"({rate_label}{rate}) {dds_eq_label}{default_mark}".rstrip()
            )
        groups_text = "\n".join(group_lines)

        # 首攻时注入首攻方案，否则注入信号方案
        if is_lead:
            from bridge.play_strategies import lead_scheme
            lead = lead_scheme()
            is_nt = state.contract.suit == "NT"
            lead_rules = lead.nt_lead_rules if is_nt else lead.trump_lead_rules
            lead_section = f"""## 首攻方案（{lead.name}）
{lead_rules}

### 首攻花色选择原则
- 无将定约：首攻长套，助攻同伴叫过的花色，攻定约方没有叫过的花色，首攻有连张大牌的花色，攻自己最强的花色
- 有将定约：首攻有连张大牌的花色，攻自己最强的花色，攻短套准备将吃，攻将牌削弱庄家将吃能力，保护性首攻以不损失大牌，不从有A的花色中攻小牌

### 组内选牌
选定花色后，在组内按上述首攻表选择具体牌张。"""
        else:
            lead_section = signal_rules

        user_prompt = f"""## 局面信息
定约: {state.contract}
庄家: {declarer}, 明手: {dummy}
**当前出牌方: {current_player}（防守方）**
**必须从{current_player}的手牌中出牌，不能出其他位置的牌。**
本墩出牌位置: 第{play_position}家（当前墩已有{current_trick_count}张牌，之后还有{remaining_players}家未出）
庄家方已得: {state.declarer_tricks}墩, 还需: {declarer_remaining}墩成约
防守方已得: {state.defender_tricks}墩, 还需: {defender_remaining}墩击垮
当前墩: {current_trick}

## 叫牌过程
{bidding_seq}
（用于推断庄家/明手花色长度和大牌位置，辅助防守方向判断）

## 基本规则提醒
大牌永远大于小牌（A>K>Q>J>10>...>2）；必须跟出领出花色；将牌大于任何边花。

## 手牌
{hands_info}

## 将牌统计（程序计算，请直接使用，不要自行数牌）
{trump_analysis}

## 庄家方关键大牌（未出现的关键大牌可能在庄家/明手或同伴手中）
{missing_info}

## 已完成墩
{completed_tricks}

## 已出牌
{played_cards_info}

## 可选出牌组
同一组内的牌在{engine_name}采样空间中DDS等价（出哪张，庄家赢墩数相同），不同组之间DDS不等价。
**第1组是{engine_name}引擎默认选择（防守视角最优），除非其他组有第1组做不到的防守价值，否则选组1。**
{groups_text}

{lead_section}
{partner_signals}

## 输出JSON
{{
  "group": 1,（最终选择的组号，无更好选择时填1）
  "card": "♠A",（本墩实际出的牌张，必须是所选组内、且当前出牌方手中可出的牌）
  "reason": "选择理由（含防守分析与信号意图）"
}}"""

        try:
            full_prompt = f"{system_prompt}\n\n{user_prompt}"
            result = self.llm_client.chat_json(
                system_prompt, user_prompt,
                temperature=0.3, thinking=use_reasoning)
            result["llm_prompt"] = full_prompt
            return result
        except Exception as e:
            print(f"[{engine_name}+LLM] 防守审查失败: {e}")
            return {"group": 0, "reason": f"审查异常: {e}", "llm_prompt": ""}

    def _run_defender_review(self, state: PlayState, engine_result: Dict[str, Any],
                             candidates: list, groups: list,
                             engine_name: str, use_reasoning: bool = False) -> Dict[str, Any]:
        """防守方分组审查主流程：赢墩硬约束下选牌传信号。

        仅在关键防守墩触发；LLM 出牌必须落在赢墩等价组内，否则回退引擎选择。
        返回引擎可选用的 result（成功时覆盖 card/reasoning/full_output）。
        """
        full_output = engine_result.get("full_output", {})
        current_player = state.current_player
        if not self._is_key_defense_trick(state, current_player):
            full_output["llm_review_status"] = "跳过：非关键防守墩"
            return engine_result

        review = self._defender_llm_review(
            state, candidates, groups,
            defender_card=full_output.get("推荐出牌", ""),
            engine_name=engine_name, use_reasoning=use_reasoning)

        chosen_group_idx = review.get("group")
        chosen_group = None
        if isinstance(chosen_group_idx, (int, float)) and not isinstance(chosen_group_idx, bool):
            idx = int(chosen_group_idx) - 1
            if 0 <= idx < len(groups):
                chosen_group = groups[idx]
        if not chosen_group:
            full_output["llm_review_status"] = "跳过：防守LLM选组失败"
            return engine_result

        dummy = state.dummy
        target_card_str, target = self._resolve_group_card(
            state, chosen_group, review.get("card", ""), dummy)
        if not target:
            full_output["llm_review_status"] = "跳过：防守LLM出牌不合法"
            return engine_result

        group_desc = ", ".join(c.get("card", "") for c in chosen_group["cards"])
        group_reason = review.get("reason", f"选择组{chosen_group_idx}（{group_desc}）")
        review_reasoning = f"[{engine_name}+LLM] 防守选组{chosen_group_idx}出{target_card_str}（{group_reason}）"
        engine_result["card"] = target.to_dict()
        engine_result["reasoning"] = f"{review_reasoning}\n{engine_result.get('reasoning', '')}"
        full_output["推荐出牌"] = target_card_str
        full_output["核心逻辑"] = review_reasoning
        full_output["llm_review_status"] = "防守方审查已激活"
        review["card"] = target_card_str
        full_output["llm_review"] = review
        return engine_result

    def _group_candidates_by_vector(self, candidates: list,
                                     trump_suit: str = "") -> list:
        """按best_vector分组：vector相同=DDS等价=一组。

        充分利用αμ搜索结果。连续张vector必然相同（自动覆盖），
        非连续但vector相同（如2,3,5）也合并为一组。
        vector缺失时退化为连续张分组（兼容边界）。

        在vector组内，进一步按区间[2-7]/[8-10]/[J-A]、跨区间连续性、
        将牌/非将牌细分。

        任何success_rate>0的候选牌都参与分组，所有机会都保留给LLM审查。

        返回: [{"cards": [...], "success_rate": float, "group_id": int, "best_vector": str}, ...]
        """
        above = [c for c in candidates if c.get("success_rate", 0) > 0]
        if len(above) < 2:
            return []

        by_vector = {}
        no_vector = []
        for c in above:
            vec = c.get("best_vector", "")
            if vec and vec != "∅":
                by_vector.setdefault(vec, []).append(c)
            else:
                no_vector.append(c)

        result = []
        for vec, cards in by_vector.items():
            subgroups = self._split_by_rank_tier(cards)
            for sg in subgroups:
                result.append({
                    "cards": sg,
                    "success_rate": max(c.get("success_rate", 0) for c in sg),
                    "best_vector": vec,

                })

        if no_vector:
            for group in self._raw_continuous_groups(no_vector):

                result.append(group)

        result.sort(key=lambda g: g["success_rate"], reverse=True)

        for i, g in enumerate(result):
            g["group_id"] = i + 1
        return result

    def _build_desperation_groups(self, candidates: list, trump_suit: str = "",
                                   state: PlayState = None) -> list:
        """αμ认为无成约机会时，按花色+rank区间构建分组供LLM审查。

        目标是尽可能多拿墩少宕，而不是追求成约。
        防守方按庄家赢墩升序（庄家赢墩越少防守越好）。
        """
        if len(candidates) < 2:
            return []
        is_defender = False
        if state and state.contract:
            declarer = state.contract.declarer
            dummy = state.dummy
            is_defender = state.current_player not in (declarer, dummy)
        by_suit = {}
        for c in candidates:
            card_str = c.get("card", "")
            suit = card_str[:1] if card_str else "?"
            by_suit.setdefault(suit, []).append(c)
        result = []
        for suit, suit_cards in by_suit.items():
            subgroups = self._split_by_rank_tier(suit_cards)
            for sg in subgroups:
                result.append({
                    "cards": sg,
                    "success_rate": max(c.get("success_rate", 0) for c in sg),
                    "best_vector": "绝望模式",
                })
        # 坐庄：avg_tricks越大越好；防守：avg_tricks越小越好
        if is_defender:
            result.sort(key=lambda g: max(c.get("avg_tricks", 0) for c in g.get("cards", [])))
        else:
            result.sort(key=lambda g: max(c.get("avg_tricks", 0) for c in g.get("cards", [])), reverse=True)
        for i, g in enumerate(result):
            g["group_id"] = i + 1
        return result

    @staticmethod
    def _truncate_by_gap(groups: list, gap_threshold: float = 0.15) -> list:
        """按成功率降序排序后，遇到第一个≥gap_threshold的差距即截断。

        排除较低及以下的组。这样即使所有组成功率都低，
        只要彼此差距<gap_threshold，仍会保留——
        因为其中可能包含唯一成局线路。

        示例（gap_threshold=0.15）：
        - [60%, 58%, 55%, 20%] → 55%→20%差距35%≥15% → 截断，保留[60%, 58%, 55%]
        - [10%, 8%, 5%] → 无≥15%差距 → 全保留
        - [60%, 40%] → 差距20%≥15% → 截断，保留[60%]
        - [60%, 58%] → 差距2%<15% → 全保留
        """
        if len(groups) <= 1:
            return groups
        for i in range(len(groups) - 1):
            gap = groups[i]["success_rate"] - groups[i + 1]["success_rate"]
            if gap >= gap_threshold:
                return groups[:i + 1]
        return groups

    def _split_by_rank_tier(self, cards: list) -> list:
        """在vector组内按花色+rank区间分拆：先按花色，再按[2-7]/[8-10]/[J-A]，跨区间连续不拆。

        不同花色分开分组（战术意义不同），同花色内大牌和小牌也分开。
        只有同花色且同区间（或跨区间连续如7-8/T-J）才合并。

        例: ♠2♠3♠4♠5♠Q → [♠2♠3♠4♠5](low) + [♠Q](high)
        例: ♠2♠3♣2♣3♠Q♣K → [♠2♠3](low) + [♣2♣3](low) + [♠Q](high) + [♣K](high)
        例: ♠7♠8 → [♠7♠8](连续跨区间不拆)
        """
        if len(cards) <= 1:
            return [cards]
        by_suit = {}
        for c in cards:
            suit = c.get("card", "")[:1] if c.get("card") else "?"
            by_suit.setdefault(suit, []).append(c)
        result = []
        for suit, suit_cards in by_suit.items():
            if len(suit_cards) <= 1:
                result.append(suit_cards)
                continue
            sorted_cards = sorted(suit_cards, key=lambda c: self._extract_rank(c.get("card", "")))
            subgroups = [[sorted_cards[0]]]
            for i in range(1, len(sorted_cards)):
                prev_rank = self._extract_rank(sorted_cards[i-1].get("card", ""))
                curr_rank = self._extract_rank(sorted_cards[i].get("card", ""))
                same_tier = (self._rank_tier(prev_rank) == self._rank_tier(curr_rank))
                is_continuous = (curr_rank - prev_rank == 1)
                if same_tier or is_continuous:
                    subgroups[-1].append(sorted_cards[i])
                else:
                    subgroups.append([sorted_cards[i]])
            result.extend(subgroups)
        return result

    @staticmethod
    def _rank_tier(rank: int) -> str:
        """牌面等级区间：[2-7]=low, [8-10]=mid, [J-A]=high。"""
        if rank <= 7:
            return "low"
        elif rank <= 10:
            return "mid"
        else:
            return "high"

    def _raw_continuous_groups(self, candidates: list) -> list:
        """vector缺失时的退化分组：同花色+等级连续(差=1)。"""
        if not candidates:
            return []
        by_suit = {}
        for c in candidates:
            card_str = c.get("card", "")
            if not card_str:
                continue
            suit = card_str[0]
            rank = self._extract_rank(card_str)
            by_suit.setdefault(suit, []).append((rank, c))

        raw_groups = []
        for suit, entries in by_suit.items():
            entries.sort(key=lambda e: e[0])
            current = [entries[0]]
            for i in range(1, len(entries)):
                if entries[i][0] - entries[i-1][0] == 1:
                    current.append(entries[i])
                else:
                    raw_groups.append(current)
                    current = [entries[i]]
            raw_groups.append(current)

        result = []
        for group in raw_groups:
            cards = [c for _, c in group]
            result.append({
                "cards": cards,
                "success_rate": max(c.get("success_rate", 0) for c in cards),
                "best_vector": "",
            })
        return result

    def _group_candidates_by_threshold(self, candidates: list, threshold: float = 0.50) -> list:
        """[已弃用] 对candidates按同花色连续分组。保留供回退使用。"""
        above = [c for c in candidates if c.get("success_rate", 0) >= threshold]
        if len(above) < 2:
            return []

        by_suit = {}
        for c in above:
            card_str = c.get("card", "")
            if not card_str:
                continue
            suit = card_str[0]
            rank = self._extract_rank(card_str)
            by_suit.setdefault(suit, []).append((rank, c))

        raw_groups = []
        for suit, entries in by_suit.items():
            entries.sort(key=lambda e: e[0])
            current = [entries[0]]
            for i in range(1, len(entries)):
                if entries[i][0] - entries[i-1][0] == 1:
                    current.append(entries[i])
                else:
                    raw_groups.append(current)
                    current = [entries[i]]
            raw_groups.append(current)

        result = []
        for idx, group in enumerate(raw_groups):
            cards = [c for _, c in group]
            max_rate = max(c.get("success_rate", 0) for c in cards)
            result.append({
                "cards": cards,
                "success_rate": max_rate,
                "group_id": idx + 1,
            })
        return result

    def _candidates_same_suit_equals(self, candidates: list) -> bool:
        """检测所有候选是否同花色紧密连张（如♥3♥2, ♠5♠4♠3）。

        当所有候选都是同一花色且等级紧密相连（相邻差=1），
        出哪张牌都等价，没有战略决策需要LLM审查。
        这不同于同花色但含高牌的等价（如♠2 vs ♠Q），
        后者保留LLM审查识别飞牌等战略差异。"""
        if len(candidates) < 2:
            return False
        top = candidates[0]
        tied = [c for c in candidates[:8]
                if c.get("success_rate") == top.get("success_rate")]
        if len(tied) < 2:
            return False
        suits = set()
        ranks = []
        for c in tied:
            card_str = c.get("card", "")
            if not card_str:
                return False
            suit = card_str[0]
            suits.add(suit)
            ranks.append(self._extract_rank(card_str))
        if len(suits) != 1:
            return False
        # 检查是否紧密连张（排序后相邻差=1）
        ranks.sort()
        for i in range(len(ranks) - 1):
            if ranks[i + 1] - ranks[i] != 1:
                return False
        return True

    def _all_suits_continuous(self, cards: list) -> bool:
        """检查一组候选牌，每个花色内部是否各自连续（差=1）。"""
        if len(cards) < 2:
            return True
        by_suit = {}
        for c in cards:
            card_str = c.get("card", "")
            if not card_str:
                return False
            suit = card_str[0]
            rank = self._extract_rank(card_str)
            by_suit.setdefault(suit, []).append(rank)
        for suit, ranks in by_suit.items():
            ranks.sort()
            for i in range(len(ranks) - 1):
                if ranks[i + 1] - ranks[i] != 1:
                    return False
        return True

    def _candidates_mixed_rank_equivalents(self, candidates: list):
        """检测同花色内同时含小牌和大牌、不相连且DDS完全等价。

        当同一花色既有小牌（等级≤5）又有大牌（等级≥11），
        且等级不相连（有缺口），且所有等价牌best_vector相同时，
        说明DDS确信结果无差异。出最高牌迷惑对手，同时LLM分析指导后续。

        返回: (Card, str)（最高牌对象和字符串），None（若未检测到）"""
        if len(candidates) < 3:
            return None
        top = candidates[0]
        tied = [c for c in candidates[:8]
                if c.get("success_rate") == top.get("success_rate")
                and c.get("avg_tricks") == top.get("avg_tricks")]
        if len(tied) < 3:
            return None
        first_vec = tied[0].get("best_vector", "")
        if not first_vec:
            return None
        for c in tied:
            if c.get("best_vector", "") != first_vec:
                return None

        by_suit = {}
        for c in tied:
            card_str = c.get("card", "")
            if not card_str:
                continue
            suit = card_str[0]
            rank = self._extract_rank(card_str)
            by_suit.setdefault(suit, []).append((rank, card_str))

        for suit, entries in by_suit.items():
            ranks = [e[0] for e in entries]
            if len(ranks) < 2:
                continue
            # 要求小牌和大牌同时存在
            min_r = min(ranks)
            max_r = max(ranks)
            if not (min_r <= 5 and max_r >= 11):
                continue
            # 要求不相连（存在等级缺口 > 1）
            ranks.sort()
            has_gap = any(ranks[i + 1] - ranks[i] > 1 for i in range(len(ranks) - 1))
            if not has_gap:
                continue
            highest_str = max(entries, key=lambda e: e[0])[1]
            return (Card(suit=highest_str[0], rank=highest_str[1:]), highest_str)
        return None

    def _candidates_dds_equivalent(self, candidates: list) -> bool:
        """检测DDS等价是否真正等价（才跳过LLM审查）。

        DDS等价有两种情况：
        - **真正等价**：每个花色内部的牌都连续（任何等级）
          ♠2345、♥KQJ（同花色）、♣AKQJ+♦32（跨花色但各自连续）
          → DDS真认为结果相同，跳过LLM
        - **可疑等价**：某花色内部不连续（如♠Q vs ♠2，有等级缺口）
          → DDS完美信息掩盖战略差异（如飞牌），保留LLM审查"""
        if len(candidates) < 2:
            return False
        top = candidates[0]
        tied = [c for c in candidates[:8]
                if c.get("success_rate") == top.get("success_rate")
                and c.get("avg_tricks") == top.get("avg_tricks")]
        if len(tied) < 2:
            return False
        first_vec = tied[0].get("best_vector", "")
        if not first_vec:
            return False
        if not all(c.get("best_vector", "") == first_vec for c in tied):
            return False

        return self._all_suits_continuous(tied)

    def _needs_strategic_review(self, candidates: list, state: PlayState) -> bool:
        """检测是否需要LLM策略审查。

        触发条件：
        1. 至少2个候选
        2. 前两名候选成功率接近（αμ无法区分，差距≤10%）
        3. 最优成功率不高（≤70%，说明定约难打，可能有唯一路线）
        4. 仅庄家方触发（防守方无需识别做庄唯一路线）
        """
        if len(candidates) < 2:
            return False
        top1 = candidates[0]
        top2 = candidates[1]
        # 条件1: 前两名成功率接近
        if top1.get("success_rate", 0) - top2.get("success_rate", 0) > 0.10:
            return False
        # 条件2: 成功率不高
        if top1.get("success_rate", 0) > 0.70:
            return False
        # 条件3: 仅庄家方
        declarer = state.contract.declarer
        dummy = state.dummy
        if state.current_player not in (declarer, dummy):
            return False
        return True

    def _llm_group_review(self, state: PlayState, candidates: list,
                           groups: list,
                           alpha_card: str = "",
                           previous_plan: str = "",
                           use_reasoning: bool = False,
                           desperation: bool = False,
                           engine_name: str = "αμ") -> dict:
        """LLM分组审查：分析各组战术意图，选择一组出牌。

        返回dict:
          - plan: str, 打牌计划
          - plan_valid: bool, 现有计划是否仍然有效
          - group: int, 选择的组号（1-based）
          - reason: str, 推荐理由
          - llm_prompt: str, 完整提示词
        """
        hands_info = self._format_hands_info(state)
        missing_info = self._format_missing_key_cards(state)
        trump_analysis = self._format_trump_analysis(state)
        completed_tricks = self._format_completed_tricks(state)
        current_trick = self._format_current_trick(state)
        played_cards_info = self._format_played_cards_info(state)

        declarer = state.contract.declarer
        dummy = state.dummy
        declarer_remaining = max(0, state.contract.tricks_needed - state.declarer_tricks)
        defender_remaining = max(0, (14 - state.contract.tricks_needed) - state.defender_tricks)
        is_trump = state.contract.suit
        is_nt = (is_trump == "NT")
        trump_cleared = self._check_trump_cleared(state) if not is_nt else False

        current_player = state.current_player
        player_role = "庄家" if current_player == declarer else ("明手" if current_player == dummy else "防守方")
        current_trick_count = len(state.current_trick.cards)
        play_position = current_trick_count + 1
        remaining_players = 4 - play_position

        system_prompt = (
            f"你是桥牌做庄专家。{engine_name}引擎已默认选定第1组出牌。"
            + (f"{engine_name}搜索已判断无成约机会，目标是**尽可能多拿墩、少宕**。" if desperation else
               "你的任务是依次检查第2组及以后的组，判断是否有组能实现某个关键战术"
               "（飞牌/将吃/进张管理/长套建立/终局打法），"
               "而第1组无法或不应实现这个战术。")
            + "如果所有非第1组都没有明显更好的战术价值，返回第1组。"
            + "只有当一个非第1组确实能实现第1组做不到的关键战术时，才选择该组。"
            "请以JSON格式输出分析结果。"
        )

        # 格式化组信息（DDS等价分组，不标注战术，避免误导LLM）
        group_lines = []
        for g in groups:
            card_strs = [c.get("card", "") for c in g["cards"]]
            rate = f"{g['success_rate']:.0%}"
            dds_eq_label = "DDS等价" if len(card_strs) > 1 else ""
            default_mark = f" ← {engine_name}默认选择" if g["group_id"] == 1 else ""
            group_lines.append(
                f"组{g['group_id']}: {' '.join(card_strs)} "
                f"(成功率{rate}) {dds_eq_label}{default_mark}".rstrip()
            )
        groups_text = "\n".join(group_lines)

        plan_section = ""
        if previous_plan:
            plan_section = f"""
## 现有打牌计划
{previous_plan}

### 校验任务
- 如果仍适用（所选组就是计划第一步）→ plan_valid=true，保持计划不变
- 如果所选组不是计划第一步 → plan_valid=false，必须制定新计划（因为偏离了原路线）

### 必须更新计划的情况（满足任一即 plan_valid=false）
- 防守方出牌异常（如垫出意外大牌、出非领出花色）
- 已暴露大牌位置与计划假设不符（如计划假设♠K在西，但已出牌显示在东）
- 花色分布严重不利（如原假设3-2实际5-0）
- 进手张被破坏（如关键进手张被防守方逼出）
"""
        else:
            plan_section = """
## 打牌计划制定
当前尚无打牌计划，请根据局面制定高层次的做庄策略，并明确第一步动作。
"""

        # 叫牌过程
        bidding_seq = state.bidding_sequence or "未提供"

        # 数输墩/赢墩分支
        if is_nt:
            loss_analysis = """1. **数赢墩（无将定约）**：
   - 逐花色列出顶张赢墩（例：♠庄AKQ2+明63→顶张3墩）。
   - 总计现有赢墩数，计算与定约所需墩数的差距。
   - 哪个花色能补足缺口且脱手次数最少？
   - 危险方是谁？树立中谁进手会攻击我薄弱花色？
   - 首攻花色是否需要忍让几轮以切断联通？
   - 首选路线失败后的后备方案及成功率？"""
        else:
            loss_analysis = """1. **数输墩（有将定约，从庄家方整体数，庄家+明手作为一体，通常从长将牌的一边数）**：
   - **将牌输墩**：直接参考上方"将牌统计"。对方将牌大牌(A/K/Q/J)的数量就是将牌输墩数。
   - **各边花输墩**：每个边花合并庄家和明手的牌一起数，识别必须输的墩。
     * 如果庄家方某花色没有A，则对方有A，该花色至少有1个输墩。
     * 如果庄家方某花色有A但缺K，且对方有K，可能还有1个输墩。
     * A是赢张不是输张；只有缺少大牌支持的小牌才是输张。
     * 注意：边花输墩可通过将吃、飞牌、长套垫牌等方式消除。
   - 合计总输墩，计算为了完成定约还需要减少多少输墩。"""

        strategy_text = self._build_strategy_text(desperation, is_nt, trump_cleared, loss_analysis, engine_name)

        user_prompt = f"""## 局面信息
定约: {state.contract}
庄家: {declarer}, 明手: {dummy}
**当前出牌方: {current_player}（{player_role}）**
**必须从{current_player}的手牌中出牌，不能出其他位置的牌。**
本墩出牌位置: 第{play_position}家（当前墩已有{current_trick_count}张牌，之后还有{remaining_players}家未出）
庄家方已得: {state.declarer_tricks}墩, 还需: {declarer_remaining}墩成约
防守方已得: {state.defender_tricks}墩, 还需: {defender_remaining}墩击垮
将牌已清完: {"是" if trump_cleared else "否"}（仅当有将定约时）
当前墩: {current_trick}

## 叫牌过程
{bidding_seq}
（用于推断对方花色长度和大牌位置，辅助飞牌方向选择和将吃风险评估）

## 基本规则提醒
大牌永远大于小牌（A>K>Q>J>10>...>2）；必须跟出领出花色；将牌大于任何边花。

## 手牌
{hands_info}

**注意：当前轮到{current_player}（{player_role}）出牌，plan中的步骤必须是{current_player}能实际执行的（牌在{current_player}手中）。**

## 将牌统计（程序计算，请直接使用，不要自行数牌）
{trump_analysis}

## 对方关键大牌（未出现的关键大牌在对方手中）
{missing_info}

## 已完成墩
{completed_tricks}

## 已出牌
{played_cards_info}

## 可选出牌组
同一组内的牌在{engine_name}采样空间中DDS等价（出哪张结果相同），不同组之间DDS不等价。
分组**不预设战术**——同一组牌既可能用于飞牌，也可能用于清将，也可能用于其他战术。
战术由你根据局面自行判断，不要根据牌张大小臆测战术类别。
**第1组是{engine_name}引擎的默认选择，除非其他组有第1组做不到的战术价值，否则选组1。**
{groups_text}

## 组内选牌（本墩具体出牌）
选定组后，还需在组内决定本墩实际出的那一张。组内牌张赢墩等价（出哪张双明手结果相同），
但出哪张在**过程**上价值不同：
1. **进手管理**：这墩由庄家还是明手赢？保留哪一边的关键进手张？
2. **信息隐藏**：出哪张对防守方泄露最少（避免暴露大牌位置或花色分布）？
3. **终局保留**：哪张留到残局更有用（保留终局遮挡/紧逼张）？
在 JSON 的 `card` 字段给出本墩实际出的牌张（必须是所选组内、且当前出牌方手中可出的牌）。

{plan_section}
## 战略分析
{strategy_text}

## 输出JSON
{{
  "group": 1,（最终选择的组号，无更好选择时填1）
  "card": "♠A",（本墩实际出的牌张，必须是所选组内、且当前出牌方手中可出的牌）
  "plan": "打牌计划简述（一句话概括）",
  "steps": [
    {{"step": 1, "action": "具体动作", "play_card": "本步执行时要出的关键牌张（如♠A，无则空）", "precondition": "前提条件（如某大牌位置、花色分布）", "tactic": "战术类型（飞牌/将吃/清将/建立长套/进张管理/终局）", "target_card": "战术目标牌（如飞牌对象，无则空）", "entry_card": "本步需要保留的进手张（无则空）", "ruff_suit": "将吃花色（无将吃则空）"}},
    {{"step": 2, "action": "...", "play_card": "", "precondition": "", "tactic": "", "target_card": "", "entry_card": "", "ruff_suit": ""}}
  ],
  "plan_valid": true/false,
  "reason": "选择理由（含战术分析）"
}}"""

        try:
            full_prompt = f"{system_prompt}\n\n{user_prompt}"
            result = self.llm_client.chat_json(
                system_prompt, user_prompt,
                temperature=0.3, thinking=use_reasoning)
            result["llm_prompt"] = full_prompt
            return result
        except Exception as e:
            print(f"[αμ+LLM] 分组审查失败: {e}")
            return {"group": 0, "reason": f"审查异常: {e}", "llm_prompt": ""}

    def _build_strategy_text(self, desperation: bool, is_nt: bool,
                              trump_cleared: bool, loss_analysis: str,
                              engine_name: str = "αμ") -> str:
        if desperation:
            return f"""⚠️ {engine_name}搜索已判定无成约机会（所有候选成功率≈0%）。目标是**尽可能多拿墩、少宕**。以下分析框架相应调整：
1. **数赢墩（力争多拿墩）**：逐花色数庄家方能赢的墩数。
   第1组是{engine_name}默认选择，检查第2组及以后是否有组能多拿墩。
2. **识别赢墩机会**：
   对照\u201c对方关键大牌\u201d列表，判断哪些花色可以通过飞牌多拿墩。
   - **如果某组所在花色对方有K/Q/J**：优先考虑飞牌来多拿墩。即使定约已无法完成，多拿一墩少宕一阶也能改善得分。
3. **依次检查第2组及以后**，判断其能多拿几墩（尽量少宕）：
   (1) **战术意图**：优先飞牌多拿墩，其次兑现顶张赢墩。
   (2) **赢墩能力**：能比第1组多拿几墩？能少宕几墩？
       特别注意：飞牌失败通常只丢1墩，飞牌成功可能多拿1墩\u2014\u2014权衡利弊。
3. 如果有组明显比第1组多拿墩，选择该组；否则选第1组。
   **以赢墩数最大化为目标**\u2014\u2014即使定约已不可能完成，也要尽量少宕。"""

        lines = [loss_analysis]
        lines.append('2. **识别飞牌机会（优先级高）**：')
        lines.append('   对照\u201c对方关键大牌\u201d列表，检查每个候选组所在花色是否缺K/Q/J（在对方手中）。')
        lines.append('')
        lines.append('   **飞牌概率原则**：')
        lines.append('   - 缺K：飞牌成功率\u224850%（K在50%概率在某一对手手中）。缺K没有\u201c砸\u201d的选择\u2014\u2014')
        lines.append('     K是单张大牌，只有飞牌或等对方主动出。如果定约需要这墩K，必须飞牌。')
        lines.append('   - 缺Q：8张配合\u2192飞牌（50%），9张配合\u2192砸Q（53%），即\u201c八飞九不飞\u201d。')
        lines.append('     但即使9张配合，如果叫牌过程暗示Q在某对手手中，仍应飞牌。')
        lines.append('')
        lines.append('   **飞牌方向推断**：')
        lines.append('   - 如果叫牌过程中某对手显示了强牌（开叫/争叫/跳叫），大牌大概率在他手中，')
        lines.append('     飞牌方向应指向持有强牌的一方。')
        lines.append('   - 如果某对手一直Pass，大牌大概率在叫过牌的对手手中。')
        lines.append('   - 注意：弱二开叫、阻击叫的对手通常大牌集中在该花色，边花大牌可能在同伴手中。')
        lines.append('')
        lines.append('3. **审查任务：检查第2组及以后是否能实现第1组做不到的关键战术**：')
        lines.append('   **第1组是{0}默认选择，除非非第1组有明确的战术优势，否则选组1。**'.format(engine_name))
        lines.append('   依次检查各组（跳过第1组），判断：')
        lines.append('   - 该组是否能启动一个第1组无法启动的关键战术？')
        lines.append('     关键战术包括：飞牌（捕捉对方K/Q/J）、树立长套（垫输墩）、')
        lines.append('     将吃（多拿墩）、进张管理（保留关键进手）、终局打法（投入/挤牌）。')
        if not is_nt:
            lines.append('     有将定约还包括清将。')
        lines.append('   - 如果该组只是成功率不同但没有战术差异\u2192跳过，不替换第1组')
        lines.append('   - 如果该组确实能启动第1组做不到的关键战术\u2192选择该组并说明理由')
        lines.append('')
        lines.append('   对每组还需要评估（非第1组才需要逐条评估，第1组作为参照）：')
        lines.append('   (1) **战术意图**：该组能启动什么关键战术？常见战术包括：飞牌、树立长套、将吃、进张管理、终局打法（投入/挤牌）。')
        if not is_nt:
            lines.append('       有将定约还包括清将。')
        lines.append('       注意：同花色内的小牌和大牌都可能用于多种战术，需结合局面判断。')
        lines.append('   (2) **与第1组的差异**：该组启动的战术，第1组是否也能启动？如果第1组也能，')
        lines.append('       那没有替换的必要——第1组成功率更高或等同。')
        lines.append('   (3) **预测回牌**：出该组后，防守方最可能回攻什么？是否威胁定约？')
        lines.append('   (4) **失败代价**：若该战术失败，后备路线是否还在？')
        lines.append('       特别注意：飞牌失败通常只丢1墩，但错过飞牌机会可能导致定约必宕。')
        lines.append('   (5) **将吃风险**：出非将牌长套时，防守方缺门后可能将吃。连出两张同花色边花后要小心。')
        if trump_cleared:
            lines.append('      （当前将牌已清完，无需担心被将吃）')
        else:
            lines.append('      考虑对方将牌长度，必要时先清将再打长套。')
        lines.append('4. **进张管理**：选这组后，明暗两手的进手张是否够兑现树立的赢墩？')
        lines.append('   特别注意：飞牌也需要进手张\u2014\u2014飞牌成功后需要回到长套方继续飞或兑现赢墩。')
        lines.append('5. **结论**：如果所有非第1组都没有第1组做不到的战术价值\u2192选第1组。')
        lines.append('   如果某个非第1组能启动第1组做不到的关键战术\u2192选择该组并解释为什么值得替换αμ的选择。')
        lines.append('')
        lines.append('## 一致性强约束')
        lines.append('如果所有非第1组都没有更好的战术价值，必须选第1组。')
        lines.append('只有当某个非第1组确实能实现第1组做不到的关键战术时，才选择该组。')
        lines.append('不要因为非第1组的成功率略低就选第1组\u2014\u2014关键是战术差异，不是成功率。')
        lines.append('不要因为非第1组的成功率略高就选非第1组\u2014\u2014关键是战术差异，不是成功率。')
        return '\n'.join(lines)

    # ────────────────────────────── 飞牌启动策略 ──────────────────────────────
    # 窗口期主动启动（2026-09-08，拖延策略已废弃）：探针识别出结构（Δ≥阈值）
    # 即处于窗口期，此刻飞最有价值。领出方为庄/明手而引擎榜首是其他花色时，
    # 主动改出该花色路线启动飞牌流程，避免"顶张先打完、窗口关闭后飞牌无收益"。
    #   ① 识别飞牌结构：DD 用探针（finesse_probe），αμ 用模板法（静态间张）；
    #   ② 窗口期启动（_probe_lead_finesse_prefer）：9 张及以上按砸/飞分流，
    #      <9 张只飞不砸；比值门槛（0.95）明显劣势时尊重引擎。
    _FINESSE_R2V = {'A': 14, 'K': 13, 'Q': 12, 'J': 11, 'T': 10, '9': 9, '8': 8,
                    '7': 7, '6': 6, '5': 5, '4': 4, '3': 3, '2': 2}

    def _detect_finesse_struct(self, state: PlayState,
                               result: Dict[str, Any] = None) -> Dict[str, Dict[str, Any]]:
        """识别飞牌结构。

        引擎分流（2026-09-07 明确）：DD 引擎只用探针法（finesse_probe 键存在
        即采纳，探针为空 = 无飞牌结构，不回退模板）；αμ 引擎无 probe，回退
        模板法（静态间张识别）。返回 {花色: {对象, 说明}}。
        """
        if result is not None:
            full_output = result.get("full_output") or {}
            if "finesse_probe" in full_output:
                # DD 引擎专用（探针法）：只信探针结果。探针为空 = 该花色位置
                # 不敏感（无需飞），不再回退模板法——模板法会误判"缺K即可飞"，
                # 如南直接领出 Q 的假飞场景（敌方总能压 K，Δ≈0）会被错误干预。
                probe = full_output.get("finesse_probe") or {}
                detected = {}
                r2v = self._FINESSE_R2V  # 'K' → 13，与模板对象数值口径一致
                declarer = state.contract.declarer
                dummy = state.dummy
                for suit, info in probe.items():
                    obj = info.get("对象")
                    obj_v = r2v.get(obj, None)
                    if obj_v is None:
                        continue  # 探针对象无法映射为数值，跳过该花色
                    # 可飞性校验2026-09-09删除：Δ≥阈值即采纳为结构。
                    # 误出防护已由接应/领出执行层承接——威胁比较制"选不出牌就尊重
                    # 引擎"（_finesse_commit_check 返回 None），不会再误改出小牌。
                    detected[suit] = {
                        "对象": obj_v,
                        "Δ": info.get("Δ", 0),
                        "引牌": info.get("引牌", ""),
                        "说明": f"探针Δ{info.get('Δ', 0)}（{info.get('引牌', '?')}）",
                        "来源": "probe",
                        "侧": "本侧",
                        "对象牌": obj,
                    }
                return detected
        # 以下为方法B：静态间张识别庄家+明手各花色是否存在飞牌结构。
        # （无 probe 时回退）
        declarer = state.contract.declarer
        dummy = state.dummy
        merged = []
        for pos in (declarer, dummy):
            hand = state.hands.get(pos, [])
            if not hand:
                return {}
            merged.extend(hand)
        # 已打出的大牌不再是"缺失对象"（如 Q/K 已出，该花色无需再飞）
        # 按花色分别记录，避免跨花色"串味"（♠Q 打出不能影响 ♥ 的缺失判定）
        played_by_suit: Dict[str, set] = {}
        for t in state.tricks:
            for _, c in t.cards:
                if c:
                    rv = self._FINESSE_R2V.get(c.rank)
                    if rv:
                        played_by_suit.setdefault(c.suit, set()).add(rv)
        for _, c in state.current_trick.cards:
            if c:
                rv = self._FINESSE_R2V.get(c.rank)
                if rv:
                    played_by_suit.setdefault(c.suit, set()).add(rv)
        suits = sorted({c.suit for c in merged})
        result = {}
        for s in suits:
            ranks = sorted(
                [self._FINESSE_R2V.get(c.rank, 0) for c in merged if c.suit == s],
                reverse=True,
            )
            if not ranks or len(ranks) < 4:
                continue
            present = set(ranks) | played_by_suit.get(s, set())
            missing = [m for m in [14, 13, 12, 11] if m not in present]
            if not missing:
                continue  # 大牌齐全 → 不需飞
            for m in sorted(missing, reverse=True):
                if m in (14, 11):
                    continue  # 缺A无控制；仅缺J（A/K/Q齐全）无需飞，连砸AKQ三轮即可处理
                # 控制张/飞张基于 present（手牌 ∪ 已出）：A 已兑现（先砸后飞）
                # 时仍是上方控制，K 未现则缺 K 结构继续成立，供 9砸后续保护间张
                above = [r for r in present if r > m]
                # 飞张只计"当前仍在我方手中"的间张（≥T 且 < 对象）：敌方打出/持有的
                # T/J 不是我们的飞张，不能据此判定该花色"可飞"（如 ♥K32+A65 缺 Q
                # 但无间张 → 不是飞牌结构，走 AK 兑取，不应启动飞Q流程）。
                below = [r for r in ranks if r < m and r >= 10]
                if above and below:
                    result[s] = {"对象": m, "说明": f"缺上方{len(above)}/飞张{len(below)}"}
                    break
        return result

    @staticmethod
    def _finesse_obj_name(m: int) -> str:
        for r, v in {"A": 14, "K": 13, "Q": 12, "J": 11, "T": 10}.items():
            if v == m:
                return r
        return "?"

    def _merge_finesse_flow(self, state: PlayState,
                            finesse_struct: Dict[str, Dict[str, Any]]
                            ) -> Dict[str, Dict[str, Any]]:
        """跟牌接应的结构来源：并入已启动的 finesse_flow。

        DD 探针门控只在领出侧生效（跟牌时 trick_cards 非空 → 探针判空），若
        只信当墩探针，跟牌墩将永远无结构、接应判据成死代码。finesse_flow 是
        流程启动墩写入的稳定对象（不随探针滑动窗口下移），恰是跟牌接应所需
        的结构来源；对象已现身者剔除（2026-09-10：流程死活只按"对象是否现身"
        判定，不再检查我方上方控制——对象可为 A/K/Q 乃至滑动后的 J/T，任何
        对象"上控制"尺子都不构成飞的支点；对象未现身流程不停）。已有探针
        结构的花色以探针为准（当墩实际探测优先）。
        """
        if not state.finesse_flow:
            return finesse_struct
        merged = dict(finesse_struct)
        for s, obj in state.finesse_flow.items():
            if not isinstance(obj, int) or s in merged:
                continue
            if self._finesse_flow_dead(state, s, obj):
                continue
            merged[s] = {"对象": obj, "说明": "流程进行中（flow）", "来源": "flow",
                         "对象牌": self._finesse_obj_name(obj)}
        return merged

    def _is_leading(self, state: PlayState) -> bool:
        """当前出牌方是否在领出：本墩尚无任何牌（自己是第一家）。"""
        return not any(c for _, c in state.current_trick.cards if c)

    def _is_discarding(self, state: PlayState) -> bool:
        """当前出牌方是否在垫牌：本墩已有人领出，且手中无领出花色的牌（只能垫）。

        垫牌时不做任何飞牌处理（延迟/8飞9砸/9砸后续/强制接应），
        飞牌策略只作用于能正常出牌（领出或跟牌）的时刻。
        """
        lead_suit = None
        for _, c in state.current_trick.cards:
            if c:
                lead_suit = c.suit
                break
        if lead_suit is None:
            return False  # 尚无领出 → 自己是领出者，不是垫牌
        hand = state.hands.get(state.current_player, [])
        return not any(c.suit == lead_suit for c in hand)

    def _apply_finesse_tactics(self, state: PlayState, result: Dict[str, Any],
                               ratio: float) -> Dict[str, Any]:
        """统一飞牌特殊处理管线（独立于引擎，DD/αμ 共用）。

        飞牌过程都从"领出"开始，按出牌场景区分（仅庄家方视角）：
          领出 → 窗口期主动启动（_probe_lead_finesse_prefer，2026-09-08）：
                探针识别出结构即窗口期，榜首为其他花色时主动改出该花色启动；
                引擎已在飞牌花色则尊重引擎。不做 8飞9砸。
          跟牌（接应）→ 队友已领出飞牌花色、本家必须跟牌时：
                强制接应 + 8飞9砸（8飞9不飞 / 9张有AQ没K先砸后飞）
          垫牌 → 不处理任何飞牌（垫牌只需垫好）
        A 已砸后不再干预，交给引擎自行决策（9砸后续已移除）。
        """
        if (state.current_player in (state.contract.declarer, state.dummy)
                and FINESSE_DEFER_ENABLE):
            if self._is_discarding(state):
                return result  # 垫牌：直接信任引擎推荐
            if self._is_leading(state):
                # 领出：先判结构（探针窗口期），无结构则放行；有结构则交给
                # 窗口期启动/9砸/流程延续逻辑处理。
                result = self._apply_lead_finesse_check(state, result, ratio)
            else:
                # 跟牌：队友已在飞牌花色启动、本家必须接应时才考虑 8飞9砸。
                # 结构识别以当墩探针为准，但探针门控只在领出侧生效（跟牌时
                # trick_cards 非空 → 探针必然判空），故并入已启动的 finesse_flow
                # （稳定对象，不随滑动窗口下移）作为跟牌侧的结构来源，使 DD 引擎
                # 的接应判据不再成死代码（2026-09-10：跟牌侧接应改由 flow 驱动）。
                fs = self._detect_finesse_struct(state, result)
                fs = self._merge_finesse_flow(state, fs)
                forced = self._finesse_commit_check(state, fs)
                if forced:
                    result, committed = self._apply_finesse_commit(state, result, fs, ratio)
                    # 仅强制接应成立（飞张与榜首差别不大=融合）才继续8飞9砸；
                    # 尊重引擎（飞张明显劣势=非融合）时不再干预
                    if committed:
                        result = self._apply_eight_nine_rule(state, result, ratio)
        return result

    def _apply_lead_finesse_check(self, state: PlayState, result: Dict[str, Any],
                                  ratio: float) -> Dict[str, Any]:
        """领出时的飞牌判定（独立于引擎，DD/αμ 共用）。

        飞牌过程从"领出"开始：先识别结构（窗口期）；引擎榜首是其他花色时
        由 _probe_lead_finesse_prefer 主动改出该花色启动飞牌；引擎已在飞牌
        花色则尊重引擎。领出不引入 8飞9砸（按"队友跟牌必须接应"才考虑）。
        """
        # 结构探测（2026-09-10）：本侧 + 队友侧（仅领出方为庄/明手时探测）全部
        # 合并为一个结构池，同花色保留 Δ 高者；后续 9砸/flow/窗口启动统一
        # 过这个池，多结构并存时按 Δ 降序逐花色过退让门控，启动第一个通过
        # 的花色（_probe_lead_finesse_prefer）。
        local = self._detect_finesse_struct(state, result)
        partner = self._probe_partner_finesse_struct(state)
        finesse_struct = dict(local)
        for s, info in partner.items():
            if s not in finesse_struct or (info.get("Δ") or 0) > (finesse_struct[s].get("Δ") or 0):
                finesse_struct[s] = info
        full_output = result.get("full_output", {})
        mcts_stats = full_output.get("mcts_stats") or {}
        candidates = mcts_stats.get("candidates") or []
        if not finesse_struct:
            # 本侧+队友侧均无结构：Δ 是采样量，探针判空不代表流程结束——
            # 若有进行中的 finesse_flow（对象未现身）→ 仍走流程延续，顶张侧
            # 回手后不会被"一时判空"中断。
            if state.finesse_flow and candidates and self._apply_flow_continuation(
                    state, result, {}, candidates):
                return result
            full_output["领出飞牌"] = {"引发": False, "说明": "无飞牌结构"}
            result["full_output"] = full_output
            return result
        # 9砸后阶段（A已砸、K未现，含"回手整理进手"之后）分流：
        #   - 非顶张方（手中无 A/Q）领出：可领出飞牌花色小牌完成飞牌；若引擎
        #     选了无关花色（绕路丢路线）→ 强制改出飞牌花色飞张小牌（规则优先）。
        #   - 顶张方（持 A/Q）领出：不得自己领出该花色（大小牌都不行——K 的
        #     决定方向错误），须换无关花色回队友手（队友稳赢接应），由队友侧飞。
        nine_suits = sorted(
            (s2 for s2 in finesse_struct if self._nine_cash_done(state, s2)),
            key=lambda s2: finesse_struct[s2].get("Δ") or 0.0,
            reverse=True)
        if nine_suits:
            s2 = nine_suits[0]
            leader = state.current_player
            leader_high = self._has_high_suit_cards(state, s2, leader, (14, 12))
            if not leader_high:
                # 非顶张方：可领出飞牌小牌找飞 → 引擎选无关花色时强制完成飞牌
                small = [c for c in candidates if c.get("card") and c["card"][0] == s2
                         and self._FINESSE_R2V.get(c["card"][1:], 0) <= 9]
                if small:
                    pick = min(small, key=lambda c: self._FINESSE_R2V.get(c["card"][1:], 0))
                    pick_str = pick["card"]
                    cur = result.get("card")
                    cur_str = str(cur) if cur else ""
                    if not (cur_str and cur_str[0] == s2):
                        hint3 = (f"[继续飞牌] {s2}已砸A、K未现，飞牌流程进行中，"
                                 f"改出{pick_str}完成飞牌")
                        print(hint3)
                        reasoning = result.get("reasoning", "")
                        result["card"] = Card(pick_str[0], pick_str[1:])
                        result["reasoning"] = f"{hint3}\n{reasoning}"
                        full_output["推荐出牌"] = pick_str
                        full_output["核心逻辑"] = hint3 + "\n" + full_output.get("核心逻辑", "")
                        full_output["领出飞牌"] = {"引发": True, "花色": s2, "对象": 13,
                                                   "领出": pick_str, "说明": "9砸后继续飞牌完成流程"}
                        full_output["继续飞牌"] = {"花色": s2, "原选": cur_str or "无",
                                                   "改选": pick_str, "说明": "9砸后K未现，继续飞牌流程"}
                        result["full_output"] = full_output
                        return result
            else:
                # 顶张方：不得自己领出飞牌花色 → 强制回手（队友稳赢接应）
                reentry = self._cash_reentry(state, candidates, s2)
                if reentry:
                    pick, pick_val = reentry
                    org_str = str(result.get("card")) if result.get("card") else ""
                    cur = Card(pick[0], pick[1:])
                    hint2 = (f"[9砸回手] {s2}已砸A、K未现，顶张方领出该花色无效，"
                             f"改出无关小牌{pick}(值{pick_val:.3f})回队友手再飞K")
                    print(hint2)
                    reasoning = result.get("reasoning", "")
                    result["card"] = cur
                    result["reasoning"] = f"{hint2}\n{reasoning}"
                    full_output["推荐出牌"] = pick
                    full_output["核心逻辑"] = hint2 + "\n" + full_output.get("核心逻辑", "")
                    full_output["9砸回手"] = {"花色": s2, "领出": org_str,
                                              "改选": pick,
                                              "说明": "顶张方不领出飞牌花色，回队友手再飞"}
                    full_output["领出飞牌"] = {"引发": True, "花色": s2, "对象": 13,
                                               "领出": org_str,
                                               "说明": "顶张方不领出飞牌花色，回手整理"}
                    result["full_output"] = full_output
                    return result
        # 飞牌流程跨墩延续（finesse_flow 标记，9张需飞/9砸启动后必须完成该花色）：
        # 启动回手/直飞/砸那墩写入标记，后续领出时优先检查——引擎若带偏到其他花色，
        # 非顶张方强制出该花色飞张小牌、顶张方强制回手队友侧飞；不再走拖延评估。
        if self._apply_flow_continuation(state, result, finesse_struct, candidates):
            return result
        # 窗口期主动启动：探针识别出飞牌结构（Δ≥阈值）= 位置敏感。领出方为
        # 庄/明手而引擎榜首是其他花色时，主动改出该花色路线启动飞牌，避免
        # "顶张先打完、窗口关闭后飞牌无收益"的死锁。但"位置敏感"≠"该启动"：
        # 是否值得由 _probe_lead_finesse_prefer → _finesse_launch_worthwhile
        # 的退让门控（契约必要性/失败安全/升级价值/低比值）逐花色裁定，全不
        # 满足则退让、尊重引擎。将牌不豁免，与边花同判据。9张及以上按砸/飞
        # 分流；<9张只飞不砸。
        if finesse_struct and candidates:
            prefer = self._probe_lead_finesse_prefer(
                state, finesse_struct, candidates, ratio, result)
            if prefer:
                pick, why = prefer
                org_str = str(result.get("card")) if result.get("card") else ""
                hint4 = (f"[窗口期启动飞牌] 探针识别出飞牌结构，"
                         f"改出{pick}启动（{why}）")
                print(hint4)
                reasoning = result.get("reasoning", "")
                result["card"] = Card(pick[0], pick[1:])
                result["reasoning"] = f"{hint4}\n{reasoning}"
                full_output["推荐出牌"] = pick
                full_output["核心逻辑"] = hint4 + "\n" + full_output.get("核心逻辑", "")
                full_output["窗口期启动"] = {"花色": pick[0], "原选": org_str,
                                             "改选": pick, "说明": why}
                result["full_output"] = full_output
                return result
        cur = result.get("card")
        cur_str = str(cur) if cur else ""
        if not cur_str or cur_str[0] not in finesse_struct:
            full_output["领出飞牌"] = {
                "引发": False,
                "结构": "、".join(
                    f"{s}(" + self._finesse_obj_name(finesse_struct[s]["对象"]) + ")" for s in finesse_struct),
                "说明": "未领出飞牌花色，不引发",
            }
            result["full_output"] = full_output
            return result
        suit = cur_str[0]
        obj = finesse_struct[suit]["对象"]
        struct_desc = f"{suit}(" + self._finesse_obj_name(obj) + ")"
        hint = (f"[领出飞牌] 引擎领出{cur_str}（{struct_desc}）：已在该花色，尊重引擎，"
                f"{'登记流程' if not self._finesse_obj_played(state, suit, obj) else '对象已现身'}")
        print(hint)
        if not self._finesse_obj_played(state, suit, obj):
            # 补登记 finesse_flow（2026-09-10）：引擎已领出飞牌花色（方向正确）
            # 时，此前该路径从不写流程标记，导致下一家跟牌时接应判据无结构来源
            # （跟牌侧探针必空、flow 为空 → 尊重引擎，不接应）。对象未现身则记
            # 为流程进行中，由跟牌侧 _merge_finesse_flow 并入结构走威胁比较制、
            # 领出侧 _apply_flow_continuation 强制续飞/回手。
            state.finesse_flow[suit] = obj
            full_output["领出飞牌"] = {"引发": True, "花色": suit, "对象": obj,
                                       "领出": cur_str,
                                       "说明": "引擎领出飞牌花色（对象未现身），登记流程供接应/续飞"}
        else:
            full_output["领出飞牌"] = {"引发": True, "花色": suit, "对象": obj,
                                       "领出": cur_str, "说明": "引擎领出飞牌花色，尊重引擎"}
        if len(candidates) >= 2:
            if self._nine_cash_done(state, suit):
                leader_high = self._has_high_suit_cards(
                    state, suit, state.current_player, (14, 12))
                if not leader_high:
                    # 非顶张方领出飞牌花色（小牌找飞）→ 方向正确，尊重引擎
                    full_output["领出飞牌"]["说明"] = "非顶张方领出飞牌花色找飞，尊重引擎"
                else:
                    # 顶张方（持A/Q）领出飞牌花色：K决定方向错误（飞K无效），
                    # 强制回手；无稳赢回手牌则尊重引擎。
                    reentry = self._cash_reentry(state, candidates, suit)
                    if reentry:
                        pick, pick_val = reentry
                        cur = Card(pick[0], pick[1:])
                        hint2 = (f"[9砸回手] {suit}已砸A、K未现，顶张方领出该花色无效，"
                                 f"改出无关小牌{pick}(值{pick_val:.3f})回队友手再飞K")
                        print(hint2)
                        reasoning = result.get("reasoning", "")
                        result["card"] = cur
                        result["reasoning"] = f"{hint2}\n{hint}\n{reasoning}"
                        full_output["推荐出牌"] = pick
                        full_output["核心逻辑"] = (hint2 + "\n" + hint + "\n"
                                                   + full_output.get("核心逻辑", ""))
                        full_output["9砸回手"] = {"花色": suit, "领出": cur_str,
                                                  "改选": pick,
                                                  "说明": "A已砸、K未现，顶张方回队友手再飞"}
                    else:
                        full_output["领出飞牌"]["说明"] = "9砸后无稳赢回手牌，尊重引擎"
            else:
                # 非9砸阶段领出该花色：已属飞牌花色路线，尊重引擎（不拖延）。
                # 窗口期主动启动由 _probe_lead_finesse_prefer 在"领出非该花色"时完成，
                # 此处不干预（2026-09-08 拖延策略废弃）。
                full_output["领出飞牌"]["说明"] = "已领出飞牌花色，尊重引擎（不拖延）"
        result["full_output"] = full_output
        if not full_output.get("推荐出牌"):
            full_output.setdefault("推荐出牌", str(result["card"]))
        return result

    def _probe_partner_finesse_struct(self, state: PlayState) -> Dict[str, Dict[str, Any]]:
        """队友侧视角的飞牌结构探测（探针法，2026-09-10）。

        当前领出方是庄/明手时才有效：以队友为领出方视角再跑一次 DD 评估
        （采样+分桶），Δ≥FINESSE_PROBE_DELTA 才算结构。结果与本侧探测
        （_detect_finesse_struct）合并成统一结构池，供窗口期启动按 Δ 降序
        逐花色过退让门控。无 finesse_probe 键（队友仅一张可出等）→ 视为无。
        """
        leader = state.current_player
        declarer = state.contract.declarer
        dummy = state.dummy
        if leader not in (declarer, dummy):
            return {}
        partner = dummy if leader == declarer else declarer
        try:
            rs = self.dd_search.search(state, perspective=partner, actual_turn=partner)
        except Exception:
            return {}
        partner_fo = rs.get("full_output") or {}
        if "finesse_probe" not in partner_fo:
            return {}
        partner_probe = partner_fo.get("finesse_probe") or {}
        out = {}
        r2v = self._FINESSE_R2V
        for s, info in partner_probe.items():
            obj = r2v.get(info.get("对象"))
            if obj is not None:
                out[s] = {
                    "对象": obj,
                    "Δ": info.get("Δ", 0),
                    "引牌": info.get("引牌", ""),
                    "说明": f"探针Δ{info.get('Δ', 0)}（{info.get('引牌', '?')}）",
                    "来源": "probe",
                    "侧": "伙伴侧",
                }
        return out

    def _apply_flow_continuation(self, state: PlayState, result: Dict[str, Any],
                                 finesse_struct: Dict[str, Dict[str, Any]],
                                 candidates: List[Dict[str, Any]]) -> bool:
        """飞牌流程跨墩延续（finesse_flow 标记）。

        窗口期启动/9张/9砸流程在"启动那墩"（回手/直飞/砸顶张）写入
        state.finesse_flow，此后每一次领出都必须完成该花色飞牌（含走其他
        花色过手的回手动作），不再被其他花色带偏。处理逻辑与9砸后分支同构：
          - 非顶张方领出：若引擎榜首非该花色 → 强制改出该花色最小飞张小牌（≤9）
          - 顶张方领出：不得自领该花色 → 强制回手（队友稳赢接应），由队友侧飞
          - 榜首已是该花色（正在飞）→ 尊重引擎，仅记录状态
        流程结束条件：对象大牌已现身（被砸落/被打出，飞牌成败已定）→ 清除标记；
        对象未现身流程不停，后续领出由当墩探针重新检测（2026-09-10）。
        返回 True 表示已处理（含尊重引擎），调用方直接返回 result。
        """
        full_output = result.get("full_output", {})
        # 显式登记路径已覆盖全部开飞场景（窗口期启动改出/引牌直出/伙伴侧过手/
        # 引擎已在该花色的补登记），隐式启动（历史上曾领出即可补登）已于
        # 2026-09-11 删除——条件过宽，任意一墩探针偶发报结构即永久登记、
        # 不走退让门控且无日志（6♠ 例 flow[♠]=A 的来源）。与其配套的
        # _our_side_led_suit 一并移除；finesse_flow_ends 保留作终结审计。
        if not state.finesse_flow:
            return False
        mcts_stats = full_output.get("mcts_stats") or {}
        candidates = mcts_stats.get("candidates") or candidates
        cur = result.get("card")
        cur_str = str(cur) if cur else ""
        leader = state.current_player
        # 清理已结束流程：仅按"对象现身"判定（2026-09-10：不再检查上方控制，
        # 对象未现身流程就有效——A/K/Q/滑动后小对象一视同仁；对象已现身即清除，
        # 后续领出由当墩探针重新检测）。
        active = []
        for s in list(state.finesse_flow.keys()):
            obj = state.finesse_flow[s]
            if not isinstance(obj, int):
                info_s = finesse_struct.get(s)
                if not info_s:
                    del state.finesse_flow[s]
                    continue
                obj = info_s["对象"]
                state.finesse_flow[s] = obj
            if self._finesse_flow_dead(state, s, obj):
                del state.finesse_flow[s]
                # 对象现身或己方已无盖过对象的牌 => 流程终结（2026-09-12 双原则）：
                # 记录终结墩数供审计，此后须重新领出该花色才有资格再启动流程。
                state.finesse_flow_ends[s] = len(state.tricks)
                continue
            active.append((s, obj))
        if not active:
            return False
        flow_suits = {s for s, _ in active}
        # 流程内动作决定出牌，不设"榜首全赢稳成→押后"的软指标：
        # 全赢是采样样本口径，不是出牌属性，不能作为是否尊重引擎的依据。
        # 尊重引擎只由硬性判据触发——回手无稳赢牌（顶张方）、续飞队友无
        # 该花色可接应（非顶张方）、或榜首本就是流程花色已在进行。
        best = None  # (val, s, obj, mode, pick)
        for s, obj in active:
            cur_in_flow = bool(cur_str and cur_str[0] == s)
            suit_cands = [c for c in candidates if c.get("card") and c["card"][0] == s]

            def _cv(cs: str) -> float:
                for c in candidates:
                    if c.get("card") == cs:
                        v = c.get("scoring_val")
                        return v if v is not None else c.get("avg_tricks", 0.0)
                return 0.0

            # 回手只适用于"顶张方领出"：顶张方 = 手中持 >对象 的上方控制
            # （如飞 K 时持 A；Q<K 是飞张不是顶张，持 Q 者是飞张侧，应继续飞
            #  而非回手——9飞第二轮北持 ♠Q 被误判回手的 bug，2026-09-08）。
            lead_ctrl = any(self._FINESSE_R2V.get(c.rank, 0) > obj
                            for c in state.hands.get(leader, []) if c.suit == s)
            if lead_ctrl and self._has_finesse_reentry_high(state, s, leader, obj):
                # 顶张端仍留有能盖过敌方未出牌（除 obj 外）的间张 → 强制回手再飞
                reentry = self._cash_reentry(state, candidates, s)
                if not reentry:
                    continue  # 无稳赢回手牌 → 该流程无法行动
                pick, val = reentry
                mode = "回手"
                # 比值退让（2026-09-12，与强制接应同款两段式）：回手牌相对引擎
                # 榜首做成率/决策值差距悬殊 → 尊重引擎，该流程不行动。
                if not self._finesse_ratio_ok(state, candidates, pick,
                                             FINESSE_RATIO, b_card=cur_str):
                    continue
            elif cur_in_flow:
                # 榜首已是该花色（正在飞）→ 尊重引擎
                pick, val, mode = cur_str, _cv(cur_str), "正在飞"
            else:
                # 榜首不是该花色 → 流程内动作，强制完成（飞张小牌≤9）。
                # 先决：队友（顶张方）该花色有牌可接应——续飞必须有人接管飞牌，
                # 队友无此花色（垫牌/将吃）则飞牌无从完成，尊重引擎。
                partner = state.dummy if leader == state.contract.declarer else state.contract.declarer
                if not any(c.suit == s for c in state.hands.get(partner, [])):
                    continue  # 队友无该花色 → 无法接应续飞
                small = [c for c in suit_cands
                         if self._FINESSE_R2V.get(c["card"][1:], 0) <= 9]
                if not small:
                    # 领出时手牌全部可打、决策候选即手牌全集——候选无该花色小牌
                    # 即手上无牌可续飞，尊重引擎
                    continue
                pick_c = min(small, key=lambda c: self._FINESSE_R2V.get(c["card"][1:], 0))
                pick = pick_c["card"]
                val = _cv(pick)
                mode = "续飞"
                # 比值退让（2026-09-12，与强制接应同款两段式）：续飞牌相对引擎
                # 榜首做成率/决策值差距悬殊（如 ♣Q 56.6% vs ♦9）→ 尊重引擎。
                if not self._finesse_ratio_ok(state, candidates, pick,
                                             FINESSE_RATIO, b_card=cur_str):
                    continue
            if best is None or val > best[0]:
                best = (val, s, obj, mode, pick)
        if best is None:
            # 所有流程均无法行动 → 尊重引擎
            full_output["领出飞牌"] = {"引发": False,
                                       "说明": "飞牌流程进行中但无可行动作，尊重引擎"}
            result["full_output"] = full_output
            return True
        val, s, obj, mode, pick = best
        if mode == "回手":
            hint = (f"[续飞回手] {s}飞牌流程进行中，顶张方领出该花色无效，"
                    f"改出无关小牌{pick}(值{val:.3f})回队友手续飞")
            print(hint)
            reasoning = result.get("reasoning", "")
            result["card"] = Card(pick[0], pick[1:])
            result["reasoning"] = f"{hint}\n{reasoning}"
            full_output["推荐出牌"] = pick
            full_output["核心逻辑"] = hint + "\n" + full_output.get("核心逻辑", "")
            full_output["飞牌续"] = {"花色": s, "原选": cur_str or "无",
                                      "改选": pick,
                                      "说明": "顶张方不领出该花色，回手队友侧飞"}
            full_output["领出飞牌"] = {"引发": True, "花色": s, "对象": obj,
                                       "领出": cur_str or "无",
                                       "说明": "飞牌流程进行中，顶张方回手整理"}
        elif mode == "正在飞":
            full_output["领出飞牌"] = {"引发": True, "花色": s, "对象": obj,
                                       "领出": cur_str,
                                       "说明": "飞牌流程进行中，继续该花色"}
        else:
            hint = (f"[续飞] {s}飞牌流程进行中（{self._finesse_obj_name(obj)}未现），"
                    f"改出{pick}完成飞牌")
            print(hint)
            reasoning = result.get("reasoning", "")
            result["card"] = Card(pick[0], pick[1:])
            result["reasoning"] = f"{hint}\n{reasoning}"
            full_output["推荐出牌"] = pick
            full_output["核心逻辑"] = hint + "\n" + full_output.get("核心逻辑", "")
            full_output["飞牌续"] = {"花色": s, "原选": cur_str or "无",
                                      "改选": pick,
                                      "说明": "飞牌流程进行中，非顶张方续飞"}
            full_output["领出飞牌"] = {"引发": True, "花色": s, "对象": obj,
                                       "领出": pick,
                                       "说明": "飞牌流程进行中，必须完成该花色"}
        result["full_output"] = full_output
        return True

    def _finesse_obj_played(self, state: PlayState, suit: str, obj: int) -> bool:
        """该花色对象大牌是否已现身（被打出/被砸落），用于判定飞牌流程是否结束。"""
        for t in state.tricks:
            for _, c in t.cards:
                if c and c.suit == suit and self._FINESSE_R2V.get(c.rank, 0) == obj:
                    return True
        for _, c in state.current_trick.cards:
            if c and c.suit == suit and self._FINESSE_R2V.get(c.rank, 0) == obj:
                return True
        return False

    def _finesse_flow_dead(self, state: PlayState, suit: str, obj: int) -> bool:
        """飞牌流程是否已无意义而应清除（双原则，2026-09-12 修正）：

        ① 对方被飞对象已现身（被打出/砸落）→ 流程终结（既有）；
        ② 己方联手现手已无高于对象的牌（上方控制张全出，对象成该花色最大，
           飞无可飞）→ 流程同样终结（如 ♦A 已出而现手只剩 ♦JT，飞 K 无意义）。
        """
        if self._finesse_obj_played(state, suit, obj):
            return True
        for pos in (state.contract.declarer, state.dummy):
            for c in state.hands.get(pos, []):
                if c.suit == suit and self._FINESSE_R2V.get(c.rank, 0) > obj:
                    return False
        return True

    def _nine_cash_done(self, state: PlayState, suit: str) -> bool:
        """9砸后阶段判定：该花色对象为 K，联手≥9张，且 A 已砸出（played 含 14）、
        K 未现。联手不足 9 张（如本例仅 7 张♦）不属于 9砸 打法（9砸=联手9张的
        砸牌路线），不得走"9砸后回手/继续飞"流程——判定依据独立于引擎，纯张数+牌面。"""
        finesse_struct = self._detect_finesse_struct(state)
        info = finesse_struct.get(suit)
        if not info or info["对象"] != 13:
            return False
        if self._combined_suit_count(state, suit) < 9:
            return False
        played = set()
        for t in state.tricks:
            for _, c in t.cards:
                if c and c.suit == suit:
                    rv = self._FINESSE_R2V.get(c.rank)
                    if rv:
                        played.add(rv)
        for _, c in state.current_trick.cards:
            if c and c.suit == suit:
                rv = self._FINESSE_R2V.get(c.rank)
                if rv:
                    played.add(rv)
        return 14 in played and 13 not in played

    def _has_finesse_reentry_high(self, state: PlayState, suit: str,
                                  pos: str, obj: int) -> bool:
        """pos（顶张端）手中是否还留有一张能"再飞"该对象的间张 g：
        g < obj（g 是对象之下的间张，真的要拿来飞 obj），
        且 g > max(敌方未出牌池 − {obj})——敌方除 obj 外没有任何牌能压住 g，
        回手后打出 g 这记稳赢。两个条件都满足才值得回手再飞；
        否则（无 g / g 非间张 / g 会被人压）回手无意义，尊重引擎。
        """
        r2v = self._FINESSE_R2V
        declarer = state.contract.declarer
        dummy = state.dummy
        present = set()
        for p in (declarer, dummy):
            for c in state.hands.get(p, []):
                if c.suit == suit:
                    present.add(r2v.get(c.rank, 0))
        for t in state.tricks:
            for _, c in t.cards:
                if c and c.suit == suit:
                    present.add(r2v.get(c.rank, 0))
        for _, c in state.current_trick.cards:
            if c and c.suit == suit:
                present.add(r2v.get(c.rank, 0))
        pool = {r for r in range(14, 1, -1) if r not in present}
        guarded = pool - {obj}  # 敌方除 obj 外还能拿来压的牌
        if not guarded:
            return False  # 敌方只剩 obj，无牌可压 → 拔顶张拿下即可，不回手
        max_def = max(guarded)
        return any(r2v.get(c.rank, 0) < obj and r2v.get(c.rank, 0) > max_def
                   for c in state.hands.get(pos, []) if c.suit == suit)

    def _cash_reentry(self, state: PlayState,
                           candidates: List[Dict[str, Any]], suit: str
                           ) -> Optional[Tuple[str, float]]:
        """9砸后回手牌选择：飞牌花色 A 已砸、K 未现 → 选无关花色小牌回队友手。

        前置：_nine_cash_done 已确认"9砸后"阶段。
        回手牌判定（基于两手牌确定性判断，不做比值）：
          找"队友稳赢"的无关花色：队友该花色最大牌 R_p >
        该花色潜在敌方最大牌 threat（= 未现于两家手牌/已出牌的最大 rank）。
          例：♠A 已出、队友持 ♠K → threat ≤ Q < K，出 ♠4 队友必赢 → 回手成立。
          在稳赢花色的候选小牌(rank≤9)中取最小牌（最小让渡，不烧间张）。
        无任何稳赢回手花色 → 返回 None，回到引擎按得分选牌。
        """
        declarer = state.contract.declarer
        dummy = state.dummy
        leader = state.current_player
        partner = dummy if leader == declarer else declarer
        played_by_suit: Dict[str, set] = {}
        for t in state.tricks:
            for _, c in t.cards:
                if c:
                    rv = self._FINESSE_R2V.get(c.rank)
                    if rv:
                        played_by_suit.setdefault(c.suit, set()).add(rv)
        for _, c in state.current_trick.cards:
            if c:
                rv = self._FINESSE_R2V.get(c.rank)
                if rv:
                    played_by_suit.setdefault(c.suit, set()).add(rv)
        # 每家手牌（按花色）
        hand_by_suit: Dict[str, Dict[str, set]] = {p: {} for p in (declarer, dummy)}
        for p in (declarer, dummy):
            for c in state.hands.get(p, []):
                hand_by_suit[p].setdefault(c.suit, set()).add(
                    self._FINESSE_R2V.get(c.rank, 0))
        # 队友最大牌 vs 敌方潜在最大牌 → 判"稳赢回手花色"
        win_leader_side = set()
        for s2, pranks in hand_by_suit[partner].items():
            if s2 == suit:
                continue  # 飞牌花色本身不用于回手
            if leader not in hand_by_suit or s2 not in hand_by_suit[leader]:
                continue  # 领出方手上无此花色牌 → 无法出
            if not any(r <= 9 for r in hand_by_suit[leader][s2]):
                continue  # 领出方此花色只剩间张/顶张（>9），打小牌会烧结构
            r_p = max(pranks)
            my_ranks = set(played_by_suit.get(s2, set()))
            for p in (declarer, dummy):
                my_ranks |= hand_by_suit[p].get(s2, set())
            absent = [r for r in range(14, 1, -1) if r not in my_ranks]
            threat = absent[0] if absent else 0
            if r_p > threat:
                win_leader_side.add(s2)
        if not win_leader_side:
            return None  # 无稳赢回手花色 → 回引擎按得分选牌
        best = None
        for c in candidates:
            cs = c.get("card", "")
            if not cs or cs[0] == suit:
                continue
            if cs[0] not in win_leader_side:
                continue  # 只选队友稳赢花色的候选
            rv = self._FINESSE_R2V.get(cs[1:], 0)
            if rv > 9:
                continue  # 只选小牌，不打其他花色顶张/间张（J/T 以上）
            val = c.get("scoring_val")
            if val is None:
                val = c.get("avg_tricks", 0.0)
            # 稳赢花色内先取最小牌（最小让渡），同 rank 取分数高
            if best is None or rv < best[2] or (rv == best[2] and val > best[1]):
                best = (cs, val, rv)
        if best is None:
            return None
        return best[0], best[1]

    def _has_high_suit_cards(self, state: PlayState, suit: str,
                             pos: str, ranks: Tuple[int, ...]) -> bool:
        """pos 手中有无该花色的指定大牌 rank（如 A/Q 顶张）。"""
        return any(self._FINESSE_R2V.get(c.rank, 0) in ranks
                   for c in state.hands.get(pos, []) if c.suit == suit)

    def _combined_suit_count(self, state: PlayState, suit: str) -> int:
        """联手（庄家+明手）该花色总张数 = 当前在手 + 我方已打出的该花色牌
        （含垫牌/跟牌/本墩已出，与 9砸判据同口径）。"""
        declarer = state.contract.declarer
        dummy = state.dummy
        cnt = sum(1 for p in (declarer, dummy)
                  for c in state.hands.get(p, []) if c.suit == suit)
        for t in state.tricks:
            for p, c in t.cards:
                if c and p in (declarer, dummy) and c.suit == suit:
                    cnt += 1
        for p, c in state.current_trick.cards:
            if c and p in (declarer, dummy) and c.suit == suit:
                cnt += 1
        return cnt

    def _nine_suit_should_garrison(self, state: PlayState, suit: str, obj: int) -> bool:
        """联手≥9 时的 9砸 判定：缺K持AQ（先砸后飞）或 缺Q持AK（双顶张齐）。"""
        declarer = state.contract.declarer
        dummy = state.dummy
        ranks = {self._FINESSE_R2V.get(c.rank)
                 for p in (declarer, dummy)
                 for c in state.hands.get(p, []) if c.suit == suit}
        has_a = 14 in ranks
        has_k = 13 in ranks
        has_q = 12 in ranks
        if obj == 13:
            return has_a and has_q  # 缺K持AQ → 先砸A
        return has_a and has_k      # 缺Q持AK → 砸

    @staticmethod
    def _percentile_int(vals: List[int], pct: float) -> int:
        """最近秩百分位（升序第 ⌊pct%·n⌋ 个，越界夹到端点）。"""
        if not vals:
            return 0
        vs = sorted(vals)
        k = int(math.floor(pct / 100.0 * len(vs)))
        k = max(0, min(len(vs) - 1, k))
        return vs[k]

    def _finesse_launch_worthwhile(self, state: PlayState, suit: str,
                                   candidates: List[Dict[str, Any]]
                                   ) -> Tuple[bool, str]:
        """启动飞牌退让门控（2026-09-10 重构，将牌不豁免）。

        决策主线：先问"榜首是否稳成"（做成率 ≥ FINESSE_NEC_MAKE_HIGH，
        不飞也成）——
          · 稳成 → 唯有"实质升级"（飞牌比榜首更好）值得启动，其余退让；
          · 非稳成 → 按 契约必要(A1/A2) → 失败安全(B) → 升级价值(C) →
                      比值尚可(D) 依次放行。
        全不满足 → 退让（尊重引擎）。探针 Δ≥阈值只是"位置敏感"信号，
        不等于"该飞"；四道闸决定是否主动改出该花色启动飞牌流程。
        返回 (是否启动, 说明)；无候选数据时不拦截。
        """
        if not candidates:
            return True, ""
        top = candidates[0]
        need = state.contract.tricks_needed
        top_scores = top.get("scores") or []
        n = len(top_scores)
        top_make = (sum(1 for x in top_scores if x >= need) / n) if n else 1.0
        stable = top_make >= FINESSE_NEC_MAKE_HIGH   # 榜首稳成：不飞也成

        def _val(c: Dict[str, Any]) -> float:
            v = c.get("scoring_val")
            return v if v is not None else c.get("avg_tricks", 0.0)

        suit_cands = [c for c in candidates
                      if c.get("card") and c["card"][0] == suit]
        if not suit_cands:
            return True, ""
        fin = max(suit_cands, key=_val)
        fin_floor = (self._percentile_int(fin.get("scores") or [], FINESSE_SAFE_PCT)
                     if fin.get("scores") else need)
        top_val = _val(top)
        fin_val = _val(fin)

        if not stable:
            # 榜首非稳成：契约/安全/比值这些"因为榜首有风险才需要替代"的判据才开放
            slack = top.get("avg_tricks", 0.0) - need
            if top_make < FINESSE_NEC_MAKE:
                return True, f"契约必要（榜首做成{top_make:.0%}，不飞没机会）"
            if slack <= FINESSE_NEC_SLACK:
                return True, f"契约必要·吃紧（盈余{slack:+.1f}）"
            if fin_floor >= need:
                return True, f"失败安全（下沿{fin_floor}≥所需{need}）"
        if fin_val > top_val:
            # 实质升级：飞牌决策值确实更高 → 唯一能穿透"榜首已稳成"的判据
            return True, f"升级价值（{fin_val:.3f}>{top_val:.3f}）"
        if (not stable and top_val > 0
                and self._finesse_ratio_ok(state, candidates, fin["card"],
                                           FINESSE_NEC_RATIO, b_card=top["card"])):
            return True, f"比值尚可（≥{FINESSE_NEC_RATIO}）"
        slack = top.get("avg_tricks", 0.0) - need
        ratio_txt = f"{fin_val / top_val:.2f}" if top_val > 0 else "—"
        return False, (f"退让（榜首做成{top_make:.0%}·盈余{slack:+.1f}已够，"
                       f"飞牌下沿{fin_floor}<{need}有险"
                       + ("" if stable else f"，比值{ratio_txt}<{FINESSE_NEC_RATIO}") + "）")

    def _probe_lead_finesse_prefer(self, state: PlayState, finesse_struct: Dict[str, Any],
                                   candidates: List[Dict[str, Any]], ratio: float,
                                   result: Dict[str, Any]) -> Optional[Tuple[str, str]]:
        """窗口期主动启动飞牌（推广自 9张"不拖延就优先"，2026-09-08）。

        探针识别出结构（Δ≥阈值）即"位置敏感"（窗口期），但不再"检测到结构
        就飞"：逐花色先过 _finesse_launch_worthwhile 退让门控（契约必要 /
        失败安全 / 升级价值 / 比值尚可，稳成线分流），不满足则退让、尊重
        引擎（2026-09-10 重建退让机制）。将牌不豁免，与边花同判据。
        返回说明携带判据与动作（如"失败安全（下沿12≥12）；动作：非顶张方
        直接飞小牌"）。
        9张及以上按砸/飞分流（应砸出顶张；应飞顶张方回手、非顶张方直飞）；
        <9张只飞不砸（8飞9砸：应飞），非顶张方直飞、顶张方无稳赢回手牌
        则不强制（尊重引擎）。
        返回 (改出牌, 说明)；不满足条件 → None。
        """
        if not FINESSE_DEFER_ENABLE:
            return None
        cur = result.get("card")
        cur_str = str(cur) if cur else ""
        leader = state.current_player

        # 引擎榜首已在任一飞牌结构花色（本侧+伙伴侧合并池）→ 尊重引擎：
        # 不得仅因 Δ 降序"跳过榜首花色"而继续尝试其他结构（如 D Δ 大、榜首
        # ♦Q 却被改 ♣3 启动草花——榜首本就是飞牌花色时，窗口期无需再启动）。
        if cur_str and any(cur_str[0] == s for s in finesse_struct):
            return None

        # 多结构并存时按 Δ 降序尝试（2026-09-10）：位置最敏感（Δ 最高）的
        # 花色最先启动；无牌可出 / 退让门控不过再依次试下一个结构。
        for s, info in sorted(
                finesse_struct.items(),
                key=lambda kv: kv[1].get("Δ") or 0.0,
                reverse=True):
            obj = info["对象"]
            if self._nine_cash_done(state, s):
                continue  # 已砸A后续流程另行处理（回手/继续飞）
            suit_cands = [c for c in candidates if c.get("card") and c["card"][0] == s]
            if not suit_cands:
                continue  # 领出方无该花色可出
            # 启动退让门控（2026-09-10）：探针识别出结构（Δ≥FINESSE_PROBE_DELTA）
            # 只是"位置敏感"信号，不等于"此刻该主动启动"。是否值得主动改出该花色
            # 由 _finesse_launch_worthwhile 判定（契约必要/失败安全/升级价值/
            # 比值尚可四道闸，稳成线分流）；不满足则退让（尊重引擎）。将牌不豁免
            # ——与边花同判据。一旦启动，流程内动作（砸顶张/回手/飞张小牌）必须
            # 完成；启动说明携带判据（如"失败安全（下沿12≥12）→非顶张方直接飞"）。
            worth, gate_why = self._finesse_launch_worthwhile(state, s, candidates)
            if not worth:
                print(f"[启动退让] {s}：{gate_why}")
                continue
            # 探针引牌直出（2026-09-11）：探针选中的引牌（Δ 最大候选）已指明
            # 出牌方向与具体牌，窗口期启动直接按引牌出，不再做顶张方回手/
            # 非顶张方直飞的二次分流——那是流程延续/9砸的规则，窗口期不适用
            # （如 ♣ 对象Q Δ0.8 引牌♣A → 直接出♣A；顶张方回手只会卡掉结构）。
            if info.get("侧") != "伙伴侧" and info.get("引牌"):
                pick = info["引牌"]
                if any(c.get("card") == pick for c in suit_cands):
                    state.finesse_flow[s] = obj
                    why = f"按探针引牌直出{pick}"
                    return pick, f"{gate_why}；动作：{why}"
            # 伙伴侧结构（v1.70 顶张侧过手，v1.72 删后语义丢失，2026-09-11 恢复）：
            # 结构是队友视角探测到的，引牌在队友手里，本侧不能直出——直接
            # 把牌权让渡给队友由其引飞（cash_reentry），不再判断本侧顶张方。
            if info.get("侧") == "伙伴侧":
                if self._nine_cash_done(state, s):
                    continue  # 9砸后回手/续飞另行处理
                partner = (state.dummy if leader == state.contract.declarer
                           else state.contract.declarer)
                if not any(c.suit == s
                           and self._FINESSE_R2V.get(c.rank, 0) < obj
                           for c in state.hands.get(partner, [])):
                    continue  # 队友无飞张小牌 → 过手后无从飞起
                reentry = self._cash_reentry(state, candidates, s)
                if not reentry:
                    continue  # 无稳赢回手牌 → 尊重引擎
                pick = reentry[0]
                state.finesse_flow[s] = obj
                why = f"过手给队友引飞（引牌{info.get('引牌', '?')}）"
                return pick, f"{gate_why}；动作：{why}"
            combined = self._combined_suit_count(state, s)
            if combined >= 9:
                if self._nine_suit_should_garrison(state, s, obj):
                    # 应砸：改出该花色最高顶张（>对象；缺K持AQ → 先砸A）
                    bank = [c for c in suit_cands
                            if self._FINESSE_R2V.get(c["card"][1:], 0) > obj]
                    if not bank:
                        continue
                    target = max(bank,
                                 key=lambda c: self._FINESSE_R2V.get(c["card"][1:], 0))
                    pick = target["card"]
                    why = "9砸优先（出顶张砸）"
                elif self._has_high_suit_cards(state, s, leader, (14, 12)):
                    # 应飞 + 顶张方：回手队友（队友稳赢接应），由队友侧飞。
                    # 回手是飞牌流程的启动动作：写入跨墩标记（存对象），
                    # 后续领出必须完成该花色飞牌，不再偏离。
                    reentry = self._cash_reentry(state, candidates, s)
                    if not reentry:
                        continue
                    pick = reentry[0]
                    why = "顶张方回手队友侧飞"
                    state.finesse_flow[s] = obj
                else:
                    # 应飞 + 非顶张方：直接出该花色最小飞张小牌（≤9）。
                    small = [c for c in suit_cands
                             if self._FINESSE_R2V.get(c["card"][1:], 0) <= 9]
                    if not small:
                        continue
                    pick = min(small,
                               key=lambda c: self._FINESSE_R2V.get(c["card"][1:], 0))["card"]
                    why = "非顶张方直接飞小牌"
                    state.finesse_flow[s] = obj
            else:
                # <9张：8飞9砸 → 只飞不砸
                if self._has_high_suit_cards(state, s, leader, (14, 12)):
                    # 顶张方（持A/Q）领出：飞需回手队友，无稳赢回手牌则不强制
                    reentry = self._cash_reentry(state, candidates, s)
                    if not reentry:
                        continue
                    pick = reentry[0]
                    why = "顶张方回手队友侧飞"
                    state.finesse_flow[s] = obj
                else:
                    small = [c for c in suit_cands
                             if self._FINESSE_R2V.get(c["card"][1:], 0) <= 9]
                    if not small:
                        continue
                    pick = min(small,
                               key=lambda c: self._FINESSE_R2V.get(c["card"][1:], 0))["card"]
                    why = "非顶张方直接飞小牌"
                    state.finesse_flow[s] = obj
            return pick, f"{gate_why}；动作：{why}"
        return None

    def _apply_eight_nine_rule(self, state: PlayState, result: Dict[str, Any],
                               ratio: float) -> Dict[str, Any]:
        """8飞9砸（通用原则，不限将牌/有将定约）。

        飞牌花色"被迫引发"（榜首为该花色牌）时的出牌原则：
          - 联手该花色张数 ≤8 → 应飞（出飞张：低于对象、≥10 的间张牌）
          - 联手张数 ≥9 且 AK（14/13）都在我方庄家/明手 → 应砸（出顶张：高于对象的 A/K）
          - 9 张缺K 但持 A+Q → 先砸后飞（拔A砸，K未落再飞Q）
          - 9 张但顶张不足（缺Q/J 且 A/K 缺一）→ 砸不动对象，仍应飞
        用比值阈值保护（FINESSE_RATIO）：改选牌相对成功率 ≥ 榜首才改选。
        仅当榜首是飞牌花色牌时介入；榜首为其他花色（接应方未领该花色）不干预。
        """
        if not FINESSE_EIGHT_NINE_ENABLE:
            return result
        finesse_struct = self._detect_finesse_struct(state, result)
        if not finesse_struct:
            return result
        full_output = result.get("full_output", {})
        mcts_stats = full_output.get("mcts_stats") or {}
        candidates = mcts_stats.get("candidates") or []
        if len(candidates) < 2:
            return result
        # 以"当前实际决策牌"为准：已被改为其他花色，则不介入8飞9砸
        cur_card = result.get("card")
        cur_str = str(cur_card) if cur_card else ""
        if not cur_str or cur_str[0] not in finesse_struct:
            return result  # 当前决策牌已非结构牌 → 不介入8飞9砸
        suit = cur_str[0]
        top = next((c for c in candidates if c.get("card") == cur_str), None)
        if top is None:
            return result
        top_card = cur_str
        top_val = top.get("scoring_val")
        if top_val is None:
            top_val = top.get("avg_tricks", 0.0)
        if top_val <= 0:
            return result
        obj = finesse_struct[suit]["对象"]
        declarer = state.contract.declarer
        dummy = state.dummy
        own_cards = [c for pos in (declarer, dummy)
                     for c in state.hands.get(pos, []) if c.suit == suit]
        # 联手张数按"初始总数"结算（用户语义 2026-09-03 修正）：
        #  初始联手数 = 当前在手 + 我方已打出的该花色牌（含垫牌/跟牌/本墩已出）。
        #  垫牌不算"处理该花色"——9砸判据基于初始联手张数，垫掉一张不减少总数；
        #  "A已砸后不再9砸"由 has_a 天然拦截（A 已出 → has_a=False → 误砸自动失效）。
        own_played = 0
        for t in state.tricks:
            for p, c in t.cards:
                if c and p in (declarer, dummy) and c.suit == suit:
                    own_played += 1
        for p, c in state.current_trick.cards:
            if c and p in (declarer, dummy) and c.suit == suit:
                own_played += 1
        trump_cnt = len(own_cards) + own_played
        own_ranks = {self._FINESSE_R2V.get(c.rank) for c in own_cards}
        has_a = 14 in own_ranks
        has_k = 13 in own_ranks
        has_q = 12 in own_ranks
        ak_ok = has_a and has_k  # A+K 都在我方（庄家/明手）才算"双顶张齐"
        # 9砸判据（联手 ≥9 张）：
        #  缺K（对象=K）：持 A+Q → "先砸后飞"（拔A砸，K未落再飞Q），无需K
        #  缺Q/J：需 A+K 全顶张才砸；AK缺一砸不动对象，仍应飞
        if obj == 13:
            should_garrison = trump_cnt >= 9 and has_a and has_q
        else:
            should_garrison = trump_cnt >= 9 and ak_ok
        top_val = top.get("scoring_val")
        if top_val is None:
            top_val = top.get("avg_tricks", 0.0)
        if top_val <= 0:
            return result
        top_rv = self._FINESSE_R2V.get(top_card[1:], 0)
        targets = {
            "card": None, "val": -1.0, "why": "", "ak": ak_ok
        }
        for c in candidates:
            cs = c.get("card", "")
            if not cs or cs[0] != suit:
                continue
            rv = self._FINESSE_R2V.get(cs[1:], 0)
            val = c.get("scoring_val")
            if val is None:
                val = c.get("avg_tricks", 0.0)
            if val <= 0:
                continue
            # 9砸是确定的打法规则（联手≥9张缺K持AQ必先砸A），不受比值软保护限制；
            # 比值保护只用于"8飞"（改飞张属软干预，统一两段式比值退让：做成率优先/决策值兜底）。
            if not should_garrison and not self._finesse_ratio_ok(
                    state, candidates, cs, ratio, b_card=cur_str):
                continue
            if should_garrison:
                # 9砸：候选里"顶张"（>对象）取代榜首"飞张"（低于对象、≥10）
                if rv > obj and 10 <= top_rv < obj and val > targets["val"]:
                    # 缺K持AQ（AK不齐）：先砸A再飞Q（先砸后飞）
                    why = "9砸先飞" if (obj == 13 and not ak_ok) else "9砸"
                    targets = {"card": cs, "val": val, "why": why, "ak": ak_ok}
            else:
                # 8飞：候选里"飞张"（低于对象、≥10）取代榜首"砸张"（>对象）
                if 10 <= rv < obj and top_rv > obj and val > targets["val"]:
                    targets = {"card": cs, "val": val, "why": "8飞", "ak": ak_ok}
        if not targets["card"]:
            return result
        pick = Card(targets["card"][0], targets["card"][1:])
        obj_name = self._finesse_obj_name(obj)
        if targets["why"] == "9砸先飞":
            ak_note = "（缺K持AQ：先砸A再飞Q）"
        else:
            ak_note = "" if ak_ok else "（AK不齐，只能飞）"
        if should_garrison:
            # 9砸为规则优先，不显示（可能<阈值的）比值，避免误导
            ratio_note = "（9砸为确定打法，规则优先）"
        else:
            ratio_note = f"，比值{targets['val']/top_val:.3f}≥{ratio}"
        hint = (f"[8飞9砸] {suit}缺{obj_name} 联手{trump_cnt}张应{targets['why']}{ak_note}: "
                f"榜首{top_card}({top_val:.3f}) → 改选{targets['card']}({targets['val']:.3f}){ratio_note}")
        print(hint)
        reasoning = result.get("reasoning", "")
        result["card"] = pick
        result["reasoning"] = f"{hint}\n{reasoning}"
        full_output["推荐出牌"] = targets["card"]
        full_output["核心逻辑"] = hint + "\n" + full_output.get("核心逻辑", "")
        # 9砸改选成功后，清除接应逻辑残留的"强制出Q"提示，避免界面自相矛盾
        full_output.pop("飞牌接应", None)
        full_output["八九原则"] = {"花色": suit, "缺": obj_name, "联手张数": trump_cnt,
                                    "AK齐全": ak_ok, "原则": targets["why"],
                                    "榜首": top_card, "改选": targets["card"]}
        return result

    def _finesse_commit_check(self, state: PlayState,
                              finesse_struct: Dict[str, Any]) -> Optional[Tuple[str, str]]:
        """强制接应飞牌：当前墩同伙（庄家/明手方）已在飞牌花色启动，
        本家必须按规则接应（盖/跟/飞），不得拔顶张烧掉进手。

        判定条件（全部满足才强制）：
          ① 当前墩已出牌中，同伙出了飞牌花色 S 的牌（rank < 对象）
          ② 当前出牌方属于庄家/明手方
          ③ 出牌方手中有 S 花色的合法跟牌

        接应选牌规则（2026-09-08 改为按"剩余牌 + 已出牌"完整判定，不再用 10 分界）：
          - 对象大牌已现身（被拿下/打出）→ 飞牌已结束，不贴小牌，尊重引擎兑现
          - 敌方本墩已出 ≥对象 → 用最小的高于对象的顶张盖掉
          - 敌方未出对象、对象未现：
            威胁 = 敌方剩余牌中除对象外的最大牌（全部牌面 − 我方庄/明现手 − 已出）。
            - 同伙引牌 > 威胁 → 引牌一方可赢，本家出最小牌保留结构（不烧高间张）
            - 否则 → 出大过威胁的最小牌（第三家打大牌，保住本墩）；
              无牌可压威胁 → 尊重引擎
        返回 (接应牌, 压制说明)；不满足返回 None。
        """
        trick = getattr(state, "current_trick", None)
        if not trick or not trick.cards or not finesse_struct:
            return None
        declarer = state.contract.declarer
        dummy = state.dummy
        turn = state.current_player
        if turn not in (declarer, dummy):
            return None
        fs_suits = set(finesse_struct.keys())
        partner = PARTNERS.get(turn, "")
        launch = None
        for p, c in trick.cards:
            if p != partner or c is None or c.suit not in fs_suits:
                continue
            rv = self._FINESSE_R2V.get(c.rank)
            if rv is not None and rv < finesse_struct[c.suit]["对象"]:
                launch = (c.suit, rv)
                break
        if not launch:
            return None
        suit, partner_rv = launch
        obj = finesse_struct[suit]["对象"]
        hand = state.hands.get(turn, [])
        playable = state.get_playable_cards(turn)
        if not playable:
            return None
        suit_cards = [c for c in playable if c.suit == suit]
        if not suit_cards:
            return None
        enemy_top = max(
            (self._FINESSE_R2V[c.rank] for p, c in trick.cards
             if p not in (partner, turn) and c and c.suit == suit),
            default=-1,
        )
        covers = [c for c in suit_cards if self._FINESSE_R2V[c.rank] > obj]
        below = [c for c in suit_cards if self._FINESSE_R2V[c.rank] < obj]
        if enemy_top >= obj:
            # 敌方本墩已出对象 → 用最小顶张盖（此时对象"现身"是盖牌动作，必须处理）
            if not covers:
                return None
            pick = min(covers, key=lambda c: self._FINESSE_R2V[c.rank])
            return str(pick), f"盖{self._finesse_obj_name(obj)}"
        # 对象在历史墩已现身（被拿下/打出）→ 飞牌已完成，不贴小牌作伪接应，
        # 尊重引擎兑现。须在盖分支之后检查——当前墩对象已在上面处理。
        if self._finesse_obj_played(state, suit, obj):
            return None
        if not below:
            return None
        # 敌方剩余牌（该花色未现者 = 全部牌面 − 我方庄/明现手 − 本墩已出 −
        # 已完成墩已出），即敌方两家手中还可能打出的牌。威胁 = 其中除对象外最大者。
        r2v = self._FINESSE_R2V
        present = set()
        for p in (declarer, dummy):
            for c in state.hands.get(p, []):
                if c.suit == suit:
                    present.add(r2v.get(c.rank, 0))
        for t in state.tricks:
            for _, c in t.cards:
                if c and c.suit == suit:
                    present.add(r2v.get(c.rank, 0))
        for _, c in trick.cards:
            if c and c.suit == suit:
                present.add(r2v.get(c.rank, 0))
        guarded = [r for r in range(14, 1, -1)
                   if r not in present and r != obj]
        threat = max(guarded) if guarded else 0
        # 第三家接应判定（不再用 10 分界，2026-09-08）：
        #   同伙引牌已大过敌方全部非对象剩余 → 引牌一方可赢，本家出最小牌保留结构；
        #   否则须出大过敌方最大威胁的最小牌（第三家打大牌，保住本墩）。
        if partner_rv > threat:
            pick = min(suit_cards, key=lambda c: r2v[c.rank])
            return str(pick), f"引牌已胜，最小跟"
        above_threat = [c for c in suit_cards if r2v[c.rank] > threat]
        if not above_threat:
            return None  # 本家无牌可压威胁 → 尊重引擎
        pick = min(above_threat, key=lambda c: r2v[c.rank])
        block = max((c for c in suit_cards if r2v[c.rank] > obj),
                    key=lambda c: r2v[c.rank], default=None)
        return str(pick), str(block) if block else str(pick)

    def _apply_finesse_commit(self, state: PlayState, result: Dict[str, Any],
                              finesse_struct: Dict[str, Dict[str, Any]],
                              ratio: float = FINESSE_RATIO) -> Tuple[Dict[str, Any], bool]:
        """在 DD/αμ 搜索结果上应用强制接应飞牌；返回 (result, 是否强制执行)。

        结构判定与 _finesse_commit_check 共用同一传入 finesse_struct——不内部
        二次检测（2026-09-09 修复）：此前内部重新 _detect_finesse_struct，
        把调用方已确认的结构静默丢弃，接应（威胁比较制算出的最小飞张）被
        吞掉、回退引擎。现在两个函数同一口径。（结构来源只有当墩探针——
        flow 补构已于 2026-09-09 撤销，可飞性校验于同日删除，跟牌严格只信探针。）

        接应是飞牌流程内的强制动作：同伙已在飞牌花色启动（当前墩出了该花色
        小牌/间张），本家必须按"盖/跟/飞"规则接应——流程一旦启动必须完成
        （与领出续飞/回手同口径）。尊重引擎的途径（2026-09-09 起）：
        ① 接应流程选不出牌（_finesse_commit_check 返回 None）；
        ② 强制接应比值退让（2026-09-12 加入）：从引擎候选取"强制牌 vs 榜首"
        的决策值，强制牌明显差于榜首（比值 < FINESSE_RATIO）时尊重引擎——
        接应贴小牌是流程内动作，但引擎榜首若 100% 而强制牌 0% 时不能硬推。
        """
        if not FINESSE_DEFER_ENABLE:
            return result, False
        if not finesse_struct:
            return result, False
        forced = self._finesse_commit_check(state, finesse_struct)
        if not forced:
            return result, False
        flyer_str, block_str = forced
        if not self._finesse_commit_ratio_ok(state, result, flyer_str, ratio):
            return result, False
        flyer = Card(flyer_str[0], flyer_str[1:])
        struct_desc = "、".join(
            f"{s}(" + self._finesse_obj_name(finesse_struct[s]["对象"]) + ")" for s in finesse_struct
        )
        hint = (f"[飞牌接应] 同伙已在 {struct_desc} 启动飞牌，必须出 {flyer_str} 完成飞牌"
                f"（压制拔 {block_str} 烧进手）")
        print(hint)
        full_output = result.get("full_output", {})
        result["card"] = flyer
        result["reasoning"] = f"{hint}\n{result.get('reasoning', '')}"
        full_output["推荐出牌"] = flyer_str
        full_output["核心逻辑"] = hint + "\n" + full_output.get("核心逻辑", "")
        full_output["飞牌接应"] = {"结构": struct_desc, "启动花色": flyer_str[0],
                                    "强制出": flyer_str, "压制": block_str, "说明": "同伙已启动飞牌，必须接应"}
        return result, True

    def _finesse_commit_ratio_ok(self, state: PlayState, result: Dict[str, Any],
                                 forced_card: str, ratio: float) -> bool:
        """强制接应比值退让判据：委托统一两段式 _finesse_ratio_ok。"""
        cands = ((result.get("full_output") or {}).get("mcts_stats") or {}).get("candidates") or []
        if not cands:
            return True
        return self._finesse_ratio_ok(state, cands, forced_card, ratio)

    def _finesse_ratio_ok(self, state: PlayState, candidates: List[Dict[str, Any]],
                          a_card: str, ratio: float,
                          b_card: Optional[str] = None) -> bool:
        """比值退让统一判据：做成率优先、决策值兜底（三处飞牌干预共用）。

        段1 做成率（success_rate / scores 相对所需墩达成占比，双方可算且参照>0）：
            比值 = 动作牌达成率 / 参照达成率，< ratio 退让（尊重引擎）；
            参照制成率≤0（双方都无法成约）时进入段2，避免二值失真。
        段2 决策值（scoring_val → avg_tricks）：比值 < ratio 退让。
        无数据 / 参照≤0 / 动作≥参照 → 不干预（维持动作）。
        返回 True=差距可接受（维持动作）；False=退让、尊重引擎。
        """
        def _make(c: Dict[str, Any]) -> Optional[float]:
            sr = c.get("success_rate")
            if sr is not None:
                return float(sr)
            scores = c.get("scores")
            if not scores:
                return None
            need = state.contract.tricks_needed
            return sum(1 for s in scores if s >= need) / len(scores)

        def _val(c: Dict[str, Any]) -> float:
            v = c.get("scoring_val")
            if v is not None:
                return float(v)
            a = c.get("avg_tricks")
            if a is not None:
                return float(a)
            s = c.get("scores")
            if s:
                return sum(s) / len(s)
            return 0.0

        a = next((c for c in candidates if str(c.get("card")) == a_card), None)
        if a is None:
            return True
        # 段1：做成率优先
        am = _make(a)
        if am is not None:
            ref_m = None
            if b_card is not None:
                bc = next((c for c in candidates if str(c.get("card")) == b_card), None)
                ref_m = _make(bc) if bc is not None else None
            if ref_m is None:
                pairs = [(_make(c), c) for c in candidates if _make(c) is not None] or []
                ref_m = max((p[0] for p in pairs), default=None)
            if ref_m is not None and ref_m > 0:
                if am >= ref_m:
                    return True
                return (am / ref_m) >= ratio
        # 段2：决策值兜底
        av = _val(a)
        bv = None
        if b_card is not None:
            bc = next((c for c in candidates if str(c.get("card")) == b_card), None)
            bv = _val(bc) if bc is not None else None
        if bv is None:
            bv = max((_val(c) for c in candidates), default=0.0)
        if bv <= 0 or av >= bv:
            return True
        return (av / bv) >= ratio

    def _dd_play(self, state: PlayState, dd_samples: int = None, dd_scoring_mode: str = None) -> Dict[str, Any]:
        """DD搜索打牌（纯蒙特卡洛 + 双明手评估，由asyncio.to_thread调用）"""
        constraints = self._get_bid_constraints()
        if constraints:
            print(f"[DD] 约束已应用: {len(constraints)}家, { {p: f'HCP[{c.min_hcp}-{c.max_hcp}] suits={c.suit_min}' for p, c in constraints.items()} }")
            self._apply_constraints(constraints)
        else:
            print(f"[DD] 无约束 (bid_history={'空' if not self.bid_history else repr(self.bid_history[:80])})")

        # Phase 0a: DD 样本数由粒子设置 API 或 DD_NUM_SAMPLES 控制
        # 请求级 dd_samples 允许临时覆盖（用完恢复）
        _saved_num_samples = self.dd_search.num_samples
        if dd_samples is not None:
            self.dd_search.num_samples = dd_samples
        # 请求级 dd_scoring_mode 允许临时覆盖计分制（用完恢复）
        _saved_scoring_mode = self.dd_search.scoring_mode
        if dd_scoring_mode is not None:
            self.dd_search.scoring_mode = dd_scoring_mode

        try:
            result = self.dd_search.search(state)
            card = result.get("card")
            if card is None:
                playable = self.engine.get_playable_cards()
                card = self._select_best_card(playable, state)
            full_output = result.get("full_output", {})
            full_output["叫牌约束"] = self._format_constraints_for_display(constraints)
            full_output["最新约束"] = self._format_latest_constraints_for_display(state, constraints)
            self._inject_played_stats(full_output, state)
            full_output["engine_phase"] = "midgame_dd"
            # 飞牌特殊处理（独立于引擎的统一管线，传入 DD 比值）。
            # DD 单独开关（运行时切换，不影响 αμ）：DD_FINESSE_ENABLE=False 时
            # DD 引擎不带任何飞牌管理——窗口期启动/接应/流程/8飞9砸全不介入，
            # 仅按引擎得分选牌。
            import config as _svc_config
            if _svc_config.DD_FINESSE_ENABLE:
                result = self._apply_finesse_tactics(state, result, FINESSE_RATIO)
            card = result.get("card")
            return {
                "card": card.to_dict() if card else None,
                "reasoning": result.get("reasoning", ""),
                "full_output": full_output,
                "prompt": "[DD] no prompt",
            }
        except Exception as e:
            playable = self.engine.get_playable_cards()
            card = self._select_best_card(playable, state)
            return {
                "card": card.to_dict() if card else None,
                "reasoning": f"DD异常，自动选择: {str(e)}",
                "error": str(e),
                "prompt": "[DD error]",
            }
        finally:
            if dd_samples is not None:
                self.dd_search.num_samples = _saved_num_samples
            if dd_scoring_mode is not None:
                self.dd_search.scoring_mode = _saved_scoring_mode

    def _perfect_play(self, state: PlayState) -> Dict[str, Any]:
        """完美DD打牌（全知双明手，无采样，一次 solve_board 得所有候选精确分）"""
        constraints = self._get_bid_constraints()
        try:
            result = self.dd_search.search_perfect(state)
            card = result.get("card")
            if card is None:
                playable = self.engine.get_playable_cards()
                card = self._select_best_card(playable, state)
            full_output = result.get("full_output", {})
            full_output["叫牌约束"] = self._format_constraints_for_display(constraints)
            full_output["最新约束"] = self._format_latest_constraints_for_display(state, constraints)
            self._inject_played_stats(full_output, state)
            return {
                "card": card.to_dict() if card else None,
                "reasoning": result.get("reasoning", ""),
                "full_output": full_output,
                "prompt": "[DD·完美] no prompt",
            }
        except Exception as e:
            playable = self.engine.get_playable_cards()
            card = self._select_best_card(playable, state)
            return {
                "card": card.to_dict() if card else None,
                "reasoning": f"完美DD异常，自动选择: {str(e)}",
                "error": str(e),
                "prompt": "[DD·完美 error]",
            }

    def _format_hands_info(self, state: PlayState) -> str:
        lines = []
        
        card_str = " ".join(str(c) for c in state.hands.get(state.current_player, []))
        lines.append(f"**你的手牌({state.current_player})**: {card_str}")
        
        # 判断明手是否已摊牌（首攻阶段明手不可见）
        dummy_visible = state.phase != PlayPhase.LEAD
        
        declarer = state.contract.declarer
        dummy = state.dummy
        declarer_partner = PARTNERS.get(declarer, "")
        is_declarer_side = state.current_player in (declarer, declarer_partner)
        
        if is_declarer_side and dummy:
            # 庄家方视角：显示庄家和明手两家（庄家始终能看到明手，因为首攻者不是庄家方）
            if state.current_player != declarer:
                declarer_cards = " ".join(str(c) for c in state.hands.get(declarer, []))
                lines.append(f"**庄家({declarer})**: {declarer_cards}")
            if state.current_player != dummy:
                dummy_cards = " ".join(str(c) for c in state.hands.get(dummy, []))
                lines.append(f"**明手({dummy})**: {dummy_cards}")
        elif dummy and dummy_visible:
            # 防守方视角：首攻时看不到明手，首攻后可以看到明手
            dummy_cards = " ".join(str(c) for c in state.hands.get(dummy, []))
            lines.append(f"**明手({dummy})**: {dummy_cards}")
        
        return "\n".join(lines)
    
    def _format_completed_tricks(self, state: PlayState) -> str:
        if not state.tricks:
            return "无"
        
        lines = []
        for i, trick in enumerate(state.tricks, 1):
            cards_str = " ".join(f"({pos}){card}" for pos, card in trick.cards)
            winner = trick.winner()
            leader = trick.cards[0][0] if trick.cards else "?"
            lines.append(f"第{i}墩[领出:{leader}]: {cards_str} - 赢家: {winner}")
        
        return "\n".join(lines)
    
    def _format_current_trick(self, state: PlayState) -> str:
        if not state.current_trick.cards:
            return "尚未开始（你是本墩领出者）"
        
        leader = state.current_trick.cards[0][0]
        cards_str = " ".join(f"({pos}){card}" for pos, card in state.current_trick.cards)
        return f"[领出:{leader}] {cards_str}"
    
    def _format_played_cards_info(self, state: PlayState) -> str:
        """格式化已见牌张与花色轮次信息"""
        all_suits = ["♠", "♥", "♦", "♣"]
        all_ranks = ["A", "K", "Q", "J", "T", "9", "8", "7", "6", "5", "4", "3", "2"]
        
        # 收集所有已出过的牌
        played_cards = {suit: [] for suit in all_suits}
        for trick in state.tricks:
            for pos, card in trick.cards:
                if card.suit in played_cards:
                    played_cards[card.suit].append(card.rank)
        for pos, card in state.current_trick.cards:
            if card.suit in played_cards:
                played_cards[card.suit].append(card.rank)
        
        # 统计每门花色已出轮次
        suit_rounds = {}
        for suit in all_suits:
            suit_rounds[suit] = len(played_cards[suit]) // 1  # 每张牌代表出了一次
        
        lines = []
        for suit in all_suits:
            seen = played_cards[suit]
            unseen = [r for r in all_ranks if r not in seen]
            rounds = len(seen)
            if seen:
                lines.append(f"- {suit}: 已出{rounds}张，已见{'/'.join(seen)}，未见{'/'.join(unseen)}")
            else:
                lines.append(f"- {suit}: 未出过")
        
        return "\n".join(lines)
    
    def _check_trump_cleared(self, state: PlayState) -> str:
        """检查将牌是否已清完"""
        if state.contract.suit == "NT":
            return "不适用（无将定约）"
        
        trump = state.contract.suit
        # 统计已出的将牌数
        played_trumps = 0
        for trick in state.tricks:
            for pos, card in trick.cards:
                if card.suit == trump:
                    played_trumps += 1
        for pos, card in state.current_trick.cards:
            if card.suit == trump:
                played_trumps += 1
        
        # 检查防守方和庄家方手中是否还有将牌
        declarer = state.contract.declarer
        dummy = state.dummy
        defender1 = [p for p in POSITION_ORDER if p not in (declarer, dummy, PARTNERS.get(declarer, ""))][0] if len(POSITION_ORDER) > 3 else ""
        defender2 = PARTNERS.get(defender1, "")
        
        # 检查可见手牌中是否还有将牌
        remaining_trumps_in_defenders = 0
        for pos in [defender1, defender2]:
            if pos in state.hands:
                for card in state.hands[pos]:
                    if card.suit == trump:
                        remaining_trumps_in_defenders += 1
        
        # 庄家方手中的将牌
        remaining_trumps_in_declarer = 0
        for pos in [declarer, dummy]:
            if pos in state.hands:
                for card in state.hands[pos]:
                    if card.suit == trump:
                        remaining_trumps_in_declarer += 1
        
        if remaining_trumps_in_defenders == 0 and remaining_trumps_in_declarer == 0:
            return "是"
        elif remaining_trumps_in_defenders == 0:
            return "庄家方仍有将牌"
        else:
            return "否"
    
    def _parse_card_from_str(self, card_str: str, playable: List[Card]) -> Optional[Card]:
        if not card_str:
            return None
        
        card_str = card_str.strip().upper()
        
        for card in playable:
            if str(card).upper() == card_str:
                return card
            if f"{card.suit}{card.rank}" == card_str:
                return card
        
        matches = re.findall(r'([♠♥♦♣])([AKQJT98765432])', card_str)
        for suit, rank in matches:
            for card in playable:
                if card.suit == suit and card.rank == rank:
                    return card
        
        return None

    def _validate_and_fallback(self, card: Card, playable: List[Card],
                                state: PlayState) -> Tuple[Card, str]:
        """LLM 输出校验 + 回退。

        校验 LLM 推荐的牌是否合法且合理。
        - critical/error 级别：强制替换为规则推荐牌
        - warning 级别：仅记录警告，使用LLM原选择
        - info/通过：正常使用

        Returns:
            (最终选定的牌, 校验警告消息)
        """
        try:
            from bridge.mcts.llm_validator import validate_llm_play, suggest_rule_based_play
            validation = validate_llm_play(card, playable, state)

            if validation.valid:
                return card, ""

            severity = validation.severity
            warning = f"[规则校验:{severity}] {validation.violation}"

            if severity in ("critical", "error"):
                # 严重错误，必须纠正
                if validation.suggested_card and any(c == validation.suggested_card for c in playable):
                    fallback_card = validation.suggested_card
                else:
                    fallback_card = suggest_rule_based_play(playable, state)
                msg = f"LLM推荐{card}触发{severity}级规则: {validation.violation}，自动纠正为{fallback_card}"
                print(f"[校验] {msg}")
                return fallback_card, msg
            else:
                # warning 级别，仅警告但使用原选择（可能是战术性选择）
                print(f"[校验] {warning} (保留LLM选择{card})")
                return card, warning
        except Exception as e:
            import traceback
            print(f"[校验] 校验器异常: {e}")
            traceback.print_exc()
            return card, ""

    def _select_best_card(self, playable: List[Card], state: PlayState) -> Card:
        """基于规则的选牌，用于LLM不可用时的回退。"""
        try:
            from bridge.mcts.llm_validator import suggest_rule_based_play
            return suggest_rule_based_play(playable, state)
        except Exception:
            # 降级为简单最小牌策略
            if len(playable) == 1:
                return playable[0]
            if state.current_trick.cards:
                lead_suit = state.current_trick.get_lead_suit()
                same_suit = [c for c in playable if c.suit == lead_suit]
                if same_suit:
                    return min(same_suit, key=lambda c: c.rank_value)
            return min(playable, key=lambda c: (c.suit_order, c.rank_value))