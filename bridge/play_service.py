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
    ALPHA_MU_ENABLE, ALPHA_MU_ENDGAME_CARDS, ALPHA_MU_NUM_WORLDS,
    ALPHA_MU_MAX_DEPTH, ALPHA_MU_TIME_LIMIT, ALPHA_MU_M,
    FINESSE_DEFER_ENABLE, FINESSE_EIGHT_NINE_ENABLE,
    FINESSE_RATIO, FINESSE_NEC_MAKE, FINESSE_NEC_MAKE_HIGH,
    FINESSE_NEC_MIN_RATIO, FINESSE_NEC_RATIO,
    FINESSE_COMMIT_DIE_PCT, FINESSE_COMMIT_ALIVE_PCT,
    DD_MAJORITY_VOTES,
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
        # 世界/样本生成统一走 dd_search._generate_worlds（DD 与 αμ 共用）：
        # 残局→完备枚举、不可行/非残局→sampler.sample_n() 均匀采样。
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
        # DD 多数投票票数（运行时可由粒子设置 API 修改；默认 1=关闭）
        self.dd_majority_votes = DD_MAJORITY_VOTES
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
                          dd_samples: int = None,
                          dd_scoring_mode: str = None,
                          amu_worlds: int = None,
                          amu_m: int = None) -> Dict[str, Any]:
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

        # P0-6 修复：DDS 库不可用时，依赖双明手的引擎（DD/完美DD/αμ）
        # 统一降级为规则选牌并明确提示，
        # 避免 DLL 缺失时静默"选第一张牌"或抛异常导致整局卡死
        if use_perfect or use_dd or use_alphamu:
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
            return await asyncio.to_thread(self._alpha_mu_play, state, amu_worlds, amu_m)

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
- [AI] 行：**一律不转译**——含义是AI模拟补全（如截屏牌局用新睿二盖一模拟人类叫牌补全），非叫牌阶段真实产物，不可信，不得进入约束；无论自然叫还是约定叫（含扣叫/4NT-5NT/斯泰曼等）都不提取，constraint 输出空字符串。
- [AI] 行不参与 pass 负面推断。

