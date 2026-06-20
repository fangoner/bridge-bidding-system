import asyncio
import json
import re
from typing import Optional, Dict, List, Any, Tuple

from bridge.play_types import Card, PlayState, PlayPhase, POSITION_ORDER, PARTNERS
from bridge.play_engine import PlayEngine
from llm.prompts import PLAY_COMMON_RULES, PLAY_COMMON_SITUATION, PLAY_DECLARER_PROMPT, PLAY_DEFENDER_PROMPT
from bridge.mcts import MctsSearch, RandomizedRollout, DDSearch
from bridge.mcts.constraints import BidConstraint, validate_sample
from config import (
    MCTS_ITERATIONS, MCTS_TIME_LIMIT, MCTS_EXPLORATION_CONSTANT,
    ROLLOUT_GREEDY_PROB, MCTS_SEARCH_MODE, DD_NUM_SAMPLES, DD_MIN_SAMPLES, DD_TIME_LIMIT,
    DD_ENDGAME_CARD_THRESHOLD, DD_ENDGAME_MAX_ENUMERATIONS,
    TIERED_CRITICAL_SPREAD_DECLARER, TIERED_CRITICAL_SPREAD_DEFENDER,
    TIERED_ENDGAME_CARDS, TIERED_MIN_SAMPLES, TIERED_OVERRIDE_THRESHOLD,
    TIERED_FUSION_SPREAD, TIERED_CLUSTER_SE, TIERED_TYPICAL_SD,
    TIERED_MCTS_CLUSTER_THRESHOLD,
    BELIEF_ENABLE,
    ALPHA_MU_ENABLE, ALPHA_MU_ENDGAME_CARDS, ALPHA_MU_NUM_WORLDS,
    ALPHA_MU_MAX_DEPTH, ALPHA_MU_TIME_LIMIT,
)


