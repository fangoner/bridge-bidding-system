import asyncio
import json
import re
from typing import Optional, Dict, List, Any, Tuple

from bridge.play_types import Card, PlayState, PlayPhase, POSITION_ORDER, PARTNERS
from bridge.play_engine import PlayEngine
from llm.prompts import PLAY_COMMON_RULES, PLAY_COMMON_SITUATION, PLAY_DECLARER_PROMPT, PLAY_DEFENDER_PROMPT
from bridge.mcts import MctsSearch, RandomizedRollout, DDSearch
from bridge.mcts.constraints import BidConstraint, validate_sample
from bridge.mcts.bid_constraint_library import extract_constraints_from_bid_history, SYSTEM_JF
from config import (
    MCTS_ITERATIONS, MCTS_TIME_LIMIT, MCTS_EXPLORATION_CONSTANT,
    ROLLOUT_GREEDY_PROB, MCTS_SEARCH_MODE, DD_NUM_SAMPLES, DD_MIN_SAMPLES, DD_TIME_LIMIT,
    DD_ENDGAME_CARD_THRESHOLD, DD_ENDGAME_MAX_ENUMERATIONS,
    DD_MAXIMIN_ENABLE,
    TIERED_CRITICAL_SPREAD_DECLARER, TIERED_CRITICAL_SPREAD_DEFENDER,
    TIERED_ENDGAME_CARDS, TIERED_MIN_SAMPLES, TIERED_OVERRIDE_THRESHOLD,
    TIERED_FUSION_SPREAD, TIERED_CLUSTER_SE, TIERED_TYPICAL_SD,
    TIERED_MCTS_CLUSTER_THRESHOLD,
    ALPHA_MU_ENABLE, ALPHA_MU_ENDGAME_CARDS, ALPHA_MU_NUM_WORLDS,
    ALPHA_MU_MAX_DEPTH, ALPHA_MU_TIME_LIMIT, ALPHA_MU_M,
)


