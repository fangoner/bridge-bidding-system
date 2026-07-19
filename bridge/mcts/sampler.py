import os
import random
import copy
from typing import Dict, List, Set, Optional, Tuple

from bridge.play_types import Card, PlayState, PlayPhase, POSITION_ORDER
from bridge.mcts.state_utils import SUIT_DISPLAY_ORDER, RANK_DESC
from bridge.mcts.constraints import (
    BidConstraint, validate_sample, compute_sample_violation_score,
    HCP_MAP, CONTROL_MAP,
    validate_level1, validate_level2, validate_voids_only,
    is_hard_source, filter_hard_constraints,
)
from bridge.mcts.belief import collect_voids


# 一副完整的52张牌
ALL_CARDS = [Card(suit=s, rank=r) for s in SUIT_DISPLAY_ORDER for r in RANK_DESC]


# 调试日志路径
_BASE_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
_DEBUG_LOG = os.path.join(_BASE_DIR, "dd_debug.log")

# ---- Phase 0a: 均匀采样 ----

def _extract_known_info(state: "PlayState", perspective: str) -> dict:
    """从 PlayState 提取生成均匀样本所需的所有已知信息。

    Returns dict with keys:
        known_cards: 已确定位置的牌张集合
        unknown_pool: 未知牌池（Card 列表）
        remaining_counts: {pos: count} 每家还需分配的张数
        known_voids: {pos: {suit, ...}} 已知缺门
        own_hand: 自己的手牌 {pos: [Card]}
        dummy_hand: 明手牌（若可见）{pos: [Card]}
        result: 预填充的已知手牌 {pos: [Card]}
    """
    declarer = state.contract.declarer
    dummy = state.dummy
    is_declarer_side = perspective in (declarer, dummy)

    # 1. 收集已知牌张
    known_cards: Set[Card] = set()
    own_hand = state.hands.get(perspective, [])
    known_cards.update(own_hand)

    if is_declarer_side and dummy:
        known_cards.update(state.hands.get(declarer, []))
        known_cards.update(state.hands.get(dummy, []))
    elif dummy and perspective != dummy:
        if state.phase != PlayPhase.LEAD:
            known_cards.update(state.hands.get(dummy, []))

    # 已出牌张
    for trick in state.tricks:
        for _, card in trick.cards:
            known_cards.add(card)
    for _, card in state.current_trick.cards:
        known_cards.add(card)

    # 1.5 检测并修复重复牌（与旧版一致）
    all_hand_cards = {}
    for pos in POSITION_ORDER:
        hand = state.hands.get(pos, [])
        seen_in_this_pos = set()
        cleaned = []
        for c in hand:
            key = (c.suit, c.rank)
            if key in all_hand_cards:
                other = all_hand_cards[key]
                with open(_DEBUG_LOG, "a", encoding="utf-8") as f:
                    f.write(f"\n[WARN] DUPLICATE in state.hands: {c} in both {other} and {pos}, removed from {pos}\n")
            elif key in seen_in_this_pos:
                with open(_DEBUG_LOG, "a", encoding="utf-8") as f:
                    f.write(f"\n[WARN] DUPLICATE in state.hands[{pos}]: {c} appears twice, removed\n")
            else:
                seen_in_this_pos.add(key)
                all_hand_cards[key] = pos
                cleaned.append(c)
        if len(cleaned) != len(hand):
            state.hands[pos] = cleaned

    # 2. 计算每家剩余张数
    total_completed = state.declarer_tricks + state.defender_tricks
    base_remaining = 13 - total_completed
    remaining_counts = {}
    for pos in POSITION_ORDER:
        in_trick = sum(1 for p, _ in state.current_trick.cards if p == pos)
        remaining_counts[pos] = base_remaining - in_trick

    # 3. 未知牌池
    unknown_pool = [c for c in ALL_CARDS if c not in known_cards]
    random.shuffle(unknown_pool)

    # 4. 预填充已知手牌
    result = {}
    if is_declarer_side and dummy:
        for pos in (declarer, dummy):
            hand = state.hands.get(pos, [])
            if hand:
                result[pos] = [Card(suit=c.suit, rank=c.rank) for c in hand]
    else:
        if own_hand:
            result[perspective] = [Card(suit=c.suit, rank=c.rank) for c in own_hand]
        if dummy and state.phase != PlayPhase.LEAD:
            hand = state.hands.get(dummy, [])
            if hand:
                result[dummy] = [Card(suit=c.suit, rank=c.rank) for c in hand]

    # 4.5 修正已知手牌张数
    for pos in list(result.keys()):
        expected = remaining_counts.get(pos, 0)
        actual = len(result[pos])
        if actual > expected:
            excess = actual - expected
            to_remove = random.sample(result[pos], excess)
            result[pos] = [c for c in result[pos] if c not in set(to_remove)]

    # 4.6 重建未知牌池（基于已分配牌）
    assigned = set()
    for pos, cards in result.items():
        for c in cards:
            assigned.add((c.suit, c.rank))
    played_set = set()
    for trick in state.tricks:
        for _, c in trick.cards:
            played_set.add((c.suit, c.rank))
    for _, c in state.current_trick.cards:
        played_set.add((c.suit, c.rank))
    unknown_pool = [c for c in ALL_CARDS
                    if (c.suit, c.rank) not in assigned
                    and (c.suit, c.rank) not in played_set]

    # 5. 收集已知缺门
    known_voids = collect_voids(state)

    return {
        "known_cards": known_cards,
        "unknown_pool": unknown_pool,
        "remaining_counts": remaining_counts,
        "known_voids": known_voids,
        "own_hand": own_hand,
        "dummy_hand": state.hands.get(dummy, []) if dummy else [],
        "result": result,
    }