class PlayService:

    def __init__(self, llm_client):
        self.llm_client = llm_client
        self.engine = PlayEngine()
        # 做庄计划：庄家和明手之间共享传递
        self.declarer_plan = ""
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
        )
        # 信念跟踪器：粒子滤波采样，缓解 strategy fusion 问题
        if BELIEF_ENABLE:
            from bridge.mcts.belief import BeliefTracker
            self.belief_tracker = BeliefTracker(self.dd_search.sampler)
            self.dd_search.sampler.set_belief_tracker(self.belief_tracker)
            self.mcts.sampler.set_belief_tracker(
                BeliefTracker(self.mcts.sampler)
            )
        else:
            self.belief_tracker = None

        # αμ 搜索器：残局多步前瞻，解决 strategy fusion 和 non-locality
        # 复用 dd_search 的 sampler（含 belief tracker 和约束）
        self.alpha_mu_search = None
        if ALPHA_MU_ENABLE:
            try:
                from bridge.mcts.alpha_mu import AlphaMuSearch, ENDPLAY_AVAILABLE
                if ENDPLAY_AVAILABLE:
                    self.alpha_mu_search = AlphaMuSearch(
                        sampler=self.dd_search.sampler,
                        num_worlds=ALPHA_MU_NUM_WORLDS,
                        max_depth=ALPHA_MU_MAX_DEPTH,
                        time_limit=ALPHA_MU_TIME_LIMIT,
                    )
            except Exception as e:
                print(f"[PlayService] αμ 搜索器初始化失败: {e}")
                self.alpha_mu_search = None
    
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
    ) -> PlayState:
        from bridge.play_types import Contract

        contract = Contract.from_str(contract_str, declarer)
        contract.doubled = doubled
        contract.redoubled = redoubled

        # 重置做庄和防守计划
        self.declarer_plan = ""
        self.defender_plans = {}
        # 缓存叫牌约束（供MCTS采样器使用）
        self.bid_history = bid_history
        self.bid_constraints = None  # 延迟提取
        # 重置信念跟踪器（清空旧粒子，新局开始）
        if self.belief_tracker is not None:
            self.belief_tracker.particles = []
            self.belief_tracker.weights = []

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
                    self.declarer_plan = ""
            
            # 如果墩数回退（从已完成墩恢复），清空所有计划
            if tricks_after < tricks_before:
                self.declarer_plan = ""
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

        if not playable_cards:
            # _select_best_card 需要 playable，此情况不应出现在正常流程中
            return {"error": "没有可出的牌"}

        hands_info = self._format_hands_info(state)
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
            previous_plan = f"## 上一轮做庄进度与调整\n{self.declarer_plan}" if self.declarer_plan else "（首轮出牌，尚无做庄计划）"
        else:
            prev = self.defender_plans.get(current_player, "")
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

        # 防守方：注入同伴已发防守信号
        if not is_declarer_side:
            try:
                from bridge.mcts.signals import format_partner_signals_for_prompt
                signal_prompt = format_partner_signals_for_prompt(state, current_player)
                if signal_prompt:
                    prompt += signal_prompt
            except Exception as e:
                print(f"[Play] 信号注入失败: {e}")

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
                if is_declarer_side:
                    self.declarer_plan = candidate_analysis
                else:
                    self.defender_plans[current_player] = candidate_analysis

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
        """分层引擎：根据局面阶段自动选择最优引擎。

        阶段判定（按优先级）：
        1. 首攻 (LEAD) → LLM reasoning（首攻策略性强）
        2. 明手亮开 (DUMMY_REVEAL) → LLM reasoning
        3. 残局 (cards/hand <= 6) → DD 精确枚举
        4. 中盘 → DD采样 + 关键决策升级LLM
        5. endplay不可用时 → MCTS回退
        """
        from bridge.mcts.dd_search import ENDPLAY_AVAILABLE

        perspective = state.current_player
        declarer = state.contract.declarer
        dummy = state.dummy
        is_declarer_side = perspective in (declarer, dummy)

        cards_in_hand = len(state.hands.get(perspective, []))

        # Phase 1: 首攻（防守方第一张牌，策略性强）
        # 并行跑 DD 蒙特卡洛（期望墩数 + min-max 区间）和 LLM（战略性首攻）
        # LLM 拿到 DD 统计后做最终选择
        if state.phase == PlayPhase.LEAD:
            result = self._opening_lead_play(state, use_reasoning)
            result.setdefault("full_output", {})["tiered_phase"] = "opening_lead"
            return result

        # Phase 2: 明手亮开（第二家出牌，需要理解首攻信号）
        if state.phase == PlayPhase.DUMMY_REVEAL:
            result = self._llm_play(state, force_reasoning=True)
            result.setdefault("full_output", {})["tiered_phase"] = "dummy_reveal"
            return result

        # Phase 3: 残局 → αμ 多步前瞻（≤8张）或 DD 精确枚举（≤6张）
        if cards_in_hand <= ALPHA_MU_ENDGAME_CARDS and ENDPLAY_AVAILABLE:
            # 优先 αμ：解决 strategy fusion，多步前瞻
            if self.alpha_mu_search is not None and ALPHA_MU_ENABLE:
                result = self._alpha_mu_play(state)
                result.setdefault("full_output", {})["tiered_phase"] = "endgame_alpha_mu"
                return result
            # αμ 不可用，回退 DD 精确枚举
            if cards_in_hand <= TIERED_ENDGAME_CARDS:
                result = self._dd_play(state, dd_samples)
                result.setdefault("full_output", {})["tiered_phase"] = "endgame"
                return result

        # Phase 4: 中盘 → DD采样 + 关键决策升级LLM
        if ENDPLAY_AVAILABLE:
            dd_result = self._dd_play(state, dd_samples)
            critical_reason = self._is_critical_decision(dd_result, state, is_declarer_side)
            if critical_reason:
                # DD不确定，升级到LLM，并注入DD候选信息
                dd_candidates = (dd_result.get("full_output", {})
                                 .get("mcts_stats", {}).get("candidates", []))
                llm_result = self._llm_play_with_dd_hint(
                    state, use_reasoning=use_reasoning,
                    dd_candidates=dd_candidates, critical_reason=critical_reason)
                llm_result.setdefault("full_output", {})["tiered_phase"] = "critical"
                llm_result["tiered_dd_fallback"] = dd_result
                # 保留DD统计数据供前端展示
                llm_result["full_output"]["mcts_stats"] = (
                    dd_result.get("full_output", {}).get("mcts_stats", {})
                )
                return llm_result

            dd_result.setdefault("full_output", {})["tiered_phase"] = "midgame"
            return dd_result
        else:
            # endplay不可用，回退MCTS
            mcts_result = self._mcts_play(state)
            critical_reason = self._is_critical_decision_mcts(mcts_result, state, is_declarer_side)
            if critical_reason:
                mcts_candidates = (mcts_result.get("full_output", {})
                                   .get("mcts_stats", {}).get("candidates", []))
                mcts_summary = ", ".join(
                    f"{c['card']}({c.get('avg_tricks', 0):.1f})"
                    for c in mcts_candidates[:3]
                ) if mcts_candidates else "无候选数据"

                llm_result = self._llm_play(state, use_reasoning=use_reasoning)
                llm_result.setdefault("full_output", {})["tiered_phase"] = "critical_mcts"
                llm_result["tiered_mcts_fallback"] = mcts_result
                llm_result["reasoning"] = (
                    f"[MCTS分析] {critical_reason}\n"
                    f"MCTS候选: {mcts_summary}\n"
                    f"--- 升级 LLM 深度推理 ---\n"
                    f"{llm_result.get('reasoning', '')}"
                )
                llm_result["full_output"]["mcts_stats"] = (
                    mcts_result.get("full_output", {}).get("mcts_stats", {})
                )
                return llm_result

            mcts_result.setdefault("full_output", {})["tiered_phase"] = "midgame_mcts"
            return mcts_result

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

    def _opening_lead_play(self, state: PlayState, use_reasoning: bool = False) -> Dict[str, Any]:
        """首攻阶段：DD 蒙特卡洛 + LLM 战略性首攻融合。

        流程：
        1. DD 跑蒙特卡洛，得到各候选首攻的期望墩数 + min-max 区间
        2. LLM 拿到 DD 统计后做战略性首攻选择（复用 _apply_dd_override）
        3. LLM 选择与 DD 最优差距过大时否决回退 DD

        首攻特殊性：DD 是双明手（假设防守方完美配合），实际首攻是单方决策，
        所以 DD 期望墩数偏高估，但候选间的相对排序仍有参考价值。
        """
        from bridge.mcts.dd_search import ENDPLAY_AVAILABLE

        # Step 1: DD 蒙特卡洛首攻分析
        dd_result = None
        dd_candidates = []
        if ENDPLAY_AVAILABLE:
            try:
                dd_result = self._dd_play(state)
                dd_candidates = (dd_result.get("full_output", {})
                                 .get("mcts_stats", {}).get("candidates", []))
                print(f"[首攻] DD分析完成，候选数={len(dd_candidates)}")
            except Exception as e:
                print(f"[首攻] DD分析失败: {e}，回退纯LLM")
                dd_result = None

        # Step 2: LLM 战略性首攻 + DD 提示
        if dd_candidates:
            # 构建首攻专用 DD 提示
            cand_str = ", ".join(
                f"{c['card']}({c.get('avg_tricks', 0):.1f}墩"
                f"[{c.get('min_tricks', 0)}-{c.get('max_tricks', 0)}])"
                for c in dd_candidates[:5]
            )
            opening_hint = (
                f"\n\n## DD双明手首攻分析参考\n"
                f"DD蒙特卡洛分析了各候选首攻的期望墩数和min-max区间（双明手假设，"
                f"实际单方首攻期望会偏低，但相对排序有参考价值）：{cand_str}\n"
                f"请结合战略性首攻原则（如：长套首攻、连接张首攻、对抗无将首攻长套、"
                f"对抗有将避免帮庄家等），从DD候选中选择或说明为何选其他牌。"
            )
            llm_result = self._llm_play(state, use_reasoning=use_reasoning or True,
                                        extra_prompt=opening_hint)

            # Step 3: 否决检查（复用 _apply_dd_override）
            llm_result = self._apply_dd_override(llm_result, dd_candidates)

            # 保留 DD 统计数据供前端展示
            llm_result.setdefault("full_output", {})["mcts_stats"] = (
                dd_result.get("full_output", {}).get("mcts_stats", {})
            )
            llm_result["tiered_dd_fallback"] = dd_result
            return llm_result
        else:
            # DD 不可用或失败，纯 LLM 首攻
            return self._llm_play(state, force_reasoning=True)

    def _apply_dd_override(self, result: Dict[str, Any],
                           dd_candidates: list) -> Dict[str, Any]:
        """LLM 选择与 DD 最优差距过大时否决回退 DD。

        从 _llm_play_with_dd_hint 抽取的复用逻辑。
        """
        if not dd_candidates or not result.get("card"):
            return result

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
            # LLM选了DD候选范围外的牌，标记警告但不自动否决（首攻策略性强）
            result["reasoning"] = (
                f"[DD提示] LLM选择{llm_card_str}不在DD候选中，"
                f"DD最优{dd_best_str}({dd_best_avg:.1f}墩)\n"
                f"{result.get('reasoning', '')}"
            )
        elif llm_in_dd is not None:
            llm_avg = llm_in_dd.get("avg_tricks", 0)
            gap = dd_best_avg - llm_avg
            if gap > TIERED_OVERRIDE_THRESHOLD:
                # LLM选的牌与DD最优差距过大，否决LLM
                print(f"[首攻] 否决LLM选择{llm_card_str}({llm_avg:.1f}墩)，"
                      f"改用DD最优{dd_best_str}({dd_best_avg:.1f}墩)，差距{gap:.1f}墩")
                playable = self.engine.get_playable_cards()
                dd_card = None
                for c in playable:
                    if str(c) == dd_best_str:
                        dd_card = c
                        break
                if dd_card:
                    result["card"] = dd_card.to_dict()
                    result["reasoning"] = (
                        f"[DD否决LLM] LLM选{llm_card_str}({llm_avg:.1f}墩)与DD最优"
                        f"{dd_best_str}({dd_best_avg:.1f}墩)差距{gap:.1f}墩>"
                        f"{TIERED_OVERRIDE_THRESHOLD}，采用DD选择\n"
                        f"{result.get('reasoning', '')}"
                    )

        return result

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
                        result["card"] = dd_card.to_dict()
                        result["reasoning"] = (
                            f"[DD否决LLM] LLM选{llm_card_str}({llm_avg:.1f}墩)与DD最优"
                            f"{dd_best_str}({dd_best_avg:.1f}墩)差距{gap:.1f}墩>{TIERED_OVERRIDE_THRESHOLD}，"
                            f"采用DD选择\n{result.get('reasoning', '')}"
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

    def _get_bid_constraints(self) -> Dict[str, BidConstraint]:
        """从叫牌含义历史中提取约束（LLM调用，结果缓存）"""
        if self.bid_constraints is not None:
            return self.bid_constraints

        if not self.bid_history or not self.bid_history.strip():
            self.bid_constraints = {}
            return self.bid_constraints

        try:
            prompt = self.BID_CONSTRAINT_PROMPT.format(bid_history=self.bid_history)
            print(f"[DD] 调用LLM提取约束, bid_history长度={len(self.bid_history)}, 内容={self.bid_history[:200]}")
            result = self.llm_client.chat_json(system_prompt=prompt, temperature=0, max_tokens=1024)
            print(f"[DD] LLM约束结果: {result}")

            POS_NAME_MAP = {
                "南": "南", "西": "西", "北": "北", "东": "东",
                "south": "南", "west": "西", "north": "北", "east": "东",
                "s": "南", "w": "西", "n": "北", "e": "东",
            }
            constraints = {}
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
                constraints[pos_cn] = c

            print(f"[DD] 解析后约束: {constraints}")

            self.bid_constraints = constraints
            return constraints
        except Exception as e:
            import traceback
            print(f"[MCTS] 约束提取失败: {e}，回退到无约束采样")
            traceback.print_exc()
            self.bid_constraints = {}
            return {}

    def _alpha_mu_play(self, state: PlayState) -> Dict[str, Any]:
        """αμ 搜索打牌：残局多步前瞻，解决 strategy fusion。

        在每手 ≤ALPHA_MU_ENDGAME_CARDS 张时启用，用 belief tracker 的粒子
        作为 possible worlds，递归搜索 Pareto 前沿，选 min-max regret 最优。
        失败时回退到 DD。
        """
        if self.alpha_mu_search is None:
            return self._dd_play(state)

        constraints = self._get_bid_constraints()
        if constraints:
            self.dd_search.sampler.set_constraints(constraints)

        try:
            result = self.alpha_mu_search.search(state)
            card = result.get("card")
            if card is None:
                # αμ 失败，回退 DD
                return self._dd_play(state)
            return {
                "card": card.to_dict() if hasattr(card, "to_dict") else None,
                "reasoning": result.get("reasoning", ""),
                "full_output": result.get("full_output", {}),
                "prompt": "[αμ] no prompt",
            }
        except Exception as e:
            print(f"[αμ] 搜索异常: {e}，回退 DD")
            return self._dd_play(state)

    def _dd_play(self, state: PlayState, dd_samples: int = None) -> Dict[str, Any]:
        """DD搜索打牌（纯蒙特卡洛 + 双明手评估，由asyncio.to_thread调用）"""
        constraints = self._get_bid_constraints()
        if constraints:
            print(f"[DD] 约束已应用: {len(constraints)}家, { {p: f'HCP[{c.min_hcp}-{c.max_hcp}] suits={c.suit_min}' for p, c in constraints.items()} }")
            self.dd_search.sampler.set_constraints(constraints)
        else:
            print(f"[DD] 无约束 (bid_history={'空' if not self.bid_history else repr(self.bid_history[:80])})")

        # 允许请求级覆盖采样数
        if dd_samples is not None:
            self.dd_search.num_samples = dd_samples

        try:
            result = self.dd_search.search(state)
            card = result.get("card")
            if card is None:
                playable = self.engine.get_playable_cards()
                card = self._select_best_card(playable, state)
            return {
                "card": card.to_dict() if card else None,
                "reasoning": result.get("reasoning", ""),
                "full_output": result.get("full_output", {}),
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

    def _perfect_play(self, state: PlayState) -> Dict[str, Any]:
        """完美DD打牌（全知双明手，无采样，一次 solve_board 得所有候选精确分）"""
        try:
            result = self.dd_search.search_perfect(state)
            card = result.get("card")
            if card is None:
                playable = self.engine.get_playable_cards()
                card = self._select_best_card(playable, state)
            return {
                "card": card.to_dict() if card else None,
                "reasoning": result.get("reasoning", ""),
                "full_output": result.get("full_output", {}),
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
            self.mcts.sampler.set_constraints(constraints)

        try:
            result = self.mcts.search(state)
            card = result.get("card")
            if card is None:
                playable = self.engine.get_playable_cards()
                card = self._select_best_card(playable, state)
            return {
                "card": card.to_dict() if card else None,
                "reasoning": result.get("reasoning", ""),
                "full_output": result.get("full_output", {}),
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

        校验 LLM 推荐的牌是否合法且合理，违规时回退到 _select_best_card。

        Returns:
            (最终选定的牌, 校验警告消息)
            校验通过时警告消息为空字符串
        """
        try:
            from bridge.mcts.llm_validator import validate_llm_play
            validation = validate_llm_play(card, playable, state)

            if validation.valid:
                return card, ""

            # 校验失败，回退到规则化选牌
            fallback_card = self._select_best_card(playable, state)
            warning = (f"LLM推荐{card}校验失败({validation.severity}): "
                       f"{validation.violation}，回退到{fallback_card}")
            print(f"[校验] {warning}")
            return fallback_card, warning
        except Exception as e:
            # 校验器异常不阻塞主流程
            print(f"[校验] 校验器异常: {e}")
            return card, ""

    def _select_best_card(self, playable: List[Card], state: PlayState) -> Card:
        if len(playable) == 1:
            return playable[0]
        
        if state.current_trick.cards:
            lead_suit = state.current_trick.get_lead_suit()
            same_suit = [c for c in playable if c.suit == lead_suit]
            if same_suit:
                return min(same_suit, key=lambda c: c.rank_value)
        
        return min(playable, key=lambda c: (c.suit_order, c.rank_value))