class PlayService:

    def __init__(self, llm_client):
        self.llm_client = llm_client
        self.engine = PlayEngine()
        # 做庄计划：庄家和明手之间共享传递（结构化）
        self.declarer_plan = self._empty_plan()
        # 防守计划：每个防守者各自维护，key=位置
        self.defender_plans = {}
        # MCTS搜索器（始终初始化，按需使用）
        self.mcts = MctsSearch(
            iterations=MCTS_ITERATIONS,
            time_limit=MCTS_TIME_LIMIT,
            exploration=MCTS_EXPLORATION_CONSTANT,
            rollout=RandomizedRollout(greedy_prob=ROLLOUT_GREEDY_PROB),
        )
        # DD搜索器（纯蒙特卡洛 + 双明手评估）
        self.dd_search = DDSearch(
            num_samples=DD_NUM_SAMPLES,
            min_samples=DD_MIN_SAMPLES,
            time_limit=DD_TIME_LIMIT,
            endgame_card_threshold=DD_ENDGAME_CARD_THRESHOLD,
            max_enumerations=DD_ENDGAME_MAX_ENUMERATIONS,
            use_maximin=DD_MAXIMIN_ENABLE,
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
        self.bid_constraints = None  # 延迟提取
        # Phase 0a: BeliefTracker 已移除，粒子缓存不再需要清理

        return self.engine.initialize(hands, contract, player_roles, bidding_sequence)
    
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
                          use_mcts: bool = False,
                          use_dd: bool = False,
                          use_tiered: bool = False,
                          use_perfect: bool = False,
                          use_alphamu: bool = False,
                          use_alphamu_llm: bool = False,
                          dd_samples: int = None) -> Dict[str, Any]:
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

        # === Tiered 分层引擎分支 ===
        if use_tiered:
            return await asyncio.to_thread(self._tiered_play, state, dd_samples, use_reasoning)

        # === Perfect DD 引擎分支（全知双明手） ===
        if use_perfect:
            return await asyncio.to_thread(self._perfect_play, state)

        # === DD 引擎分支 ===
        if use_dd:
            return await asyncio.to_thread(self._dd_play, state, dd_samples)

        # === αμ 纯引擎分支（从开局到残局全覆盖） ===
        if use_alphamu:
            return await asyncio.to_thread(self._alpha_mu_play, state)

        # === αμ + LLM策略审查分支 ===
        if use_alphamu_llm:
            return await asyncio.to_thread(self._alphamu_llm_play, state, use_reasoning)

        # === MCTS 引擎分支 ===
        if use_mcts:
            return await asyncio.to_thread(self._mcts_play, state)

        # === LLM 引擎分支 ===
        return await asyncio.to_thread(self._llm_play, state, use_reasoning)

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

    def _tiered_play(self, state: PlayState, dd_samples: int = None,
                     use_reasoning: bool = False) -> Dict[str, Any]:
        """分层引擎：按牌局阶段选择最优引擎。

        Phase 1 — 通用 (tricks≥0, cards>8): DD 采样 + 三信号升级 LLM
          Phase 2 — 残局 (cards≤8): αμ 搜索 → DD 枚举回退
          DirectDDS 总是可用（ctypes 直调 dds.dll）
        """
        perspective = state.current_player
        declarer = state.contract.declarer
        dummy = state.dummy
        is_declarer_side = perspective in (declarer, dummy)

        cards_in_hand = len(state.hands.get(perspective, []))

        # ═══════════════════════════════════════════════════════════
        # Phase 1: 通用 — DD 采样 + 关键决策升级 LLM
        # ═══════════════════════════════════════════════════════════
        if cards_in_hand > ALPHA_MU_ENDGAME_CARDS:
            dd_result = self._dd_play(state, dd_samples)
            critical_reason = self._is_critical_decision(dd_result, state, is_declarer_side)
            if critical_reason:
                dd_candidates = (dd_result.get("full_output", {})
                                 .get("mcts_stats", {}).get("candidates", []))
                llm_result = self._llm_play_with_dd_hint(
                    state, use_reasoning=use_reasoning,
                    dd_candidates=dd_candidates, critical_reason=critical_reason)
                llm_result.setdefault("full_output", {})["tiered_phase"] = "critical"
                llm_result["tiered_dd_fallback"] = dd_result
                llm_result["full_output"]["mcts_stats"] = (
                    dd_result.get("full_output", {}).get("mcts_stats", {})
                )
                return llm_result

            dd_result.setdefault("full_output", {})["tiered_phase"] = "midgame"
            return dd_result

        # ═══════════════════════════════════════════════════════════
        # Phase 2: 残局 — αμ 多步前瞻 或 DD 精确枚举 或 DD 采样兜底
        # ═══════════════════════════════════════════════════════════
        if self.alpha_mu_search is not None and ALPHA_MU_ENABLE:
            result = self._alpha_mu_play(state)
            result.setdefault("full_output", {})["tiered_phase"] = "endgame_alpha_mu"
            return result
        if cards_in_hand <= TIERED_ENDGAME_CARDS:
            result = self._dd_play(state, dd_samples)
            result.setdefault("full_output", {})["tiered_phase"] = "endgame"
            return result
        # cards 7-8 且 αμ 不可用 → DD 采样兜底
        result = self._dd_play(state, dd_samples)
        result.setdefault("full_output", {})["tiered_phase"] = "endgame"
        return result

    def _is_critical_decision(self, dd_result: dict, state: PlayState,
                              is_declarer_side: bool) -> Optional[str]:
        """检测DD结果是否为关键决策点（需要升级LLM）。

        三信号检测（替代旧固定阈值）：
        信号1: Strategy Fusion — 候选牌 min-max 跨度≥阈值，且与#1均值在集群内
        信号2: 候选集群 — 用动态标准误 SE=SD/√N 替代固定阈值，距#1在 N×SE 内的牌≥2张
        信号3: 定约边缘 — 庄家还需≤1墩成约 / 防守方还需≤1墩击垮
        """
        candidates = (dd_result.get("full_output", {})
                      .get("mcts_stats", {})
                      .get("candidates", []))

        if not candidates or len(candidates) < 2:
            return None

        # 检查有效样本量
        top_samples = candidates[0].get("samples", 0)
        if top_samples < TIERED_MIN_SAMPLES:
            return None  # 统计不可靠，不升级

        side = "庄家方" if is_declarer_side else "防守方"
        top1 = candidates[0]
        top1_avg = top1.get("avg_tricks", 0)

        # ── 信号1: Strategy Fusion 检测 ──
        # 遍历 top 候选，若某牌 min-max 跨度≥FUSION_SPREAD 且与 #1 均值差在集群范围内 → 触发
        for cand in candidates[:3]:  # 只看前3个候选，避免噪声
            mn = cand.get("min_tricks")
            mx = cand.get("max_tricks")
            if mn is None or mx is None:
                continue
            fusion_spread = mx - mn
            if fusion_spread >= TIERED_FUSION_SPREAD:
                # 该牌与 #1 的均值差需在集群范围内（即也是真正的竞争者）
                gap_to_top1 = abs(cand.get("avg_tricks", 0) - top1_avg)
                # 用动态 SE 作为集群边界
                se = self._estimate_se(top_samples)
                cluster_margin = TIERED_CLUSTER_SE * se
                if gap_to_top1 <= cluster_margin:
                    return (f"{side}Strategy Fusion信号：{cand['card']} "
                            f"min-max跨度{fusion_spread}墩≥{TIERED_FUSION_SPREAD} "
                            f"({cand.get('avg_tricks',0):.1f}[{mn}-{mx}])，"
                            f"与最优{top1['card']}({top1_avg:.1f})差{gap_to_top1:.2f}"
                            f"≤集群边界{cluster_margin:.2f}，升级LLM深度推理")

        # ── 信号2: 候选集群检测（动态标准误） ──
        # SE = SD/√N，距 #1 在 N×SE 内的牌视为"不可区分"，≥2张牌在集群内 → 触发
        se = self._estimate_se(top_samples)
        cluster_margin = TIERED_CLUSTER_SE * se
        cluster_members = [top1]
        for cand in candidates[1:]:
            gap = abs(cand.get("avg_tricks", 0) - top1_avg)
            if gap <= cluster_margin:
                cluster_members.append(cand)

        if len(cluster_members) >= 2:
            cluster_str = ", ".join(
                f"{c['card']}({c.get('avg_tricks',0):.1f})"
                for c in cluster_members[:4]
            )
            return (f"{side}候选集群信号：{len(cluster_members)}张牌在动态SE边界"
                    f"{cluster_margin:.2f}墩内（SE={se:.2f}, N={top_samples}），"
                    f"难以区分优劣：{cluster_str}，升级LLM深度推理")

        # ── 信号3: 定约/击败定约岌岌可危 ──
        tricks_needed = state.contract.tricks_needed
        remaining_tricks = 13 - len(state.tricks)

        if is_declarer_side:
            declarer_needs = tricks_needed - state.declarer_tricks
            if 0 < declarer_needs <= 1 and remaining_tricks > 0:
                return (f"庄家还需{declarer_needs}墩完成定约，"
                        f"剩余{remaining_tricks}墩，每墩皆关键，升级LLM深度推理")
        else:
            tricks_to_beat = 14 - tricks_needed
            defender_needs = tricks_to_beat - state.defender_tricks
            if 0 < defender_needs <= 1 and remaining_tricks > 0:
                return (f"防守方还需{defender_needs}墩击败定约，"
                        f"剩余{remaining_tricks}墩，每墩皆关键，升级LLM深度推理")

        return None

    @staticmethod
    def _estimate_se(n_samples: int) -> float:
        """估计 solve_board 赢墩均值的标准误。

        solve_board 赢墩的典型标准差约 1.5 墩（单套打法 min-max 通常≤2墩）。
        SE = SD / √N，N=30 → 0.27，N=100 → 0.15，N=200 → 0.11。
        """
        if n_samples <= 0:
            return TIERED_TYPICAL_SD  # 退化情况，给最大 SE
        return TIERED_TYPICAL_SD / (n_samples ** 0.5)

    def _is_critical_decision_mcts(self, mcts_result: dict, state: PlayState,
                                   is_declarer_side: bool) -> Optional[str]:
        """MCTS回退模式下的关键决策检测。

        MCTS rollout 的 min/max 不如 solve_board 可靠，只用：
        - 固定集群阈值检测（TIERED_MCTS_CLUSTER_THRESHOLD）
        - 定约边缘检测
        """
        candidates = (mcts_result.get("full_output", {})
                      .get("mcts_stats", {})
                      .get("candidates", []))

        side = "庄家方" if is_declarer_side else "防守方"

        # 集群检测：固定阈值，距 #1 在阈值内的牌≥2张 → 触发
        if len(candidates) >= 2:
            top1_avg = candidates[0].get("avg_tricks", 0)
            cluster_members = [candidates[0]]
            for cand in candidates[1:]:
                gap = abs(cand.get("avg_tricks", 0) - top1_avg)
                if gap <= TIERED_MCTS_CLUSTER_THRESHOLD:
                    cluster_members.append(cand)

            if len(cluster_members) >= 2:
                cluster_str = ", ".join(
                    f"{c['card']}({c.get('avg_tricks',0):.1f})"
                    for c in cluster_members[:4]
                )
                return (f"{side}MCTS候选集群：{len(cluster_members)}张牌在"
                        f"{TIERED_MCTS_CLUSTER_THRESHOLD}墩阈值内难以区分：{cluster_str}，"
                        f"升级LLM深度推理")

        # 定约边缘检测
        tricks_needed = state.contract.tricks_needed
        remaining_tricks = 13 - len(state.tricks)

        if is_declarer_side:
            declarer_needs = tricks_needed - state.declarer_tricks
            if 0 < declarer_needs <= 1 and remaining_tricks > 0:
                return (f"庄家还需{declarer_needs}墩完成定约，升级LLM深度推理")
        else:
            tricks_to_beat = 14 - tricks_needed
            defender_needs = tricks_to_beat - state.defender_tricks
            if 0 < defender_needs <= 1 and remaining_tricks > 0:
                return (f"防守方还需{defender_needs}墩击败定约，升级LLM深度推理")

        return None

    def _llm_play_with_dd_hint(self, state: PlayState, use_reasoning: bool = False,
                                dd_candidates: list = None,
                                critical_reason: str = None) -> Dict[str, Any]:
        """LLM打牌 + DD候选提示。当DD不确定时，将DD候选注入LLM prompt，
        并在LLM选择明显偏离DD最优时否决LLM。"""
        # 构建DD提示文本
        dd_hint = ""
        if dd_candidates:
            cand_str = ", ".join(
                f"{c['card']}({c.get('avg_tricks', 0):.1f}墩)"
                for c in dd_candidates[:5]
            )
            dd_hint = (
                f"\n\n## DD双明手分析参考\n"
                f"DD分析认为以下候选牌的期望墩数接近，难以区分优劣：{cand_str}\n"
                f"原因：{critical_reason or '候选分差小'}\n"
                f"请优先从上述DD候选中选择，或说明为何选择其他牌。"
            )

        result = self._llm_play(state, use_reasoning=use_reasoning,
                                extra_prompt=dd_hint)

        # 保存 DD 注入提示供前端展示
        if dd_hint:
            result.setdefault("full_output", {})["dd_hint"] = dd_hint.strip()

        # 否决检查：如果LLM选的牌与DD最优差距过大，改用DD选择
        if dd_candidates and result.get("card"):
            llm_card_str = f"{result['card']['suit']}{result['card']['rank']}"
            dd_best = dd_candidates[0]
            dd_best_str = dd_best["card"]
            dd_best_avg = dd_best.get("avg_tricks", 0)

            # 找LLM选的牌在DD候选中的排名
            llm_in_dd = None
            for c in dd_candidates:
                if c["card"] == llm_card_str:
                    llm_in_dd = c
                    break

            if llm_in_dd is None and dd_best_avg > 0:
                # LLM选了DD候选范围外的牌，检查差距
                # 用DD最优的期望墩数作为基准，LLM选的牌不在候选中意味着DD认为它更差
                result["reasoning"] = (
                    f"[DD否决] LLM选择{llm_card_str}不在DD候选中，"
                    f"DD最优{dd_best_str}({dd_best_avg:.1f}墩)\n"
                    f"{result.get('reasoning', '')}"
                )
                # 不自动否决，但标记警告

            elif llm_in_dd is not None:
                llm_avg = llm_in_dd.get("avg_tricks", 0)
                gap = dd_best_avg - llm_avg
                if gap > TIERED_OVERRIDE_THRESHOLD:
                    # LLM选的牌与DD最优差距过大，否决LLM
                    print(f"[Tiered] 否决LLM选择{llm_card_str}({llm_avg:.1f}墩)，"
                          f"改用DD最优{dd_best_str}({dd_best_avg:.1f}墩)，差距{gap:.1f}墩")
                    # 从playable中找到DD最优牌
                    playable = self.engine.get_playable_cards()
                    dd_card = None
                    for c in playable:
                        if str(c) == dd_best_str:
                            dd_card = c
                            break
                    if dd_card:
                        dd_card, dd_validation = self._validate_and_fallback(
                            dd_card, playable, state)
                        result["card"] = dd_card.to_dict()
                        reasoning_prefix = (
                            f"[DD否决LLM] LLM选{llm_card_str}({llm_avg:.1f}墩)与DD最优"
                            f"{dd_best_str}({dd_best_avg:.1f}墩)差距{gap:.1f}墩>{TIERED_OVERRIDE_THRESHOLD}，"
                            f"采用DD选择"
                        )
                        if dd_validation:
                            reasoning_prefix += f" (规则校验: {dd_validation})"
                        result["reasoning"] = (
                            f"{reasoning_prefix}\n{result.get('reasoning', '')}"
                        )

        return result

    BID_CONSTRAINT_PROMPT = """从叫牌历史中提取每名牌手透露的点力范围和花色张数约束。

叫牌历史（格式：(位置)叫品：含义）：
{bid_history}

对每名牌手（南/西/北/东），根据其叫品含义提取：
- min_hcp: 最低点力（无约束填null）
- max_hcp: 最高点力（无约束填null）
- balanced: 均型=true, 非均型=false, 未知=null
- spades_min: S最少张数（无约束填null）
- hearts_min: H最少张数（无约束填null）
- diamonds_min: D最少张数（无约束填null）
- clubs_min: C最少张数（无约束填null）

注意：pass/不叫表示无合格叫品，不代表点力或牌型信息。

仅输出JSON，不要Markdown代码块："""

    def _merge_constraints(self, c1: BidConstraint, c2: BidConstraint) -> BidConstraint:
        """合并两个约束：硬编码约束优先，LLM约束作为补充，取更严格的限制"""
        from bridge.mcts.bid_constraint_library import _merge_constraints
        return _merge_constraints(c1, c2)

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
            {position: BidConstraint}
        """
        import re
        constraints: Dict[str, BidConstraint] = {}

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
            suit_map = {'♠': '♠', '♥': '♥', '♦': '♦', '♣': '♣',
                        'S': '♠', 'H': '♥', 'D': '♦', 'C': '♣'}
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

        return constraints

    def _apply_constraints(self, constraints: Dict[str, BidConstraint], sampler=None) -> None:
        """将约束应用到采样器"""
        target_sampler = sampler or self.dd_search.sampler
        target_sampler.set_constraints(constraints)

    def _get_bid_constraints(self) -> Dict[str, BidConstraint]:
        """从叫牌历史中提取约束：优先硬编码标准叫品表，LLM提取作为补充，结果缓存"""
        if self.bid_constraints is not None:
            return self.bid_constraints

        if not self.bid_history or not self.bid_history.strip():
            self.bid_constraints = {}
            return self.bid_constraints

        # Step 1: 先用硬编码约束库提取确定性约束
        # 规则：提供了叫牌历史 → 按JF约定处理；无叫牌历史 → 返回空约束（普通随机/自然）
        hard_constraints = {}
        try:
            hard_constraints = extract_constraints_from_bid_history(self.bid_history, system=SYSTEM_JF)
            print(f"[DD] 硬编码约束提取(JF体系): { {p: f'HCP{c.min_hcp}-{c.max_hcp}[{c.inference_source}]' for p, c in hard_constraints.items()} }")
        except Exception as e:
            print(f"[DD] 硬编码约束提取失败: {e}")
            hard_constraints = {}

        # Step 2: 从叫牌含义文本中提取约束（复用叫牌阶段LLM已分析的信息）
        constraints = dict(hard_constraints)
        meanings_text = getattr(self, 'bid_meanings', '') or ''

        if meanings_text.strip():
            try:
                meaning_constraints = self._parse_constraints_from_meanings(meanings_text)
                for pos_cn, mc in meaning_constraints.items():
                    if pos_cn in constraints:
                        constraints[pos_cn] = self._merge_constraints(constraints[pos_cn], mc)
                    else:
                        constraints[pos_cn] = mc
                print(f"[DD] 含义文本解析补充约束: { {p: f'HCP{c.min_hcp}-{c.max_hcp}' for p, c in meaning_constraints.items()} }")
            except Exception as e:
                print(f"[DD] 含义文本解析失败: {e}")

        # Step 3: 如果约束仍不完整，用LLM补充
        if not constraints:
            try:
                prompt = self.BID_CONSTRAINT_PROMPT.format(bid_history=self.bid_history)
                print(f"[DD] 调用LLM补充提取约束...")
                result = self.llm_client.chat_json(system_prompt=prompt, temperature=0, max_tokens=1024)

                POS_NAME_MAP = {
                    "南": "南", "西": "西", "北": "北", "东": "东",
                    "south": "南", "west": "西", "north": "北", "east": "东",
                    "s": "南", "w": "西", "n": "北", "e": "东",
                }
                for pos, data in result.get("constraints", result).items():
                    pos_cn = POS_NAME_MAP.get(pos.lower() if isinstance(pos, str) else pos)
                    if pos_cn is None:
                        continue
                    c = BidConstraint(
                        position=pos_cn,
                        min_hcp=data.get("min_hcp"),
                        max_hcp=data.get("max_hcp"),
                        balanced=data.get("balanced"),
                        suit_min={},
                    )
                    for suit in ("♠", "♥", "♦", "♣"):
                        key = {"♠": "spades_min", "♥": "hearts_min",
                               "♦": "diamonds_min", "♣": "clubs_min"}[suit]
                        val = data.get(key)
                        if val is not None and isinstance(val, (int, float)):
                            c.suit_min[suit] = int(val)

                    if pos_cn in constraints:
                        constraints[pos_cn] = self._merge_constraints(constraints[pos_cn], c)
                    else:
                        constraints[pos_cn] = c

                print(f"[DD] 最终合并约束: { {p: f'HCP{c.min_hcp}-{c.max_hcp}, suits={dict(c.suit_min)}' for p, c in constraints.items()} }")
            except Exception as e:
                import traceback
                print(f"[MCTS] LLM约束补充提取失败: {e}，使用纯硬编码约束")
                traceback.print_exc()
            self.bid_constraints = hard_constraints
            return hard_constraints

        # 一二层已产出约束，缓存并返回
        self.bid_constraints = constraints
        return constraints

    def _alpha_mu_play(self, state: PlayState) -> Dict[str, Any]:
        """αμ 引擎（论文实现，纯αμ无回退）。

        M 值由 ALPHA_MU_M 配置（默认 2），全程不降级。
        注意：牌数多时 M=2 会非常慢（13 张牌约 30s+），研究用途可接受。
        """
        from bridge.mcts.alpha_mu import AlphaMuSearch

        perspective = state.current_player
        cards = len(state.hands.get(perspective, []))

        base_worlds = ALPHA_MU_NUM_WORLDS
        # 世界数随牌数减少而增加（残局越小，采样越精确）
        if cards <= 4:
            n_worlds = min(100, base_worlds * 5)
        elif cards <= 6:
            n_worlds = min(60, base_worlds * 3)
        elif cards <= 8:
            n_worlds = min(30, base_worlds * 2)
        else:
            n_worlds = min(20, base_worlds)
        M_value = ALPHA_MU_M

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

        # 创建临时搜索器（复用 dd_search 的 sampler + 约束）
        constraints = self._get_bid_constraints()
        if constraints:
            self._apply_constraints(constraints)

        search = AlphaMuSearch(
            sampler=self.dd_search.sampler,
            num_worlds=n_worlds,
            M=M_value,
            time_limit=time_lim,
            dds_budget=dds_budget,
        )

        result = search.search(state)
        card = result.get("card")
        if card is None:
            # αμ 无结果时选第一张合法牌（不静默回退其他引擎）
            playable = self.engine.get_playable_cards()
            card = playable[0] if playable else None
        full_output = result.get("full_output", {})
        full_output["叫牌约束"] = self._format_constraints_for_display(constraints)
        return {
            "card": card.to_dict() if hasattr(card, "to_dict") else None,
            "reasoning": result.get("reasoning", ""),
            "full_output": full_output,
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

        # Step 2: 按 best_vector 分组
        trump_suit = state.contract.suit if state.contract.suit != "NT" else ""
        groups = self._group_candidates_by_vector(candidates, trump_suit=trump_suit)
        desperation_mode = False
        if not self._should_trigger_llm(groups, candidates):
            all_zero = candidates and all(c.get("success_rate", 0) == 0 for c in candidates)
            if all_zero and len(candidates) >= 2:
                groups = self._build_desperation_groups(candidates, trump_suit=trump_suit)
                if len(groups) < 2:
                    return alpha_result
                desperation_mode = True
                print(f"[αμ+LLM] 绝望模式：αμ认为无成约机会，LLM审查{len(groups)}组、力争多拿墩少宕")
            else:
                return alpha_result

        # 仅庄家方触发
        declarer = state.contract.declarer
        dummy = state.dummy
        if state.current_player not in (declarer, dummy):
            return alpha_result

        # 检测plan是否失效，失效则清空（强制LLM重新制定）
        if self._check_plan_invalidation(state):
            print(f"[αμ+LLM] 检测到plan失效，清空旧计划")
            self.declarer_plan = self._empty_plan()

        # Step 3: LLM分组审查
        alpha_card_str = full_output.get("推荐出牌", "")
        review = self._llm_group_review(state, candidates, groups,
                                         alpha_card=alpha_card_str,
                                         previous_plan=self._format_plan_for_prompt(self.declarer_plan),
                                         desperation=desperation_mode)
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
            # 按规则从组内选牌
            playable = self.engine.get_playable_cards()
            playable_strs = {str(c): c for c in playable}
            group_playable = [c for c in chosen_group["cards"] if c.get("card", "") in playable_strs]
            if group_playable:
                # 当前玩家是明手 → 选最小；否则选最大
                is_dummy_turn = (state.current_player == dummy)
                if is_dummy_turn:
                    target_card_str = min(group_playable, key=lambda c: self._extract_rank(c.get("card", "")))["card"]
                else:
                    target_card_str = max(group_playable, key=lambda c: self._extract_rank(c.get("card", "")))["card"]

                target = playable_strs.get(target_card_str)
                if target:
                    target, validation = self._validate_and_fallback(target, playable, state)
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

    def _build_plan_from_review(self, review: dict, trick_number: int) -> dict:
        """从LLM审查结果构建结构化plan。

        LLM输出的plan可能是字符串或含steps的结构。
        统一转为结构化dict存储。
        """
        plan = self._empty_plan()
        plan["created_at_trick"] = trick_number
        plan["last_validated_trick"] = trick_number

        raw = review.get("plan", "")
        steps = review.get("steps", [])

        if isinstance(raw, str) and raw:
            plan["raw_text"] = raw
        if isinstance(steps, list) and steps:
            plan["steps"] = steps
        elif isinstance(raw, str) and raw:
            # 没有结构化steps，尝试简单解析（按句号/分号分割）
            sentences = [s.strip() for s in raw.replace("；", "。").split("。") if s.strip()]
            plan["steps"] = [
                {"step": i + 1, "action": s, "precondition": "", "completed": False}
                for i, s in enumerate(sentences[:6])  # 最多6步
            ]
        return plan

    def _check_plan_invalidation(self, state: PlayState) -> bool:
        """检测当前plan是否失效。

        失效条件：
        0. 所有步骤都已完成 → 计划执行完毕，失效
        1. plan中提到的大牌已出（如"飞♠K"但♠K已出）
        2. plan创建后已过太多墩（>4墩未更新）
        3. 未完成步骤的前提条件不满足（如关键大牌已出）

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

        for s in steps:
            if s.get("completed"):
                continue
            action = s.get("action", "")
            precondition = s.get("precondition", "")

            check_text = action + " " + precondition
            key_cards = ["♠A", "♠K", "♠Q", "♠J", "♠T",
                         "♥A", "♥K", "♥Q", "♥J", "♥T",
                         "♦A", "♦K", "♦Q", "♦J", "♦T",
                         "♣A", "♣K", "♣Q", "♣J", "♣T"]
            for card in key_cards:
                if card in check_text and card in played_cards:
                    return True

        return False

    def _mark_step_completed(self, played_card: str, trick_number: int) -> bool:
        """出牌后标记plan中匹配的步骤为完成。

        在第一个未完成的步骤的action中查找played_card，
        如果匹配则标记completed=True。
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
            action = s.get("action", "")
            if played_card in action:
                s["completed"] = True
                plan["last_validated_trick"] = trick_number
                print(f"[αμ+LLM] plan步骤{s.get('step', '?')}完成: {action[:40]}...")
                return True
        return False

    def _should_trigger_llm(self, groups: list, candidates: list = None) -> bool:
        """判断是否需要触发LLM分组审查。

        条件：
        1. 至少2组（有选择空间）
        2. top-1和top-2的成功率差距 < 15%

        如果αμ已明显偏好某组（gap≥15%），则信任αμ、不触发LLM。
        如果αμ分不清（gap<15%），则触发LLM帮忙判断。
        """
        if len(groups) < 2:
            return False
        rates = [g["success_rate"] for g in groups]
        if rates[0] - rates[1] >= 0.15:
            return False
        return True

    def _extract_rank(self, card_str: str) -> int:
        """从牌张代码中提取数字等级。♠2→2, ♥J→11, ♣Q→12, ♦K→13, ♠A→14"""
        rank_str = card_str[1:] if len(card_str) >= 2 else ""
        rank_map = {"2": 2, "3": 3, "4": 4, "5": 5, "6": 6, "7": 7,
                    "8": 8, "9": 9, "T": 10, "10": 10, "J": 11, "Q": 12, "K": 13, "A": 14}
        return rank_map.get(rank_str, 0)

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

    def _build_desperation_groups(self, candidates: list, trump_suit: str = "") -> list:
        """αμ认为无成约机会时，按花色+rank区间构建分组供LLM审查。

        目标是尽可能多拿墩少宕，而不是追求成约。
        """
        if len(candidates) < 2:
            return []
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
                           desperation: bool = False) -> dict:
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
            "你是桥牌做庄专家。αμ引擎已默认选定第1组出牌。"
            + ("αμ搜索已判断无成约机会，目标是**尽可能多拿墩、少宕**。" if desperation else
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
            default_mark = " ← αμ默认选择" if g["group_id"] == 1 else ""
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

        strategy_text = self._build_strategy_text(desperation, is_nt, trump_cleared, loss_analysis)

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
同一组内的牌在αμ采样空间中DDS等价（出哪张结果相同），不同组之间DDS不等价。
分组**不预设战术**——同一组牌既可能用于飞牌，也可能用于清将，也可能用于其他战术。
战术由你根据局面自行判断，不要根据牌张大小臆测战术类别。
**第1组是αμ引擎的默认选择，除非其他组有第1组做不到的战术价值，否则选组1。**
{groups_text}

{plan_section}
## 战略分析
{strategy_text}

## 输出JSON
{{
  "group": 1,（最终选择的组号，无更好选择时填1）
  "plan": "打牌计划简述（一句话概括）",
  "steps": [
    {{"step": 1, "action": "具体动作", "precondition": "前提条件（如某大牌位置、花色分布）"}},
    {{"step": 2, "action": "...", "precondition": "..."}}
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
                              trump_cleared: bool, loss_analysis: str) -> str:
        if desperation:
            return f"""⚠️ αμ搜索已判定无成约机会（所有候选成功率≈0%）。目标是**尽可能多拿墩、少宕**。以下分析框架相应调整：