转译规则：
1. 每个叫品：从其"含义"提取公开承诺。含义明确给出的点力区间/花色张数/牌型必须转写；含义未提及的不写；不确定一律不写。
2. HCP 段必须是该叫品对**本家个人大牌点（HCP）**的承诺。含义中"联手点力/联手至少X点/合计X点"表示己方两人总点力：
   - [XR]/[JF] 来源（非AI，约定含义可靠）：若含义明确给出联手下限 X 且含义中已注明同伴的 HCP 区间，可推导本家下限 = X − 同伴区间上限，写成个人 HCP（例：同伴 2NT=20-21、含义"联手≥37点"→ 本家 HCP16+）；同伴区间未知或无法推导时，HCP 段留空。
   - [AI] 来源：一律禁止推导，HCP 段留空（且按来源过滤规则[AI]行整体不转译，此处为冗余兜底）。
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

    def parse_constraints_text(self, text: str) -> Dict[str, BidConstraint]:
        """解析用户在"确认定约与首攻"弹窗手动编辑的约束文本。

        _format_constraints_for_display 的逆过程，一行一个位置，格式示例：
            南: HCP 12-14 均型 ♠≥5
            西: HCP ≤10 ♥≥5 ♠≤3
            北: ♠=4 必持:♠A,♥K ≥2控
        支持 HCP 范围/≥/≤、均型/非均型、♠≥n/♠≤n/♠=n/♠2-4、
        ≥n控、必持:♠A,♥K；来源标记（[约定] 等）与无法识别的 token 忽略；
        无位置名的行忽略；无任何有效字段的位置排除（=该家无约束）。
        """
        constraints: Dict[str, BidConstraint] = {}
        suit_alias = {"S": "♠", "H": "♥", "D": "♦", "C": "♣"}

        def norm_suit(ch: str) -> str:
            return suit_alias.get(ch, ch)

        for line in text.splitlines():
            line = line.strip()
            if not line:
                continue
            pos = None
            body = None
            for p in ("南", "北", "东", "西"):
                if line.startswith(p + ":"):
                    pos = p
                    body = line[len(p) + 1:].strip()
                    break
            if pos is None or not body:
                continue
            c = BidConstraint(position=pos, inference_source="manual")
            changed = False
            cleaned = body.replace("，", " ").replace("；", " ").replace(",", " ")
            tokens = cleaned.split()
            i = 0
            while i < len(tokens):
                tok = tokens[i]
                if tok.startswith("HCP"):
                    rest = tokens[i + 1] if i + 1 < len(tokens) else ""
                    m = re.match(r"^(\d{1,2})\s*-\s*(\d{1,2})$", rest)
                    if m:
                        lo, hi = int(m.group(1)), int(m.group(2))
                        c.min_hcp = lo if c.min_hcp is None else max(c.min_hcp, lo)
                        c.max_hcp = hi if c.max_hcp is None else min(c.max_hcp, hi)
                        changed = True
                        i += 1
                    else:
                        m = re.match(r"^≥\s*(\d{1,2})$", rest)
                        if m:
                            v = int(m.group(1))
                            c.min_hcp = v if c.min_hcp is None else max(c.min_hcp, v)
                            changed = True
                            i += 1
                        else:
                            m = re.match(r"^≤\s*(\d{1,2})$", rest)
                            if m:
                                v = int(m.group(1))
                                c.max_hcp = v if c.max_hcp is None else min(c.max_hcp, v)
                                changed = True
                                i += 1
                elif tok in ("均型", "非均型"):
                    c.balanced = (tok == "均型")
                    changed = True
                elif tok.endswith("控"):
                    m = re.match(r"^≥\s*(\d{1,2})$", tok[:-1])
                    if m:
                        v = int(m.group(1))
                        c.min_controls = v if c.min_controls is None else max(c.min_controls, v)
                        changed = True
                elif tok.startswith("必持:"):
                    items = tok[len("必持:"):]
                    for item in re.split(r"[,，]", items):
                        m = re.match(r"^([♠♥♦♣SHDC])\s*((?:10)|[AKQJT])$", item)
                        if m:
                            c.specific_cards.add((norm_suit(m.group(1)), m.group(2)))
                            changed = True
                elif re.match(r"^[♠♥♦♣SHDC]", tok):
                    s = norm_suit(tok[0])
                    rest = tok[1:]
                    if rest.startswith("≥"):
                        v = int(rest[1:])
                        c.suit_min[s] = max(c.suit_min.get(s, 0), v)
                        changed = True
                    elif rest.startswith("≤"):
                        v = int(rest[1:])
                        c.suit_max[s] = v if s not in c.suit_max else min(c.suit_max[s], v)
                        changed = True
                    else:
                        m = re.match(r"^(\d{1,2})\s*-\s*(\d{1,2})$", rest)
                        if m:
                            c.suit_min[s] = max(c.suit_min.get(s, 0), int(m.group(1)))
                            c.suit_max[s] = int(m.group(2))
                            changed = True
                        else:
                            m = re.match(r"^=\s*(\d{1,2})$", rest)
                            if m:
                                c.exact_suit[s] = int(m.group(1))
                                changed = True
                            else:
                                m = re.match(r"^(?:(10)|[AKQJT])$", rest)
                                if m:
                                    c.specific_cards.add((s, m.group(0)))
                                    changed = True
                i += 1
            if changed:
                constraints[pos] = c
        return constraints

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
        # 约束总开关（运行时切换）：关闭后全部引擎按无约束均匀采样，
        # 不管有没有 payload/含义文本（config.DD_USE_CONSTRAINTS 即时生效）
        import config as _cfg
        if not _cfg.DD_USE_CONSTRAINTS:
            return {}

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

    def _alpha_mu_play(self, state: PlayState,
                       amu_worlds: Optional[int] = None,
                       amu_m: Optional[int] = None) -> Dict[str, Any]:
        """αμ 引擎（论文实现，纯αμ无回退）。

        M 值由 ALPHA_MU_M 配置（默认 2），全程不降级。
        注意：牌数多时 M=2 会非常慢（13 张牌约 30s+），研究用途可接受。
        请求级 amu_worlds/amu_m：临时覆盖搜索器配置（用完恢复），
        与 _dd_play 的 dd_samples 同模式——见 GET_AI_PLAY 请求携带（v1.90）。
        """
        from bridge.mcts.alpha_mu import AlphaMuSearch

        perspective = state.current_player
        cards = len(state.hands.get(perspective, []))

        # 请求级临时覆盖（仅传入非 None 时）：αμ world数 / 层数M
        _saved_worlds = None
        _saved_m = None
        if amu_worlds is not None and self.alpha_mu_search:
            _saved_worlds = self.alpha_mu_search.num_worlds
            self.alpha_mu_search.num_worlds = amu_worlds
        if amu_m is not None and self.alpha_mu_search:
            _saved_m = self.alpha_mu_search.M
            self.alpha_mu_search.M = amu_m
        try:
            return self._alpha_mu_play_inner(state, perspective, cards)
        finally:
            if _saved_worlds is not None and self.alpha_mu_search:
                self.alpha_mu_search.num_worlds = _saved_worlds
            if _saved_m is not None and self.alpha_mu_search:
                self.alpha_mu_search.M = _saved_m

    def _alpha_mu_play_inner(self, state: PlayState, perspective: str,
                             cards: int) -> Dict[str, Any]:

        # 时间预算从世界生成开始计时（含枚举/采样，共享总 deadline）
        _t_alpha_start = time.time()
        remaining_tricks = 13 - (state.declarer_tricks + state.defender_tricks)

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

        # 世界集生成与 DD 完全共用（_generate_worlds 唯一分叉：残局→枚举、
        # 不可行/非残局→均匀采样）。枚举阈值统一用 dd_search.endgame_card_threshold，
        # αμ 不再单独调 _enumerate_endgame_worlds / sampler.sample_n。
        # num_samples=n_worlds：非残局采样时按 αμ 的世界数（DD 自适应样本数仅 DD 用）。
        worlds, source, _gen_t = self.dd_search._generate_worlds(
            state, perspective, remaining_tricks, num_samples=n_worlds)
        if source == "残局枚举":
            print(f"[αμ] 残局完备世界集: {len(worlds)} 个（枚举替代采样，αμ 决策）")

        # P1-2 修复：αμ 搜索预算扣除世界生成已用时间（共享总 deadline，下限 3s）
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
            result = search.search(state, worlds=worlds,
                                   worlds_source="enumerated" if source == "残局枚举" else "sampled")
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
        if source == "残局枚举":
            full_output["引擎阶段"] = "endgame_enum_αμ"
        full_output["叫牌约束"] = self._format_constraints_for_display(constraints)
        full_output["最新约束"] = self._format_latest_constraints_for_display(state, constraints)
        self._inject_played_stats(full_output, state)
        # αμ 引擎完全不引入飞牌管理（含 8飞9砸）：αμ 多世界联合评估已含
        # 飞牌位置考量，飞牌门控依赖的 scores/scoring_val 字段 αμ 也不产出，
        # 额外覆盖只会用 avg_tricks 误判升级。纯 αμ / αμ+LLM / DD-αμ-LLM
        # 残局阶段均经此函数，一并关闭（2026-09-12）。
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
                    # 组合飞条目把 废弃对象/组合飞 放在 "全"[0]（顶层无此键），
                    # 顶层取不到时回退到全列表首条，保证结构池判定与 UI 确认一致
                    all_items = (info.get("全") if isinstance(info.get("全"), list)
                                 and info.get("全") else [info])
                    combo = bool(info.get("组合飞") or any(
                        isinstance(it, dict) and it.get("组合飞") for it in all_items))
                    disc = info.get("废弃对象")
                    if not disc:
                        disc = next((it.get("废弃对象") for it in all_items
                                     if isinstance(it, dict) and it.get("废弃对象")), None)
                    detected[suit] = {
                        "对象": obj_v,
                        "Δ": info.get("Δ", 0),
                        "引牌": info.get("引牌", ""),
                        "说明": f"探针Δ{info.get('Δ', 0)}（{info.get('引牌', '?')}）",
                        "来源": "probe",
                        "侧": "本侧",
                        "对象牌": obj,
                        "方向": info.get("方向"),
                        "押桶成": info.get("押桶成"),
                        "组合飞": combo,
                        "废弃对象": disc or [],
                        "全": list(all_items),
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
        for r, v in {"A": 14, "K": 13, "Q": 12, "J": 11, "T": 10, "9": 9, "8": 8}.items():
            if v == m:
                return r
        return "?"

    def _probe_finesse_ok(self, state: PlayState, suit: str, info: Dict[str, Any]) -> bool:
        """探针飞牌结构条件判定（用户定义，纯条件、不做赢墩推演）。

        飞牌结构成立 ⇔ 存在一张飞张 G，同时满足：
          ① G < 被飞对象 obj （比对象小）
          ② G > 防守方除 obj 以外的全部该花色牌（能盖住它们）
        即 G 是"对象之下、但盖得住防家所有非对象牌"的飞张（如 K 对 A、
        Q 对 K——前提是防家没有比 G 更大的非对象牌）。

        G 的位置（2026-09-14 用户修订）：
          · 引牌侧的对侧（同伙手里有间张，引牌后可作飞张）
          · **引牌侧自身**：仅当**引牌本身**满足条件（如南持 Q 飞 K、
            Q 在引牌南手——出 Q 逼出 K 或 Q 赢）——与
            _finesse_commit_check 的"同伙引牌 > 威胁 → 引牌一方可赢"判据一致。
            此处是"引牌本身"而非引牌侧整手：本侧引小牌 2 时，南手 Q 不该
            构成飞（用例：本侧引2/A → 废弃）。
        存在 ⇒ 真飞结构（保留探针）；不存在 ⇒ 不能飞（废弃探针）。
        """
        obj = info.get("对象")
        lead = info.get("引牌")
        r2v = self._FINESSE_R2V
        if obj is None or not lead or lead[0] != suit:
            return False
        decl = state.contract.declarer
        dummy = state.dummy
        if info.get("侧") == "伙伴侧":
            lead_side = dummy if decl == state.current_player else decl
        else:
            lead_side = state.current_player
        if lead_side not in (decl, dummy):
            return False
        # 对侧 = 引牌侧的另一半（庄/明手中的另一家）：G 候选 = 对侧全部牌 ∪ 引牌本身
        peer = dummy if lead_side == decl else decl
        g_ranks = set()
        for c in state.hands.get(peer, []):
            if c.suit == suit:
                rv = r2v.get(c.rank, 0)
                if rv:
                    g_ranks.add(rv)
        lead_rv = r2v.get(lead[1:], 0)
        if lead_rv:
            g_ranks.add(lead_rv)
        # 防家除 obj 外该花色剩余牌 = 全部该花色 − 我方持有 − 已出 − obj
        mine = set()
        for pos in (decl, dummy):
            for c in state.hands.get(pos, []):
                if c.suit == suit:
                    r = r2v.get(c.rank, 0)
                    if r:
                        mine.add(r)
        played = set()
        for t in state.tricks:
            for _, c in t.cards:
                if c and c.suit == suit:
                    r = r2v.get(c.rank)
                    if r:
                        played.add(r)
        for _, c in state.current_trick.cards:
            if c and c.suit == suit:
                r = r2v.get(c.rank)
                if r:
                    played.add(r)
        # 组合飞废弃对象（如 ♥KQ 双飞保留 K 后废弃 Q）：不参与"防家最大牌"，
        # 否则被飞对象会被废弃对象抬高挡住飞张判定
        discard_obj = {r2v.get(d) for d in (info.get("废弃对象") or [])
                       if r2v.get(d) is not None}
        enemy = [r for r in range(2, 15)
                 if r not in mine and r not in played and r != obj
                 and r not in discard_obj]
        if not enemy:
            return False
        max_enemy = max(enemy)
        return any(obj > g > max_enemy for g in g_ranks)

    def _registry_finesse_struct(self, state: PlayState,
                                 finesse_struct: Dict[str, Dict[str, Any]]
                                 ) -> Dict[str, Dict[str, Any]]:
        """跟牌接应的结构来源：并入本墩登记（finesse_flow）。

        DD 探针门控只在领出侧生效（跟牌时 trick_cards 非空 → 探针判空），若
        只信当墩探针，跟牌墩将永远无结构、接应判据成死代码。本墩领出方启动
        飞牌时登记的 finesse_flow（含组合飞废弃对象 `finesse_flow_extra`）恰是
        接应所需的结构来源；对象已现身者剔除。已有探针结构的花色以探针为准
        （当墩实际探测优先）。登记只存活到本墩出完（2026-09-13：跨墩续飞已
        移除，无"对象未现身流程不停"的稳定对象语义）。
        """
        if not state.finesse_flow:
            return finesse_struct
        extra = getattr(state, "finesse_flow_extra", None) or {}
        merged = dict(finesse_struct)
        for s, obj in state.finesse_flow.items():
            if not isinstance(obj, int) or s in merged:
                continue
            if self._finesse_obj_played(state, s, obj):
                continue
            discarded = []
            if isinstance(extra.get(s), dict):
                discarded = extra[s].get("废弃对象") or []
            merged[s] = {"对象": obj, "说明": "本墩登记（flow）", "来源": "flow",
                         "对象牌": self._finesse_obj_name(obj),
                         "废弃对象": list(discarded)}
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

    def _intervene(self, state: PlayState, result: Dict[str, Any],
                   ratio: float) -> Dict[str, Any]:
        """介入层总入口（v1.84 架构）：引擎结果之上的并列规则分支，按序裁定，
        先命中先赢。分支独立、互不依赖，未来分支（忍让等）同接口并列加入。

          分支1 _garrison_*（9砸，完全独立于飞牌介入，2026-09-17 用户定调）：
            判据自含（联手张数+持张+对象未现+稳成线），零探针依赖——满手大牌
            场景探针 Δ 天然趋零（DD 完美防守下大牌位置互偿），而 9砸 判据
            本就不需要位置信息，故独立裁定。砸完 AK/A 即退出，交回引擎和
            飞牌介入（无回手/继续飞等后续强制干预）。
          分支2 _finesse_*（飞牌介入）：探针探测→启动门控→过手/引牌；跟牌
            接应。Δ 的语义是"引牌方向探测"（飞张在对象身前出才敏感）。

        九砸标记（flow_extra"九砸"）为跨分支本墩通信：9砸 分支引小时写入，
        飞牌介入的接应消费（顶张超吃）。登记只存活本墩（领出=新墩清空）；
        nine_cash_bank 为 9砸 分支私有跨墩状态（顺序砸 AK 连拔）。
        """
        if state.current_player not in (state.contract.declarer, state.dummy):
            return result
        if self._is_discarding(state):
            return result  # 垫牌：直接信任引擎推荐
        if self._is_leading(state):
            # 领出=新墩开始：上一墩的登记已完成接应使命，作废（组合飞
            # 废弃对象随登记同灭）；随后重新探测+重过门控。
            state.finesse_flow.clear()
            extra = getattr(state, "finesse_flow_extra", None)
            if extra:
                extra.clear()
            # 分支1：9砸 先裁定（门控只管"飞"不管"砸"；稳成线两分支同口径）
            if FINESSE_EIGHT_NINE_ENABLE:
                hit = self._garrison_lead(state, result)
                if hit is not None:
                    return hit
            if not FINESSE_DEFER_ENABLE:
                return result
            return self._finesse_lead(state, result, ratio)
        # 跟牌：9砸 判据先行（9张套顶张兑现优先于接应选牌）；不满足则接应。
        # 结构识别以当墩探针为准，但探针门控只在领出侧生效（跟牌时
        # trick_cards 非空 → 探针必然判空），故并入本墩登记
        # （finesse_flow，含组合飞废弃对象）作为跟牌侧的结构来源。
        if FINESSE_EIGHT_NINE_ENABLE:
            hit = self._garrison_follow(state, result)
            if hit is not None:
                return hit
        if not FINESSE_DEFER_ENABLE:
            return result
        fs = self._detect_finesse_struct(state, result)
        fs = self._registry_finesse_struct(state, fs)
        forced = self._finesse_commit_check(state, fs)
        if forced:
            result, _committed = self._apply_finesse_commit(state, result, fs, ratio)
        return result

    def _top1_make(self, state: PlayState,
                   candidates: List[Dict[str, Any]]) -> float:
        """稳成线口径（2026-09-20 用户定调）：**引擎 top1 候选**的做成率。

        规则：引擎结果 top1 做成率 ≥ FINESSE_NEC_MAKE_HIGH(0.85) → 退让给引擎，
        不做飞牌介入（9砸 分支同口径）。

        变更沿革：
          · v1.84（FIX-7）原口径为「全体候选最高做成率」——理由是"榜首可能被
            位置信息误导，另有一条稳成路线时不应砸/飞"。
          · 2026-09-20 改为「top1 做成率」并下调阈值 0.95→0.85：使实现与
            config 注释（"做成率 ≥ 此值"）语义一致，且退让判据对齐**引擎实际
            要走的路线**——若引擎自己选的路线都已 ≥85% 成约，再改飞牌是负期望。
        无样本数据时返回 1.0（不拦截）。
        """
        need = state.contract.tricks_needed
        if not candidates:
            return 1.0
        scores = candidates[0].get("scores") or []
        if not scores:
            return 1.0
        return sum(1 for x in scores if x >= need) / len(scores)

    def _garrison_target(self, state: PlayState, suit: str,
                         candidates: List[Dict[str, Any]]) -> Optional[Tuple[int, int, bool]]:
        """9砸 判据（独立分支核心，零探针依赖）：仅两种情况（用户定调）。

          AK缺Q（A、K 在手，Q 未现）→ 砸 A 后连拔 K
          AQ缺K（A、Q 在手，K 未现）→ 砸 A
        其他一律不走 9砸（如 AKQ 在手顶张齐全，交回引擎自然兑现）。
        "未现" = 不在联手现手且未打出。返回 (对象, 联手张数, True)，
        对象供连拔检查（对象是否已现）与跟牌侧间张判定；不满足返回 None。
        """
        combined = self._combined_suit_count(state, suit)
        if combined < 9:
            return None
        declarer = state.contract.declarer
        dummy = state.dummy
        own = set()
        seen = set()
        for p in (declarer, dummy):
            for c in state.hands.get(p, []):
                if c.suit == suit:
                    own.add(self._FINESSE_R2V.get(c.rank, 0))
        for t in state.tricks:
            for _, c in t.cards:
                if c and c.suit == suit:
                    seen.add(self._FINESSE_R2V.get(c.rank, 0))
        for _, c in state.current_trick.cards:
            if c and c.suit == suit:
                seen.add(self._FINESSE_R2V.get(c.rank, 0))
        seen |= own
        if 14 in own and 13 in own and 12 not in seen:
            return 12, combined, True
        if 14 in own and 12 in own and 13 not in seen:
            return 13, combined, True
        return None

    def _garrison_lead(self, state: PlayState,
                       result: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """9砸 分支·领出侧（v1.84，完全独立于飞牌介入）。

        ① 连拔检查（nine_cash_bank）：上墩砸 A（缺Q/J 持 A+K）登记的
           "顺序砸"续接——本墩领出且对象未现 → 本方可出 K → 连拔 K；
           K 在对侧 → 引最小小牌 + 九砸标记（伙伴第三家超吃 K 完成连拔）。
           连拔是已启动流程的完成动作，不受稳成线约束。
        ② 独立扫描全部花色（按联手张数降序）：稳成线退让 → 9砸 判据
           （≥9张+缺K持AQ/缺Q持AK+对象未现）→ A 在领出方手直接砸
           （缺Q持AK 登记 cash_bank 下墩连拔 K）；A 在伙伴手 → 引最小
           小牌 + 九砸标记（伙伴超吃 A，缺Q持AK 由接应补登记连拔）。
        命中返回改选后 result；未命中返回 None（交回飞牌介入分支）。
        """
        full_output = result.get("full_output") or {}
        mcts9 = full_output.get("mcts_stats") or {}
        cands9 = mcts9.get("candidates") or []
        # ① 连拔检查（规则优先，不受稳成线约束）
        bank9 = getattr(state, "nine_cash_bank", None)
        if bank9:
            for s, bk in list(bank9.items()):
                obj9 = bk.get("obj")
                rv9 = bk.get("rv")
                if obj9 is None or rv9 is None:
                    del bank9[s]
                    continue
                if self._finesse_obj_played(state, s, obj9):
                    del bank9[s]  # 对象已现身，无需再连拔
                    continue
                tgt9 = next((c for c in cands9 if c.get("card")
                             and c["card"][0] == s
                             and self._FINESSE_R2V.get(c["card"][1:], 0) == rv9), None)
                if tgt9:
                    hint9b = (f"[9砸连拔] {s} 对象{self._finesse_obj_name(obj9)}未现，"
                              f"连拔{self._finesse_obj_name(rv9)}")
                    print(hint9b)
                    result["card"] = Card(s, self._finesse_obj_name(rv9))
                    result["reasoning"] = hint9b + "\n" + result.get("reasoning", "")
                    fo9 = result.get("full_output") or {}
                    fo9["推荐出牌"] = tgt9["card"]
                    fo9["核心逻辑"] = hint9b + "\n" + fo9.get("核心逻辑", "")
                    fo9["八九原则"] = {"花色": s, "缺": self._finesse_obj_name(obj9),
                                        "原则": "9砸连拔", "改选": tgt9["card"]}
                    del bank9[s]
                    return result
                small9 = [c for c in cands9 if c.get("card")
                          and c["card"][0] == s
                          and 2 <= self._FINESSE_R2V.get(c["card"][1:], 0) <= 9]
                if small9:
                    pick9 = min(small9,
                                key=lambda c: self._FINESSE_R2V.get(c["card"][1:], 0))
                    hint9c = (f"[9砸连拔] {s} 对象{self._finesse_obj_name(obj9)}未现，"
                              f"连拔{self._finesse_obj_name(rv9)}在对侧，"
                              f"引{pick9['card']}让伙伴超吃")
                    print(hint9c)
                    result["card"] = Card(pick9["card"][0], pick9["card"][1:])
                    result["reasoning"] = hint9c + "\n" + result.get("reasoning", "")
                    fo9 = result.get("full_output") or {}
                    fo9["推荐出牌"] = pick9["card"]
                    fo9["核心逻辑"] = hint9c + "\n" + fo9.get("核心逻辑", "")
                    fo9["八九原则"] = {"花色": s, "缺": self._finesse_obj_name(obj9),
                                        "原则": "9砸连拔(顶张在对侧)",
                                        "改选": pick9["card"]}
                    self._register_finesse_flow(state, s, obj9, None)
                    extra9 = getattr(state, "finesse_flow_extra", None)
                    if extra9 is None:
                        extra9 = {}
                        setattr(state, "finesse_flow_extra", extra9)
                    extra9.setdefault(s, {})["九砸"] = True
                    del bank9[s]
                    return result
                # 本方无可出（无 K 无小牌）→ 保留登记下墩再试
        # ② 独立扫描（不依赖探针结构池）
        if self._top1_make(state, cands9) >= FINESSE_NEC_MAKE_HIGH:
            return None  # 稳成线退让（引擎top1成约≥85%）：不砸也成，尊重引擎（连拔不受此限）
        declarer = state.contract.declarer
        dummy = state.dummy
        suits_by_len = sorted("♠♥♦♣",
                              key=lambda s2: -self._combined_suit_count(state, s2))
        for suit in suits_by_len:
            tgt = self._garrison_target(state, suit, cands9)
            if tgt is None:
                continue
            obj, combined, _should = tgt
            cur_str = str(result.get("card")) if result.get("card") else ""
            # A 在领出方手 → 直接砸 A
            bank = [c for c in cands9 if c.get("card")
                    and c["card"][0] == suit
                    and self._FINESSE_R2V.get(c["card"][1:], 0) == 14]
            if bank:
                hint = (f"[9砸] {suit} 联手{combined}张缺{self._finesse_obj_name(obj)}"
                        f"持{'AQ' if obj == 13 else 'AK'}应砸A（9砸独立分支）")
                print(hint)
                result["card"] = Card(suit, "A")
                result["reasoning"] = hint + "\n" + result.get("reasoning", "")
                fo = result.get("full_output") or {}
                fo["推荐出牌"] = suit + "A"
                fo["核心逻辑"] = hint + "\n" + fo.get("核心逻辑", "")
                fo["八九原则"] = {"花色": suit, "缺": self._finesse_obj_name(obj),
                                  "联手张数": combined, "原则": "9砸",
                                  "榜首": cur_str, "改选": suit + "A"}
                fo["领出飞牌"] = {"引发": False, "说明": "9砸独立分支（顶张在手，出A砸）"}
                # 缺Q/J 持 AK：A 砸后 K 仍在联手 → 登记连拔（下墩顺序砸 K）
                if (obj != 13
                        and not self._finesse_obj_played(state, suit, 13)
                        and any(self._FINESSE_R2V.get(c.rank, 0) == 13
                                for p in (declarer, dummy)
                                for c in state.hands.get(p, [])
                                if c.suit == suit)):
                    nb9 = getattr(state, "nine_cash_bank", None)
                    if nb9 is None:
                        nb9 = {}
                        setattr(state, "nine_cash_bank", nb9)
                    nb9[suit] = {"obj": obj, "rv": 13}
                return result
            # A 在伙伴手（本方无 A 可出）→ 引最小小牌 + 九砸标记（伙伴超吃 A）
            small = [c for c in cands9 if c.get("card")
                     and c["card"][0] == suit
                     and 2 <= self._FINESSE_R2V.get(c["card"][1:], 0) <= 9]
            if small:
                pick = min(small,
                           key=lambda c: self._FINESSE_R2V.get(c["card"][1:], 0))
                hint = (f"[9砸] {suit} 联手{combined}张缺{self._finesse_obj_name(obj)}"
                        f"应砸A（顶张在对侧）：引{pick['card']}让伙伴A超吃")
                print(hint)
                result["card"] = Card(pick["card"][0], pick["card"][1:])
                result["reasoning"] = hint + "\n" + result.get("reasoning", "")
                fo = result.get("full_output") or {}
                fo["推荐出牌"] = pick["card"]
                fo["核心逻辑"] = hint + "\n" + fo.get("核心逻辑", "")
                fo["八九原则"] = {"花色": suit, "缺": self._finesse_obj_name(obj),
                                  "联手张数": combined, "原则": "9砸(顶张在对侧)",
                                  "榜首": cur_str, "改选": pick["card"]}
                fo["领出飞牌"] = {"引发": False, "说明": "9砸独立分支（顶张在对侧，引小让A砸）"}
                self._register_finesse_flow(state, suit, obj, None)
                extra9 = getattr(state, "finesse_flow_extra", None)
                if extra9 is None:
                    extra9 = {}
                    setattr(state, "finesse_flow_extra", extra9)
                extra9.setdefault(suit, {})["九砸"] = True
                return result
        return None

    def _garrison_follow(self, state: PlayState,
                         result: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """9砸 分支·跟牌侧（v1.84）：所跟花色满足 9砸 判据 → A 替代间张。

        介入口径：引擎当前决策牌为该花色"低于对象的间张"（10 ≤ rv < 对象，
        拟飞/拟盖的间张牌）时改出 A——9张套的顶张兑现优先；引擎已选 A/小牌
        （保结构、接应已胜）不干预。A 须在当前跟牌方手。缺Q/J 持 AK 且 K 在
        联手未出 → 出 A 后登记 cash_bank（下墩连拔 K）。稳成线退让。
        """
        trick = getattr(state, "current_trick", None)
        lead_suit = trick.get_lead_suit() if trick else None
        if not lead_suit:
            return None
        cur_card = result.get("card")
        cur_str = str(cur_card) if cur_card else ""
        if not cur_str or cur_str[0] != lead_suit:
            return None
        full_output = result.get("full_output") or {}
        candidates = (full_output.get("mcts_stats") or {}).get("candidates") or []
        tgt = self._garrison_target(state, lead_suit, candidates)
        if tgt is None:
            return None
        obj, combined, _should = tgt
        cur_rv = self._FINESSE_R2V.get(cur_str[1:], 0)
        if not (10 <= cur_rv < obj):
            return None  # 引擎未选间张（已选A/小牌）→ 不干预
        my_cards = [c for c in state.hands.get(state.current_player, [])
                    if c.suit == lead_suit]
        if not any(self._FINESSE_R2V.get(c.rank, 0) == 14 for c in my_cards):
            return None  # A 不在本方手 → 跟牌无法砸
        if self._top1_make(state, candidates) >= FINESSE_NEC_MAKE_HIGH:
            return None  # 稳成线退让
        declarer = state.contract.declarer
        dummy = state.dummy
        hint = (f"[9砸] {lead_suit} 联手{combined}张缺{self._finesse_obj_name(obj)}"
                f"跟牌应砸A：榜首{cur_str} → 改出{lead_suit}A")
        print(hint)
        result["card"] = Card(lead_suit, "A")
        result["reasoning"] = hint + "\n" + result.get("reasoning", "")
        fo = result.get("full_output") or {}
        fo["推荐出牌"] = lead_suit + "A"
        fo["核心逻辑"] = hint + "\n" + fo.get("核心逻辑", "")
        fo["八九原则"] = {"花色": lead_suit, "缺": self._finesse_obj_name(obj),
                          "联手张数": combined, "原则": "9砸(跟牌)",
                          "榜首": cur_str, "改选": lead_suit + "A"}
        # 缺Q/J 持 AK：K 在联手未出 → 登记 cash_bank（下墩连拔）
        if (obj != 13
                and not self._finesse_obj_played(state, lead_suit, 13)
                and any(self._FINESSE_R2V.get(c.rank, 0) == 13
                        for p in (declarer, dummy)
                        for c in state.hands.get(p, [])
                        if c.suit == lead_suit)):
            nb9 = getattr(state, "nine_cash_bank", None)
            if nb9 is None:
                nb9 = {}
                setattr(state, "nine_cash_bank", nb9)
            nb9[lead_suit] = {"obj": obj, "rv": 13}
        return result

    def _finesse_lead(self, state: PlayState, result: Dict[str, Any],
                      ratio: float) -> Dict[str, Any]:
        """飞牌介入分支·领出侧（v2.03 顺序定调：结构探测确认 → 稳成检测 → 押桶成榜首）。

        9砸 已独立为 _garrison_lead 分支先行裁定（未命中才进入本函数）。
        执行顺序（2026-09-21 用户定调"先确认后稳成"）：
          ① 结构探测（本侧+伙伴侧）→ _probe_finesse_ok 逐条确认 → 确认结构池
          ② 稳成检测：引擎 top1 做成率 ≥85% → 用**已确认**池判断引擎领出
             是否在飞牌花色（在则仅登记本墩接应，不在则提前退让）
          ③ 未稳成 → _probe_lead_finesse_prefer 全局押桶成榜首 + 榜首门控
        稳成检测必须后置于结构确认：未确认探针（如防家仍有更大牌的对象）
        不能作为"引擎 top1 是否在飞牌花色"的判断依据。
        """
        full_output = result.get("full_output", {})
        # 结构探测（2026-09-10）：本侧 + 队友侧（仅领出方为庄/明手时探测）全部
        # 汇聚；每个探针先过"引牌测试"（_probe_finesse_ok 单花色推演，非 DDS）——
        # 引牌打出后对象在防家两侧结果相同 ⇒ 不能飞，废弃该探针。保留的探针
        # 全部参与后续（v1.89：不再按 Δ 剪枝为单条，改留栈逐条过门控）。
        local = self._detect_finesse_struct(state, result)
        partner = self._probe_partner_finesse_struct(state)
        # 全部探针结果花色（本侧+伙伴侧，含被废弃者）：选中的飞牌花色需要过手时，
        # 过手牌绝不能来自这些花色——可能破坏其他飞牌结构造成严重后果。
        probe_suits = set(local) | set(partner)
        full_output["_probe_suits"] = sorted(probe_suits)
        pool = []
        confirm = {}
        r2v = self._FINESSE_R2V
        for s, info in list(local.items()) + list(partner.items()):
            mark_prefix = "探针" if info.get("侧") == "本侧" else "伙伴探针"
            if info.get("来源") == "probe" and info.get("引牌"):
                # 判定只做一次（2026-09-13）：结果同时决定"是否进结构池"（行为）
                # 与 _probe_confirm 的 ✓/✗（UI 显示），两者同源，杜绝两边参数
                # 不一致导致的"显示✓实际判废"。
                # 逐条展开（2026-09-15）：此前只裁决每花色最高Δ代表一条（如 ♠J），
                # 其余对象（如 ♠K 引小、Q 可盖 J 的真飞结构）被连带废弃，整花色
                # 一并漏判成"无飞牌结构"。现按"全"逐条 (对象, 引牌) 各过
                # _probe_finesse_ok，通过者才入结构池；确认键带对象避免
                # 同引牌多对象撞键（J3/K3 共显✗）。
                all_probe = (info.get("全")
                             if isinstance(info.get("全"), list) and info.get("全")
                             else [info])
                entry_combo = bool(info.get("组合飞"))
                entry_disc = info.get("废弃对象") or []
                for e in all_probe:
                    e_info = dict(info)
                    obj_s = (e.get("对象牌") or e.get("对象")
                             or info.get("对象牌") or info.get("对象"))
                    if isinstance(obj_s, str):
                        obj_v = r2v.get(obj_s)
                    elif isinstance(obj_s, int):
                        obj_v = obj_s
                        obj_s = self._finesse_obj_name(obj_v)
                    else:
                        obj_v = None
                    if obj_v is None:
                        continue
                    e_info["对象"] = obj_v
                    e_info["对象牌"] = obj_s
                    e_info["Δ"] = e.get("Δ", info.get("Δ", 0))
                    e_info["引牌"] = e.get("引牌", info.get("引牌", ""))
                    e_info["押桶成"] = e.get("押桶成", info.get("押桶成"))
                    e_info["方向"] = e.get("方向", info.get("方向"))
                    e_info["组合飞"] = bool(e.get("组合飞", entry_combo))
                    e_info["废弃对象"] = e.get("废弃对象") or entry_disc
                    ok = self._probe_finesse_ok(state, s, e_info)
                    confirm[f"{mark_prefix}|{s}|{obj_s}|{e_info['引牌']}"] = ok
                    if not ok:
                        print(f"[探针废弃] {s}对象{self._finesse_obj_name(obj_v)} "
                              f"引{e_info['引牌']}：对象放防家两侧无差异，不能飞")
                        continue
                    pool.append((s, e_info))
            else:
                pool.append((s, info))
        mcts_stats = full_output.get("mcts_stats") or {}
        candidates = mcts_stats.get("candidates") or []
        # 多花色结构池（2026-09-12）：全部通过测试的探针花色都保留。
        # v2.00 简化（用户定调）：不再按同 (花色,对象,侧) 取档压缩代表——
        # 全局押桶成排序取榜首（_probe_lead_finesse_prefer）天然让最高
        # 押桶成引牌胜出，提前压缩反而可能拦掉押桶成更高的备选。
        struct_stack: Dict[str, List[Dict[str, Any]]] = {}
        for s, info in pool:
            struct_stack.setdefault(s, []).append(info)
        for s in struct_stack:
            struct_stack[s].sort(key=lambda i: -(i.get("Δ") or 0))
        if partner:
            full_output["伙伴探针"] = partner
        if confirm:
            full_output["_probe_confirm"] = confirm
        # 稳成检测（v2.03 定调·后置于结构确认）：引擎 top1 做成率 ≥85% 直接
        # 退让，不做榜单改出。与**已确认**结构池对比（结构探测+_probe_finesse_ok
        # 已先行完成）——仅当引擎领出牌花色在该确认池中才登记本墩接应，杜绝
        # 未确认探针（如防家仍有更大牌的对象）被借用于登记（2026-09-21 用户
        # 指出：未确认探针不能作为"top1 是否在飞牌花色"的判断依据）。
        if candidates and self._top1_make(state, candidates) >= FINESSE_NEC_MAKE_HIGH:
            cur_str = str(result.get("card") or "")
            if cur_str and cur_str[0] in struct_stack:
                suit = cur_str[0]
                info = struct_stack[suit][0]
                obj = info.get("对象")
                if obj is not None and not self._finesse_obj_played(state, suit, obj):
                    self._register_finesse_flow(state, suit, obj, info)
                    full_output["领出飞牌"] = {"引发": True, "花色": suit,
                                               "对象": obj, "Δ": info.get("Δ"),
                                               "领出": cur_str,
                                               "说明": "稳成且引擎已在飞牌花色（结构已确认），登记供本墩接应"}
                else:
                    full_output["领出飞牌"] = {"引发": True, "花色": suit,
                                               "对象": obj, "Δ": info.get("Δ"),
                                               "领出": cur_str,
                                               "说明": "稳成，引擎领出飞牌花色（结构已确认），尊重引擎"}
                result["full_output"] = full_output
                return result
            full_output["领出飞牌"] = {"引发": False, "说明": "稳成（引擎top1成约≥85%），提前退让"}
            result["full_output"] = full_output
            return result
        # 全部引牌候选明细（2026-09-21 用户要求：打牌结果显示所有候选引牌的
        # 押桶成，不只胜出的榜首）：{花色: [{引牌, 对象, 押桶成, 方向, Δ,
        # 组合飞, 过手牌, 侧}]}，依探测通过顺序原样记录。
        cand_detail: Dict[str, List[Dict[str, Any]]] = {}
        for s, info in pool:
            cand_detail.setdefault(s, []).append({
                "引牌": info.get("引牌", ""),
                "对象": info.get("对象牌"),
                "押桶成": info.get("押桶成"),
                "方向": info.get("方向"),
                "Δ": info.get("Δ"),
                "组合飞": bool(info.get("组合飞")),
                "过手牌": info.get("过手牌"),
                "侧": info.get("侧", "本侧"),
            })
        if cand_detail:
            full_output["探针候选"] = cand_detail
        if not struct_stack:
            # 本侧+队友侧均无结构：Δ 是采样量，探针判空即无飞牌结构，
            # 尊重引擎（2026-09-13：跨墩续飞已移除，不再有"流程延续"路径）。
            full_output["领出飞牌"] = {"引发": False, "说明": "无飞牌结构"}
            result["full_output"] = full_output
            return result
        # v2.00 简化：不再有"引擎已在飞牌花色"早退分支——引擎 top1 恰为
        # 引牌时同样落入全局押桶成榜首决策（_probe_lead_finesse_prefer），
        # 由其统一裁决登记/改出；对象已现身花色经探测端窗口滑动自然排除。
        cur_str = str(result.get("card") or "")
        # 榜单决策（v2.00）：_probe_lead_finesse_prefer 全局押桶成排序取
        # 榜首 + 榜首单独过门控（比值单调性论证），改出榜首并登记。
        if candidates:
            prefer = self._probe_lead_finesse_prefer(
                state, struct_stack, candidates, ratio, result)
            if prefer:
                pick, why = prefer
                org_str = cur_str
                hint4 = (f"[窗口期启动飞牌] 探针识别出飞牌结构，"
                         f"改出{pick}启动（{why}）")
                print(hint4)
                reasoning = result.get("reasoning", "")
                result["card"] = Card(pick[0], pick[1:])
                result["reasoning"] = f"{hint4}\n{reasoning}"
                full_output["推荐出牌"] = pick
                full_output["核心逻辑"] = hint4 + "\n" + full_output.get("核心逻辑", "")
                full_output["窗口期启动"] = {
                    "花色": pick[0], "原选": org_str, "改选": pick,
                    "说明": why}
                result["full_output"] = full_output
                return result
        # 未介入：尊重引擎（全被门控否决 / 无动作可出 / 未领出飞牌花色）
        struct_list = []
        for s in struct_stack:
            info_s = struct_stack[s][0]
            d = info_s.get("Δ")
            name_s = f"{s}(" + self._finesse_obj_name(info_s["对象"]) + ")"
            name_s = name_s[:-1] + f",Δ{d:.2f})" if d else name_s
            struct_list.append(name_s)
        full_output["领出飞牌"] = {
            "引发": False,
            "结构": "、".join(struct_list),
            "说明": "未领出飞牌花色，不引发",
        }
        result["full_output"] = full_output
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
            rs = self.dd_search.search(state, perspective=partner, actual_turn=partner,
                                       preset_worlds=getattr(self.dd_search, "last_worlds", None))
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
                all_items = (info.get("全") if isinstance(info.get("全"), list)
                             and info.get("全") else [info])
                combo = bool(info.get("组合飞") or any(
                    isinstance(it, dict) and it.get("组合飞") for it in all_items))
                disc = info.get("废弃对象")
                if not disc:
                    disc = next((it.get("废弃对象") for it in all_items
                                 if isinstance(it, dict) and it.get("废弃对象")), None)
                out[s] = {
                    "对象": obj,
                    "Δ": info.get("Δ", 0),
                    "引牌": info.get("引牌", ""),
                    "说明": f"探针Δ{info.get('Δ', 0)}（{info.get('引牌', '?')}）",
                    "来源": "probe",
                    "侧": "伙伴侧",
                    "方向": info.get("方向"),
                    "押桶成": info.get("押桶成"),
                    "组合飞": combo,
                    "废弃对象": disc or [],
                    "全": list(all_items),
                }
        return out

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

    def _cash_reentry(self, state: PlayState,
                      candidates: List[Dict[str, Any]], suit: str,
                      excluded_suits=()) -> Optional[Tuple[str, float]]:
        """伙伴侧飞牌结构的安全过手牌选择：选无关花色小牌过手到队友。

        过手牌判定（基于两手牌确定性判断，不做比值）：
          找"队友稳赢"的无关花色：队友该花色最大牌 R_p >
        该花色潜在敌方最大牌 threat（= 未现于两家手牌/已出牌的最大 rank）。
          例：♠A 已出、队友持 ♠K → threat ≤ Q < K，出 ♠4 队友必赢 → 过手成立。
          在稳赢花色的候选小牌(rank≤9)中取最小牌（最小让渡，不烧间张）。
        无任何稳赢过手花色 → 返回 None，回到引擎按得分选牌。
        excluded_suits：额外排除的花色（其他有探针结果的飞牌结构花色）——
        过手牌绝不能来自这些花色（避免破坏其他飞牌结构造成严重后果）。
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
            if s2 == suit or s2 in excluded_suits:
                continue  # 飞牌花色与其他探针结构花色均不用于回手
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

    @staticmethod
    def _percentile_int(vals: List[int], pct: float) -> int:
        """最近秩百分位（升序第 ⌊pct%·n⌋ 个，越界夹到端点）。"""
        if not vals:
            return 0
        vs = sorted(vals)
        k = int(math.floor(pct / 100.0 * len(vs)))
        k = max(0, min(len(vs) - 1, k))
        return vs[k]

    def _finesse_launch_worthwhile(self, state: PlayState, action_card: str,
                                   candidates: List[Dict[str, Any]],
                                   action_make: Optional[float] = None
                                   ) -> Tuple[bool, str]:
        """逐动作启动退让门控（v1.89：稳成已由 _finesse_lead 入口短路）。

        分子 = 动作牌价值，分母 = 引擎榜首（v1.94 两侧同秤）：
          · 引牌在押注方向半桶的做成率（探针"押桶成"）——启动飞牌后
            非押注方向的世界已无意义，飞牌线价值按押注桶的条件做成率计；
            混合值（本侧引擎值/伙伴侧过手牌独立值）掺入非押注世界的死值，
            会系统性低估飞牌线。
          · 契约必要（榜首做成率 < FINESSE_NEC_MAKE=0.50）且动作/榜首
            比值 ≥ FINESSE_NEC_MIN_RATIO=0.50 → 必飞；
          · 否则动作/榜首 ≥ FINESSE_NEC_RATIO=0.70 → 启动；
          · 否则退让（尊重引擎）。
        无候选数据时不拦截。返回 (是否启动, 说明)。
        """
        if not candidates:
            return True, ""
        top = candidates[0]
        need = state.contract.tricks_needed
        top_scores = top.get("scores") or []
        n = len(top_scores)
        top_make = (sum(1 for x in top_scores if x >= need) / n) if n else 1.0
        top_val = (top.get("scoring_val")
                   if top.get("scoring_val") is not None
                   else top.get("avg_tricks", 0.0))
        if action_make is not None:
            action_val = float(action_make)
        else:
            action_val = next((c.get("scoring_val")
                               if c.get("scoring_val") is not None
                               else c.get("avg_tricks", 0.0)
                               for c in candidates if str(c.get("card")) == action_card),
                              None)
        if action_val is None:
            return True, ""
        if top_make < FINESSE_NEC_MAKE:
            if self._finesse_ratio_ok(state, candidates, action_card,
                                      FINESSE_NEC_MIN_RATIO,
                                      b_card=str(top.get("card")),
                                      a_make_override=action_make):
                return True, f"契约必要（榜首做成{top_make:.0%}，不飞没机会）"
            # 飞牌相对榜首差距过大（<下限）→ 不强制起飞，落 D 闸裁决
        if (top_val > 0
                and self._finesse_ratio_ok(state, candidates, action_card,
                                           FINESSE_NEC_RATIO,
                                           b_card=str(top.get("card")),
                                           a_make_override=action_make)):
            return True, f"比值尚可（≥{FINESSE_NEC_RATIO}）"
        slack = top.get("avg_tricks", 0.0) - need
        if action_make is not None:
            ratio_txt = f"{action_val / top_make:.2f}" if top_make > 0 else "—"
        else:
            ratio_txt = f"{action_val / top_val:.2f}" if top_val > 0 else "—"
        return False, f"退让（榜首做成{top_make:.0%}·盈余{slack:+.1f}已够，比值{ratio_txt}<{FINESSE_NEC_RATIO}）"

    def _register_finesse_flow(self, state: PlayState, s: str, obj: int,
                               info: Optional[Dict[str, Any]] = None) -> None:
        """登记飞牌流程：写 flow（对象）+ flow_extras（组合飞废弃对象）。

        组合飞（保 K 废 Q）启动后，后续接应方靠 flow 取结构——当墩探针在跟牌
        时判空，废弃对象随 flow_extras 带过去，供 _finesse_commit_check 威胁
        计算排除。
        """
        state.finesse_flow[s] = obj
        extra = getattr(state, "finesse_flow_extra", None)
        if extra is None:
            extra = {}
            setattr(state, "finesse_flow_extra", extra)
        entry = dict(extra.get(s) or {})
        disc = (info or {}).get("废弃对象") or []
        if disc:
            entry["废弃对象"] = list(disc)
        direction = (info or {}).get("方向")
        if direction:
            entry["方向"] = direction
        if entry:
            extra[s] = entry
        else:
            extra.pop(s, None)

    def _partner_overhand_action(self, state: PlayState, s: str, obj, partner_lead,
                                 candidates: List[Dict[str, Any]], gate_why: str,
                                 excluded_suits=()):
        """过手给队友引飞（伙伴侧路线被判定更优时执行）。

        与"侧==伙伴侧"分支同一可行性：队友须有该花色飞张小牌（<对象）；
        有稳赢过手牌（cash_reentry）才可实际过手——过手牌不能来自其他
        探针结果花色（excluded_suits），否则破坏其他飞牌结构，找不到安全
        过手牌则尊重引擎。返回 (改出牌, 说明)；不可行返回 None。

        过手**不启动飞牌**（2026-09-12）：这里不写 finesse_flow。过手牌可能
        被将吃拦截、队友未必进手；若提前登记流程，一旦进手失败会造成后续
        按死流程强飞的麻烦。过手后下一墩重新探测、重新走完整飞牌介入流程
        （含全部退让机制），由实际局面重新决定是否引飞。
        """
        leader = state.current_player
        partner = (state.dummy if leader == state.contract.declarer
                   else state.contract.declarer)
        if not any(c.suit == s and self._FINESSE_R2V.get(c.rank, 0) < obj
                   for c in state.hands.get(partner, [])):
            return None
        reentry = self._cash_reentry(state, candidates, s,
                                     excluded_suits=excluded_suits)
        if not reentry:
            return None
        return reentry[0], f"{gate_why}；动作：过手给队友引飞（引牌{partner_lead}）"

    def _probe_lead_finesse_prefer(self, state: PlayState, struct_stack: Dict[str, List[Dict[str, Any]]],
                                   candidates: List[Dict[str, Any]], ratio: float,
                                   result: Dict[str, Any]) -> Optional[Tuple[str, str]]:
        """窗口期主动启动飞牌（v2.00 简化：过手预检 → 押桶成榜首 → 榜首单独门控）。

        输入为以花色为键、Δ 降序的条目栈（探测已全部通过引牌测试，组合飞
        字段透传）。过手预检：伙伴侧条目逐个求安全过手牌，失败只删该条目
        （不再整花色出局）；动作统一为真实出牌（本侧=引牌 / 伙伴侧=过手牌）。
        全局押桶成排序保留榜首（_subset_select）：同花色方向对决与逐动作
        门控的集合语义，可由"门控比值单调于押桶成 → 榜首即唯一候选"替代，
        故只对榜首单独过门控（_finesse_launch_worthwhile，判据不变），
        通过即登记终选；被否 / 无动作可出 → None（尊重引擎）。
        """
        if not FINESSE_DEFER_ENABLE:
            return None
        excluded = (result.get("full_output") or {}).get("_probe_suits") or ()
        # 过手预检（v1.89：逐条目弹栈，失败只删该条目，其余备胎保留）
        for s, entries in list(struct_stack.items()):
            alive = []
            for info in entries:
                if info.get("侧") == "伙伴侧":
                    act = self._partner_overhand_action(
                        state, s, info.get("对象"), info.get("引牌", "?"),
                        candidates, "", excluded_suits=excluded)
                    if act is None:
                        print(f"[过手预检] {s} 动作Δ{info.get('Δ')} 无法安全过手，弹栈")
                        continue
                    info["过手牌"] = act[0]
                alive.append(info)
            if alive:
                struct_stack[s] = alive
            else:
                del struct_stack[s]
        if not struct_stack:
            return None
        # 动作池：每条目 → 真实出牌动作（探针法必有引牌/过手牌，必须存在
        # 于引擎候选池才有评估值；模板法条目不经介入层，无兜底）。
        actions = []  # (动作牌, 条目, 花色)
        for s, entries in struct_stack.items():
            for info in entries:
                act = info.get("过手牌") if info.get("侧") == "伙伴侧" else info.get("引牌")
                if act and any(c.get("card") == act for c in candidates):
                    actions.append((act, info, s))
        if not actions:
            return None
        # 全局押桶成排序，保留榜首（v2.00 用户定调：路线对决的"同花色单方向"
        # 与逐动作门控的集合语义，皆因"门控比值单调于押桶成"而被榜首取代）
        best = self._subset_select(state, candidates, actions)
        if best is None:
            return None
        pick, info, s = best
        # 榜首单独过门控（同一判据）：通过即终选登记；被否 → 尊重引擎
        a_make = info.get("押桶成")
        worth, gate_why = self._finesse_launch_worthwhile(state, pick, candidates,
                                                         action_make=a_make)
        if not worth:
            print(f"[启动退让] {s} 榜首{pick}：{gate_why}")
            return None
        obj = info.get("对象")
        obj_name = self._finesse_obj_name(obj) if obj is not None else "?"
        self._register_finesse_flow(state, s, obj, info)
        a_mk = info.get("押桶成")
        mk_txt = f"押桶成{a_mk:.0%}" if a_mk is not None else "引擎值"
        combo = "双飞组合" if info.get("组合飞") else "单飞"
        if info.get("侧") == "伙伴侧":
            why = (f"飞{obj_name}({combo})过手{pick}给队友引飞"
                   f"（引牌{info.get('引牌', '?')}，{mk_txt}）")
        else:
            why = f"飞{obj_name}({combo}){mk_txt}直出{pick}"
        return pick, f"终选·押桶成榜首（{why}）"

    def _subset_select(self, state: PlayState,
                       candidates: List[Dict[str, Any]],
                       passed: List[Tuple[str, Dict[str, Any], str]],
                       ) -> Optional[Tuple[str, Dict[str, Any], str]]:
        """押桶成榜首选择：全部动作按押桶成主排序，平票用较大领出牌决胜。

        主键 = 条目"押桶成"（与门控分子同口径：启动飞牌后非押注方向世界
        无意义，引牌价值按押注方向半桶做成率计）。押桶成缺失（模板法条目
        无探针数据）回退引擎全样本做成率。平票决胜（v2.03 用户定调，押桶成
        平局之后）：偏好"领出牌 牌点 > 较小飞牌对象"（min(对象, *废弃对象)）
        的较大牌——不区分单双飞：单飞仅一对象=min对象，领出牌必小于对象
        → 大牌判据失效；双飞 K/9 → min=9，♦J/♦Q 牌点>9 即判大牌优先。
        再平票降级到引擎决策值（make_rate 下 blended=做成率×10000+平均
        赢墩），最后 rankpos（同为大牌时的最大牌）。启动方必为庄家方，统一取高。
        """
        from bridge.mcts import dd_search as _ds
        if not passed:
            return None
        _dds = getattr(self, "dd_search", None)
        mode = (_dds.scoring_mode if _dds is not None else None) or "make_rate"
        need = state.contract.tricks_needed
        cand_map = {str(c.get("card")): c for c in candidates}
        best = None
        best_key = None
        for act, info, s in passed:
            cc = cand_map.get(act) or {}
            scores = cc.get("scores") or []
            if mode == "make_rate" and scores:
                mk = _ds._make_rate_value(scores, need)
                blended = mk * 10000.0 + (cc.get("avg_tricks") or 0.0)
            else:
                v = cc.get("scoring_val")
                blended = v if v is not None else (cc.get("avg_tricks") or 0.0)
            a_make = info.get("押桶成")
            if a_make is None:
                a_make = _ds._make_rate_value(scores, need) if scores else 0.0
            else:
                a_make = float(a_make)
            # 平票决胜先于引擎值：倾向"牌点 > 较小飞牌对象"的较大领出牌
            # （v2.03 用户定调，押桶成平局之后；不区分单双飞，见 docstring）
            lead = info.get("引牌") or act
            lead_rv = self._FINESSE_R2V.get(lead[1] if len(lead) >= 2 else lead, 0)
            def _rv(v):
                return v if isinstance(v, int) else self._FINESSE_R2V.get(v[-1] if v else "", 0)
            obj_vals = []
            _obj = info.get("对象")
            if _obj is not None:
                obj_vals.append(_rv(_obj))
            for _d in (info.get("废弃对象") or []):
                obj_vals.append(_rv(_d))
            obj_vals = [v for v in obj_vals if v > 0]
            min_obj = min(obj_vals) if obj_vals else None
            big = 1.0 if (min_obj is not None and lead_rv > min_obj) else 0.0
            rankpos = lead_rv / 14.0
            key = (a_make, big, blended, rankpos)
            print(f"[终选] 动作{act} 花色{s} 押桶成{a_make} "
                  f"大牌big={big:.0f} 领出{lead}(牌点{lead_rv}) "
                  f"min对象{min_obj} 引擎blended={round(blended, 2)} "
                  f"(做成率{mk if mode=='make_rate' and scores else '—'}"
                  f" avg={cc.get('avg_tricks')})")
            if best is None or key > best_key:
                best, best_key = (act, info, s), key
        return best

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
        # BUG-2（v1.84）：领出方必须是我方（伙伴）——防守方领出时 flow 可能
        # 残留上一墩登记（_intervene 仅我方领出时清空），若按"同伙任意位置
        # 出了该花色小牌"判定，会把防守方引发的跟牌误判为我方启动而强制接应。
        first = trick.cards[0]
        if (first[0] != partner or first[1] is None
                or first[1].suit not in fs_suits):
            return None
        partner_rv = self._FINESSE_R2V.get(first[1].rank)
        if partner_rv is None or partner_rv >= finesse_struct[first[1].suit]["对象"]:
            return None
        suit = first[1].suit
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
        # 9砸（顶张在对侧）：同伙引小、起 launch 于登记（flow_extra"九砸"）——
        # 持 A 方（第三家）强制用最大顶张超吃完成砸，规则优先于威胁判定
        extra9 = getattr(state, "finesse_flow_extra", None) or {}
        if isinstance(extra9.get(suit), dict) and extra9[suit].get("九砸"):
            if covers:
                pick9 = max(covers, key=lambda c: self._FINESSE_R2V[c.rank])
                # 超吃顶张后补登记连拔（FIX-10）：缺Q/J 持 AK 场景，A 超吃
                # 完成后 K 仍 > 对象且在联手未出 → 登记 cash_bank 下墩连拔。
                if obj != 13:
                    own_ranks = {self._FINESSE_R2V.get(c.rank)
                                 for p in (declarer, dummy)
                                 for c in state.hands.get(p, []) if c.suit == suit}
                    if 13 in own_ranks:
                        bank9 = getattr(state, "nine_cash_bank", None)
                        if bank9 is None:
                            bank9 = {}
                            setattr(state, "nine_cash_bank", bank9)
                        bank9[suit] = {"obj": obj, "rv": 13}
                return str(pick9), "9砸（同伙引小，持顶张超吃）"
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
        # 组合飞：该花色被废弃对象（如保 K 废 Q）不是"应压威胁"，从敌方剩余
        # 牌剔除——否则威胁被抬高，本家会选不出（或错误地不敢）接应牌。
        info_disc = finesse_struct.get(suit, {}) or {}
        disc = {r2v.get(d) for d in (info_disc.get("废弃对象") or [])
                if r2v.get(d) is not None}
        extra = getattr(state, "finesse_flow_extra", None) or {}
        if isinstance(extra.get(suit), dict):
            disc |= {r2v.get(d) for d in (extra[suit].get("废弃对象") or [])
                     if r2v.get(d) is not None}
        guarded = [r for r in range(14, 1, -1)
                   if r not in present and r != obj and r not in disc]
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
        # BUG-6（v1.84）：第二元素统一为说明文案（此前返回牌名，与其他返回点
        # 的"盖K"/"引牌已胜"混用，消费方拼进 hint 语义不通）
        pick = min(above_threat, key=lambda c: r2v[c.rank])
        block = max((c for c in suit_cards if r2v[c.rank] > obj),
                    key=lambda c: r2v[c.rank], default=None)
        t_name = {14: "A", 13: "K", 12: "Q", 11: "J", 10: "T"}.get(threat, str(threat))
        why = f"第三家压威胁{t_name}"
        if block:
            why += f"（不拔{block}烧顶张）"
        return str(pick), why

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
        flyer_str, why = forced
        if not self._finesse_commit_ratio_ok(state, result, flyer_str, ratio,
                                             finesse_struct=finesse_struct):
            return result, False
        flyer = Card(flyer_str[0], flyer_str[1:])
        struct_desc = "、".join(
            f"{s}(" + self._finesse_obj_name(finesse_struct[s]["对象"]) + ")" for s in finesse_struct
        )
        hint = (f"[飞牌接应] 同伙已在 {struct_desc} 启动飞牌，"
                f"必须出 {flyer_str} 完成飞牌（{why}）")
        print(hint)
        full_output = result.get("full_output", {})
        result["card"] = flyer
        result["reasoning"] = f"{hint}\n{result.get('reasoning', '')}"
        full_output["推荐出牌"] = flyer_str
        full_output["核心逻辑"] = hint + "\n" + full_output.get("核心逻辑", "")
        full_output["飞牌接应"] = {"结构": struct_desc, "启动花色": flyer_str[0],
                                    "强制出": flyer_str, "说明": why}
        return result, True

    def _finesse_commit_ratio_ok(self, state: PlayState, result: Dict[str, Any],
                                 forced_card: str, ratio: float,
                                 finesse_struct: Optional[Dict[str, Dict[str, Any]]] = None
                                 ) -> bool:
        """强制接应退让判据（v1.96 三层判据前插 + v1.93 口径兜底）：
        ⓪ 三层判据（押对世界桶内，引擎最优替代牌的桶内做成率 b_bucket，
        语义=定约对这墩飞牌的依赖度；榜首=非强制牌的引擎最优候选）：
           b_bucket ≤ FINESSE_COMMIT_DIE_PCT 且强制牌桶内成率 > 0
             → 不飞即死，强制接应（6NT 型：西桶 ♦A=0、♦J=0.353）；
           b_bucket ≥ FINESSE_COMMIT_ALIVE_PCT
             → 定约不依赖飞牌，退让引擎（B26 型：西桶 ♦A=0.542、♦Q=1.0）；
           灰色区 / 桶数据缺失 / 双零死局 → 维持 v1.93 口径。
        v1.98 修正一 → v2.02 全中子桶（"严峻"名废弃）：双飞登记有废弃
        对象（Q）时桶键细化为"{direction}·全中"（Q 与登记对象 K 同侧，
        即两对象都在押注方向=接应上家的世界），优先读取——出A后双威胁
        同侧存活各拿一墩必宕正是这些世界，Q 异侧（被迫跌落/被A顺吃）的
        意外收益不再稀释 b_bucket；全中桶空（该方向无同侧世界）落回普通桶。
        v1.98 修正二（top_alt 排除等价组）：与强制牌逐世界 scores 全等
        的候选是同一动作（接应小牌组），拿它算 b_bucket 是评估"接应
        自己"（6NT 双飞案误判根因），跳过取真正的大牌替代（♠A）。
        ① 引擎榜首与强制牌同花色、且榜首也是飞张（rank < 对象）→ 采信
           引擎 top1（飞牌意图与引擎一致，强制改选会破坏引擎规划——
           BM2000 Level 2 B26 丢墩根因）；
        ② 同花色但榜首是顶张/盖张（rank ≥ 对象，如对象 Q 榜首 ♦A）→
           引擎在兑现不是在飞，采信会打断已启动的飞牌流程（启动侧押方向
           飞、接应侧砸顶张漏飞），落比值退让裁决（v1.93 用户定调）；
        ③ 否则委托统一两段式 _finesse_ratio_ok 做比值退让。
        返回 True=差距可接受（维持强制动作）；False=退让、尊重引擎。
        """
        cands = ((result.get("full_output") or {}).get("mcts_stats") or {}).get("candidates") or []
        if not cands:
            return True
        follow = (((result.get("full_output") or {}).get("finesse_probe_follow") or {})
                  .get(forced_card[0]))
        if follow:
            extra = getattr(state, "finesse_flow_extra", None) or {}
            e_suit = extra.get(forced_card[0])
            direction = e_suit.get("方向") if isinstance(e_suit, dict) else None
            if direction in ("东", "西"):
                full_hit = follow.get(f"{direction}·全中")
                bucket = full_hit or follow.get(direction) or {}
                b_name = f"{direction}·全中" if full_hit else direction
                forced_scores = next((c.get("scores") for c in cands
                                      if str(c.get("card")) == forced_card), None)
                top_alt = None
                for c in cands:
                    cs = str(c.get("card"))
                    if cs == forced_card:
                        continue
                    if forced_scores and c.get("scores") == forced_scores:
                        continue
                    top_alt = cs
                    break
                if top_alt and top_alt in bucket:
                    b_bucket = bucket.get(top_alt)
                    a_bucket = bucket.get(forced_card)
                    if b_bucket <= FINESSE_COMMIT_DIE_PCT:
                        if a_bucket and a_bucket > 0:
                            print(f"[接应三层] {forced_card[0]}押{b_name}桶内"
                                  f"引擎最优{top_alt}成{b_bucket:.3f}"
                                  f"≤{FINESSE_COMMIT_DIE_PCT}（不飞即死）→ "
                                  f"强制接应{forced_card}")
                            return True
                    elif b_bucket >= FINESSE_COMMIT_ALIVE_PCT:
                        print(f"[接应三层] {forced_card[0]}押{b_name}桶内"
                              f"引擎最优{top_alt}成{b_bucket:.3f}"
                              f"≥{FINESSE_COMMIT_ALIVE_PCT}（定约不依赖飞牌）→ "
                              f"退让引擎{top_alt}")
                        return False
        top_str = str(cands[0].get("card") or "")
        if top_str and top_str[0] == forced_card[0]:
            obj_v = ((finesse_struct or {}).get(forced_card[0]) or {}).get("对象")
            top_rv = self._FINESSE_R2V.get(top_str[1:])
            if (obj_v is not None and top_rv is not None
                    and top_rv >= obj_v):
                print(f"[飞牌接应] 引擎榜首{top_str}为顶张"
                      f"（≥对象{self._finesse_obj_name(obj_v)}）非飞牌意图，"
                      f"落比值退让裁决强制{forced_card}")
            else:
                print(f"[飞牌接应] 引擎榜首{top_str}与强制{forced_card}同花色，采信引擎 top1")
                return False
        return self._finesse_ratio_ok(state, cands, forced_card, ratio)

    def _finesse_ratio_ok(self, state: PlayState, candidates: List[Dict[str, Any]],
                          a_card: str, ratio: float,
                          b_card: Optional[str] = None,
                          a_make_override: Optional[float] = None) -> bool:
        """比值退让统一判据：做成率优先、决策值兜底（三处飞牌干预共用）。

        段1 做成率（success_rate / scores 相对所需墩达成占比，双方可算且参照>0）：
            比值 = 动作牌达成率 / 参照达成率，< ratio 退让（尊重引擎）；
            参照制成率≤0（双方都无法成约）时进入段2，避免二值失真。
        段2 决策值（scoring_val → avg_tricks）：比值 < ratio 退让。
        a_make_override：外部口径的动作做成率（v1.93 伙伴侧门控传引牌押注
        方向半桶做成率），非 None 时段1 用它替代动作牌引擎评估值。
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
        am = a_make_override if a_make_override is not None else _make(a)
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

    def _dd_maybe_majority_vote(self, state: PlayState, result: Dict[str, Any],
                                engine_card: Optional[Card]) -> Optional[Card]:
        """多数投票（2026-09-16 方案乙，用户定判据）：飞牌优先，未改选才触发。

        触发条件（全部满足才投票）：
          1. DD_MAJORITY_VOTES > 1（开关；1=关闭保持现状）
          2. 飞牌介入未改选（engine_card == result.card → 飞牌尊重引擎）
          3. "口径矛盾"：非等价候选按做成率 vs 按赢墩排出的 top 组不同
             —— 做成率榜第一组 ≠ 赢墩榜第一组，说明"到底谁好"取决于
             看哪个指标，此局面值得多采几票（用户定调，无阈值）。
             （等价候选按逐世界 scores 全等进同一组——KQJ连张/中间牌已出
               的KJ 不算对手，不触发）
        每票＝一次独立 search（内部自重新采样，按面板计分制选牌），取多数。
        返回 None 表示不触发（照常单次结果）；否则返回多数票牌。
        """
        if (self.dd_majority_votes if hasattr(self, "dd_majority_votes")
                else DD_MAJORITY_VOTES) <= 1:
            print(f"[VOTE-DBG] 票数≤1关闭 mv={getattr(self, 'dd_majority_votes', '<absent>')} cfg={DD_MAJORITY_VOTES}")
            return None
        card = result.get("card")
        if card is None or engine_card is None or card != engine_card:
            print(f"[VOTE-DBG] 前置拦截 card={card} eng={engine_card} mv={getattr(self,'dd_majority_votes','<absent>')} cfg={DD_MAJORITY_VOTES}")
            return None  # 飞牌已改选/无牌：飞牌优先，不票选
        cands = (result.get("full_output") or {}).get("mcts_stats", {}).get("candidates") or []
        if len(cands) < 2:
            print(f"[VOTE-DBG] 候选数<2 ncand={len(cands)}")
            return None

        # ── 等价分组：逐世界 scores 全等视为同一组（代表=第一张遇到的）──
        groups = []
        for cc in cands:
            sa = cc.get("scores") or []
            if not sa:
                groups.append([cc])
                continue
            placed = False
            for g in groups:
                gs = g[0].get("scores") or []
                if len(gs) == len(sa) and all(x == y for x, y in zip(gs, sa)):
                    g.append(cc)
                    placed = True
                    break
            if not placed:
                groups.append([cc])
        if len(groups) < 2:
            print(f"[VOTE-DBG] 全部等价 ngroups={len(groups)}")
            return None  # 全部等价：无对手可比较，不触发

        def grp_make(g):
            return max((cc.get("make_rate_val") or 0.0) for cc in g)
        def grp_avg(g):
            return max((cc.get("avg_tricks") or 0.0) for cc in g)

        by_make = sorted(groups, key=lambda g: -grp_make(g))
        by_avg = sorted(groups, key=lambda g: -grp_avg(g))
        top_make_cards = {str(cc["card"]) for cc in by_make[0]}
        top_avg_cards = {str(cc["card"]) for cc in by_avg[0]}
        print(f"[VOTE-DBG] ngroups={len(groups)} make_top={top_make_cards} avg_top={top_avg_cards} "
              f"scores全等组数={len(groups)}")
        if top_make_cards == top_avg_cards:
            return None  # 两口径一致：做成率高者也赢墩高，无需票选

        # ── 触发票选：每票独立 search（自重新采样，按面板计分制）──
        from collections import Counter
        tally = Counter()
        _votes = (self.dd_majority_votes if hasattr(self, "dd_majority_votes")
                  else DD_MAJORITY_VOTES)
        for _ in range(_votes):
            r = self.dd_search.search(state)
            rc = r.get("card")
            if rc is not None:
                tally[str(rc)] += 1
        winner_str = tally.most_common(1)[0][0]
        # 从候选列表确认多数牌合法存在（engine.get_playable_cards 依赖出牌方
        # 前置状态，此时可能为空；候选本身即 search 的合法出牌）
        if not any(str(cc["card"]) == winner_str
                   for cc in (result.get("full_output") or {})
                   .get("mcts_stats", {}).get("candidates") or []):
            return None
        winner = self._card_from_str(state, winner_str)
        if winner is None:
            return None
        print(f"[DD多数投票] {_votes}票 口径矛盾"
              f"(做成率{str(list(top_make_cards))} vs 赢墩{str(list(top_avg_cards))}) "
              f"→ 多数{winner} 分布{dict(tally)}")
        return winner

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
            engine_card = card  # 飞牌介入前的引擎牌（判定飞牌是否改选）
            full_output = result.get("full_output", {})
            full_output["叫牌约束"] = self._format_constraints_for_display(constraints)
            full_output["最新约束"] = self._format_latest_constraints_for_display(state, constraints)
            self._inject_played_stats(full_output, state)
            full_output["engine_phase"] = "midgame_dd"
            # 介入层（v1.84：独立于引擎的统一管线，传入 DD 比值）。
            # 9砸 与飞牌介入为并列规则分支，按序裁定、先命中先赢。
            # DD 单独开关（运行时切换，不影响 αμ）：DD_FINESSE_ENABLE=False 时
            # DD 引擎不带任何介入——9砸/窗口期启动/接应全不介入，仅按引擎得分选牌。
            import config as _svc_config
            if _svc_config.DD_FINESSE_ENABLE:
                result = self._intervene(state, result, FINESSE_RATIO)
            card = result.get("card")
            # 平局多数投票（2026-09-16 方案乙）：飞牌优先——飞牌已改选则
            # 不再票选；只有飞牌尊重引擎时，才在"top 与首个非等价对手
            # 做成率差 ≤ 阈值"时触发多票多数（每票独立 search 自重新采样）。
            vote_card = self._dd_maybe_majority_vote(state, result, engine_card)
            if vote_card is not None:
                card = vote_card
                result["card"] = vote_card
                _votes = (self.dd_majority_votes if hasattr(self, "dd_majority_votes")
                          else DD_MAJORITY_VOTES)
                result["reasoning"] = (result.get("reasoning") or "") + \
                    f" [多数投票{_votes}票: {vote_card}]"
                full_output["推荐出牌"] = str(vote_card)
                full_output["多数投票"] = {"票数": _votes,
                                           "结果": str(vote_card)}
            return {
                "card": card.to_dict() if card else None,
                "reasoning": result.get("reasoning", ""),
                "full_output": full_output,
                "prompt": "[DD] no prompt",
            }
        except Exception as e:
            import traceback as _tb
            print(f"[DD_ERROR] {type(e).__name__}: {e}")
            _tb.print_exc()
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

    @staticmethod
    def _card_from_str(state: PlayState, card_str: str) -> Optional[Card]:
        """从字符串（如 ♦K）在庄家/明手手牌中找对应 Card 对象。

        多数投票的赢家在 search 候选里已知合法，但 engine.get_playable_cards()
        依赖出牌方前置状态可能为空；从手牌直接构造即可（出牌方=当前玩家，
        其手牌必含该合法出牌）。
        """
        if not card_str:
            return None
        cstr = card_str.strip().upper()
        import re as _re
        m = _re.match(r'([♠♥♦♣])([AKQJT98765432])', cstr)
        if not m:
            return None
        suit, rank = m.group(1), m.group(2)
        for card in state.hands.get(state.current_player, []):
            if card.suit == suit and card.rank == rank:
                return card
        # 兜底：明手（若当前方是明手由庄家代出，手牌在 dummy）
        for card in state.hands.get(state.dummy or "", []):
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