def _sample_uniform(known_info: dict) -> Dict[str, List[Card]]:
    """均匀随机分配未知牌：打乱 pool → 按位置所需张数顺次分配，跳过 void 花色。

    这就是论文的 "random generation followed by verification of the constraints"。
    """
    result = {pos: list(cards) for pos, cards in known_info["result"].items()}
    pool = list(known_info["unknown_pool"])
    random.shuffle(pool)
    remaining_counts = dict(known_info["remaining_counts"])
    known_voids = known_info["known_voids"]

    idx = 0
    # 收集 void 跳过的牌，后面回填（避免丢牌）
    skipped: Dict[str, List[Card]] = {pos: [] for pos in POSITION_ORDER}
    for pos in POSITION_ORDER:
        if pos in result:
            continue
        count = remaining_counts[pos]
        void_suits = known_voids.get(pos, set())
        result[pos] = []
        for _ in range(count):
            while idx < len(pool) and pool[idx].suit in void_suits:
                skipped[pos].append(pool[idx])
                idx += 1
            if idx < len(pool):
                result[pos].append(pool[idx])
                idx += 1
    # 回填：void 跳过的牌分配给不 void 该花色的后续位置
    for pos in POSITION_ORDER:
        while len(result.get(pos, [])) < remaining_counts.get(pos, 0):
            for p2 in POSITION_ORDER:
                if skipped.get(p2) and pos != p2:
                    card = skipped[p2].pop()
                    if card.suit not in known_voids.get(pos, set()):
                        result.setdefault(pos, []).append(card)
                        break

    return result


def _warn_fallback(level: str, known_info: dict, constraints: dict) -> None:
    """记录约束降级日志。"""
    try:
        pos_list = [p for p in POSITION_ORDER if p not in known_info.get("result", {})]
        srcs = {}
        for p in pos_list:
            if p in constraints:
                srcs[p] = constraints[p].inference_source
        with open(_DEBUG_LOG, "a", encoding="utf-8") as _f:
            _f.write(f"[SAMPLER_FALLBACK] {level} sources={srcs}\n")
    except Exception:
        pass