1. **数赢墩（力争多拿墩）**：逐花色数庄家方能赢的墩数。
   第1组是αμ默认选择，检查第2组及以后是否有组能多拿墩。
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
        lines.append('   **第1组是αμ默认选择，除非非第1组有明确的战术优势，否则选组1。**')
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

    def _dd_play(self, state: PlayState, dd_samples: int = None) -> Dict[str, Any]:
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

        try:
            result = self.dd_search.search(state)
            card = result.get("card")
            if card is None:
                playable = self.engine.get_playable_cards()
                card = self._select_best_card(playable, state)
            full_output = result.get("full_output", {})
            full_output["叫牌约束"] = self._format_constraints_for_display(constraints)
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

    def _mcts_play(self, state: PlayState) -> Dict[str, Any]:
        """MCTS搜索打牌（同步方法，由asyncio.to_thread调用）"""
        # 首次调用时提取叫牌约束
        constraints = self._get_bid_constraints()
        if constraints:
            self._apply_constraints(constraints, self.mcts.sampler)

        # Phase 0a: MCTS 样本数由 config 控制

        try:
            result = self.mcts.search(state)
            card = result.get("card")
            if card is None:
                playable = self.engine.get_playable_cards()
                card = self._select_best_card(playable, state)
            full_output = result.get("full_output", {})
            full_output["叫牌约束"] = self._format_constraints_for_display(constraints)
            return {
                "card": card.to_dict() if card else None,
                "reasoning": result.get("reasoning", ""),
                "full_output": full_output,
                "prompt": "[MCTS] no prompt",
            }
        except Exception as e:
            playable = self.engine.get_playable_cards()
            card = self._select_best_card(playable, state)
            return {
                "card": card.to_dict() if card else None,
                "reasoning": f"MCTS异常，自动选择: {str(e)}",
                "error": str(e),
                "prompt": "[MCTS error]",
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