class DealSampler:
    """从当前玩家视角采样未知手牌分布。

    Phase 0a: 使用均匀随机分配 + 分级硬约束验证回退链。
    不再使用 BeliefTracker 或加权粒子。
    """

    def __init__(self):
        self.constraints: Dict[str, BidConstraint] = {}
        self.belief_tracker = None  # 已废弃，保留属性避免 AttributeError

    def set_constraints(self, constraints: Dict[str, BidConstraint]) -> None:
        """设置叫牌约束，后续 sample() 会验证采样结果。

        Args:
            constraints: {position: BidConstraint} 映射
        """
        self.constraints = constraints or {}

    # ---- 向后兼容接口（Phase 0a 移除 BeliefTracker） ----
    def set_belief_tracker(self, tracker=None) -> None:
        """[已废弃] BeliefTracker 已移除。保留接口避免 import 错误。"""
        pass

    def sample(self, state: PlayState, perspective: str) -> Dict[str, List[Card]]:
        """均匀采样一套与当前信息一致的手牌，等级约束验证。

        Phase 0a: 替换旧的三步有偏生成 + 信念跟踪器路径。
        使用均匀随机分配 + 分级硬约束验证回退。

        Args:
            state: 当前PlayState
            perspective: 当前出牌者位置

        Returns:
            完整4家手牌 Dict[str, List[Card]]
        """
        known_info = _extract_known_info(state, perspective)
        hard_constraints = filter_hard_constraints(self.constraints)

        # ==== Level 1: 硬约束验证 ====
        for _attempt in range(50):
            world = _sample_uniform(known_info)
            if not hard_constraints:
                return world  # 无约束，一次均匀采样就是无偏样本
            if validate_level1(world, hard_constraints):
                return world

        # ==== Level 2: 放宽约束 ====
        _warn_fallback("Level 1→2", known_info, self.constraints)
        for _attempt in range(50):
            world = _sample_uniform(known_info)
            if validate_level2(world, hard_constraints):
                return world

        # ==== Level 0: 仅 void 保护 ====
        _warn_fallback("Level 2→0", known_info, self.constraints)
        for _attempt in range(20):
            world = _sample_uniform(known_info)
            if validate_voids_only(world, known_info["known_voids"]):
                return world

        # 极端兜底
        _warn_fallback("FINAL_FALLBACK", known_info, self.constraints)
        return _sample_uniform(known_info)

    def sample_n(self, n: int, state: PlayState, perspective: str) -> List[Dict[str, List[Card]]]:
        """生成 n 个独立均匀样本（用于 DD/αμ 引擎）。"""
        return [self.sample(state, perspective) for _ in range(n)]

    def _sample_once(self, state: PlayState, perspective: str) -> Dict[str, List[Card]]:
        """采样一套与当前信息一致的完整手牌（均匀分配 + void 保护）。

        Phase 0a: 不再使用三步有偏生成，改为 _sample_uniform。
        约束验证由 sample() 调用方在外部完成。

        Args:
            state: 当前PlayState
            perspective: 当前出牌者位置

        Returns:
            完整4家手牌 Dict[str, List[Card]]
        """
        known_info = _extract_known_info(state, perspective)
        return _sample_uniform(known_info)

    def _constrained_select(
        cls,
        pool: List[Card],
        count: int,
        constraint: "BidConstraint",
    ) -> List[Card]:
        """从 pool 中选 count 张牌，保证满足所有约束，且HCP分布符合自然概率。
        采用多次重试机制提高满足率。
        """
        if count >= len(pool):
            return list(pool)

        # 计算目标HCP中心值
        target_hcp = None
        if constraint.min_hcp_target is not None:
            target_hcp = constraint.min_hcp_target
        elif constraint.min_hcp is not None and constraint.max_hcp is not None:
            target_hcp = (constraint.min_hcp + constraint.max_hcp) / 2.0
        elif constraint.min_hcp is not None:
            target_hcp = constraint.min_hcp + 2
        elif constraint.max_hcp is not None:
            target_hcp = constraint.max_hcp - 2

        # 多次尝试找满足硬约束的手牌
        max_attempts = 20
        for attempt in range(max_attempts):
            # 每次尝试打乱pool顺序，增加随机性
            attempt_pool = list(pool)
            random.shuffle(attempt_pool)
            selected, remaining = cls._constrained_select_once(attempt_pool, count, constraint, target_hcp)

            # 微调：局部交换修正约束违反
            # 受保护的牌（specific_cards）不能被换出去
            protected = set((c.suit, c.rank) for c in selected if (c.suit, c.rank) in constraint.specific_cards)

            for _ in range(200):
                if cls._check_all_constraints(selected, constraint, count):
                    return selected

                current_hcp = sum(HCP_MAP.get(c.rank, 0) for c in selected)
                current_dist: Dict[str, int] = {"♠": 0, "♥": 0, "♦": 0, "♣": 0}
                for c in selected:
                    current_dist[c.suit] = current_dist.get(c.suit, 0) + 1

                swapped = False

                # 1. 修正HCP不足：换大牌进来（不换出受保护的牌）
                if constraint.min_hcp is not None and current_hcp < constraint.min_hcp:
                    low_cards = sorted(
                        [c for c in selected if (c.suit, c.rank) not in protected],
                        key=lambda c: HCP_MAP.get(c.rank, 0)
                    )
                    for low in low_cards:
                        low_hcp = HCP_MAP.get(low.rank, 0)
                        candidates = [c for c in remaining if HCP_MAP.get(c.rank, 0) > low_hcp]
                        random.shuffle(candidates)
                        for high in candidates:
                            trial = selected.copy()
                            trial.remove(low)
                            trial.append(high)
                            if cls._check_all_constraints(trial, constraint, count):
                                selected = trial
                                remaining.remove(high)
                                remaining.append(low)
                                swapped = True
                                break
                        if swapped:
                            break
                    if swapped:
                        continue

                # 2. 修正HCP过高：换小牌进来（不换出受保护的牌）
                if constraint.max_hcp is not None and current_hcp > constraint.max_hcp:
                    high_cards = sorted(
                        [c for c in selected if (c.suit, c.rank) not in protected],
                        key=lambda c: -HCP_MAP.get(c.rank, 0)
                    )
                    for high in high_cards:
                        high_hcp = HCP_MAP.get(high.rank, 0)
                        candidates = [c for c in remaining if HCP_MAP.get(c.rank, 0) < high_hcp]
                        random.shuffle(candidates)
                        for low in candidates:
                            trial = selected.copy()
                            trial.remove(high)
                            trial.append(low)
                            if cls._check_all_constraints(trial, constraint, count):
                                selected = trial
                                remaining.remove(low)
                                remaining.append(high)
                                swapped = True
                                break
                        if swapped:
                            break
                    if swapped:
                        continue

                # 3. 修正花色长度不满足（短套补牌/长套减牌）
                # 3a. suit_min不满足：某套不够张数，需要换该套牌进来
                for suit, min_len in constraint.suit_min.items():
                    if current_dist.get(suit, 0) < min_len:
                        out_candidates = [c for c in selected if c.suit != suit and (c.suit, c.rank) not in protected]
                        in_candidates = [c for c in remaining if c.suit == suit]
                        random.shuffle(out_candidates)
                        random.shuffle(in_candidates)
                        for out_c in out_candidates:
                            for in_c in in_candidates:
                                trial = selected.copy()
                                trial.remove(out_c)
                                trial.append(in_c)
                                if cls._check_all_constraints(trial, constraint, count):
                                    selected = trial
                                    remaining.remove(in_c)
                                    remaining.append(out_c)
                                    swapped = True
                                    break
                            if swapped:
                                break
                        if swapped:
                            break
                if swapped:
                    continue

                # 3b. suit_max不满足：某套太长，需要换其他套牌
                effective_max = dict(constraint.suit_max)
                if constraint.balanced:
                    for s in ("♠", "♥", "♦", "♣"):
                        effective_max[s] = min(effective_max.get(s, 13), 5)
                for suit, max_len in effective_max.items():
                    if current_dist.get(suit, 0) > max_len:
                        out_candidates = [c for c in selected if c.suit == suit and (c.suit, c.rank) not in protected]
                        in_candidates = [c for c in remaining if c.suit != suit]
                        random.shuffle(out_candidates)
                        random.shuffle(in_candidates)
                        for out_c in out_candidates:
                            for in_c in in_candidates:
                                trial = selected.copy()
                                trial.remove(out_c)
                                trial.append(in_c)
                                if cls._check_all_constraints(trial, constraint, count):
                                    selected = trial
                                    remaining.remove(in_c)
                                    remaining.append(out_c)
                                    swapped = True
                                    break
                            if swapped:
                                break
                        if swapped:
                            break
                if swapped:
                    continue

                # 3c. exact_suit不满足
                for suit, exact_len in constraint.exact_suit.items():
                    if current_dist.get(suit, 0) < exact_len:
                        out_candidates = [c for c in selected if c.suit != suit and (c.suit, c.rank) not in protected]
                        in_candidates = [c for c in remaining if c.suit == suit]
                        random.shuffle(out_candidates)
                        random.shuffle(in_candidates)
                        for out_c in out_candidates:
                            for in_c in in_candidates:
                                trial = selected.copy()
                                trial.remove(out_c)
                                trial.append(in_c)
                                if cls._check_all_constraints(trial, constraint, count):
                                    selected = trial
                                    remaining.remove(in_c)
                                    remaining.append(out_c)
                                    swapped = True
                                    break
                            if swapped:
                                break
                        if swapped:
                            break
                    elif current_dist.get(suit, 0) > exact_len:
                        out_candidates = [c for c in selected if c.suit == suit and (c.suit, c.rank) not in protected]
                        in_candidates = [c for c in remaining if c.suit != suit]
                        random.shuffle(out_candidates)
                        random.shuffle(in_candidates)
                        for out_c in out_candidates:
                            for in_c in in_candidates:
                                trial = selected.copy()
                                trial.remove(out_c)
                                trial.append(in_c)
                                if cls._check_all_constraints(trial, constraint, count):
                                    selected = trial
                                    remaining.remove(in_c)
                                    remaining.append(out_c)
                                    swapped = True
                                    break
                            if swapped:
                                break
                        if swapped:
                            break
                if swapped:
                    continue

                # 4. 修正均型牌约束：没有单张/缺门/6张套
                if constraint.balanced:
                    # 有缺门/单张：需要换牌
                    bad_suits = [s for s, d in current_dist.items() if d <= 1]
                    long_suits = [s for s, d in current_dist.items() if d >= 6]
                    if bad_suits or long_suits:
                        fix_suit = bad_suits[0] if bad_suits else long_suits[0]
                        need_longer = bool(bad_suits)
                        if need_longer:
                            out_candidates = [c for c in selected if c.suit != fix_suit
                                              and current_dist[c.suit] >= 3
                                              and (c.suit, c.rank) not in protected]
                            in_candidates = [c for c in remaining if c.suit == fix_suit]
                        else:
                            out_candidates = [c for c in selected if c.suit == fix_suit and (c.suit, c.rank) not in protected]
                            short_suits = [s for s, d in current_dist.items() if d <= 4 and s != fix_suit]
                            in_candidates = [c for c in remaining if c.suit in short_suits] if short_suits else [c for c in remaining if c.suit != fix_suit]
                        random.shuffle(out_candidates)
                        random.shuffle(in_candidates)
                        for out_c in out_candidates:
                            for in_c in in_candidates:
                                trial = selected.copy()
                                trial.remove(out_c)
                                trial.append(in_c)
                                if cls._check_all_constraints(trial, constraint, count):
                                    selected = trial
                                    remaining.remove(in_c)
                                    remaining.append(out_c)
                                    swapped = True
                                    break
                            if swapped:
                                break
                        if swapped:
                            continue

                # 5. 修正控制数不足（不换出受保护的牌）
                if constraint.min_controls is not None:
                    current_controls = sum(CONTROL_MAP.get(c.rank, 0) for c in selected)
                    if current_controls < constraint.min_controls:
                        low_control = [c for c in selected if CONTROL_MAP.get(c.rank, 0) == 0 and (c.suit, c.rank) not in protected]
                        high_control = [c for c in remaining if CONTROL_MAP.get(c.rank, 0) > 0]
                        random.shuffle(low_control)
                        random.shuffle(high_control)
                        for out_c in low_control:
                            for in_c in high_control:
                                trial = selected.copy()
                                trial.remove(out_c)
                                trial.append(in_c)
                                if cls._check_all_constraints(trial, constraint, count):
                                    selected = trial
                                    remaining.remove(in_c)
                                    remaining.append(out_c)
                                    swapped = True
                                    break
                            if swapped:
                                break
                        if swapped:
                            continue

                if not swapped:
                    break

            if cls._check_all_constraints(selected, constraint, count):
                return selected

        # 所有尝试都失败，返回最后一次结果（软约束会在信念权重中惩罚）
        return selected


# ============================================================
# 新的全局约束采样算法 v2
# 核心思想：先全局分配牌型+HCP，再按骨架填充牌张
# ============================================================

