import os
import random
import copy
from typing import Dict, List, Set, Optional, Tuple

from bridge.play_types import Card, PlayState, PlayPhase, POSITION_ORDER
from bridge.mcts.state_utils import SUIT_DISPLAY_ORDER, RANK_DESC
from bridge.mcts.constraints import (
    BidConstraint, validate_sample,
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

    # 4.7 统计每家已出牌（中局约束扣减用：初始约束 = 已出部分 + 剩余部分）
    played_stats = {
        p: {"hcp": 0, "controls": 0, "suit": {"♠": 0, "♥": 0, "♦": 0, "♣": 0}}
        for p in POSITION_ORDER
    }
    for _trick in state.tricks:
        for p, c in _trick.cards:
            _st = played_stats.get(p)
            if _st is None:
                continue
            _st["hcp"] += HCP_MAP.get(c.rank, 0)
            _st["controls"] += CONTROL_MAP.get(c.rank, 0)
            _st["suit"][c.suit] = _st["suit"].get(c.suit, 0) + 1
    for p, c in state.current_trick.cards:
        _st = played_stats.get(p)
        if _st is None:
            continue
        _st["hcp"] += HCP_MAP.get(c.rank, 0)
        _st["controls"] += CONTROL_MAP.get(c.rank, 0)
        _st["suit"][c.suit] = _st["suit"].get(c.suit, 0) + 1

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
        "played": played_stats,
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
    # 初始化空位置
    for pos in POSITION_ORDER:
        if pos not in result:
            result[pos] = []
    # 收集 void 跳过的牌，后面回填（避免丢牌）
    skipped: Dict[str, List[Card]] = {pos: [] for pos in POSITION_ORDER}
    for pos in POSITION_ORDER:
        have = len(result.get(pos, []))
        need = remaining_counts.get(pos, 0) - have
        void_suits = known_voids.get(pos, set())
        for _ in range(need):
            while idx < len(pool) and pool[idx].suit in void_suits:
                skipped[pos].append(pool[idx])
                idx += 1
            if idx < len(pool):
                result[pos].append(pool[idx])
                idx += 1
    # 回填：void 跳过的牌分配给不 void 该花色的后续位置
    for pos in POSITION_ORDER:
        _retries = 0
        while len(result.get(pos, [])) < remaining_counts.get(pos, 0) and _retries < 100:
            _retries += 1
            filled = False
            for p2 in POSITION_ORDER:
                if pos == p2 or not skipped.get(p2):
                    continue
                for i, card in enumerate(skipped[p2]):
                    if card.suit not in known_voids.get(pos, set()):
                        result.setdefault(pos, []).append(skipped[p2].pop(i))
                        filled = True
                        break
                if filled:
                    break
            if not filled:
                break  # 无可用牌，放弃回填

    return result


def _constraint_trivially_satisfied(c: "BidConstraint", remaining_count: int) -> bool:
    """剩余约束是否无条件满足（采样无需再验证该位置）。"""
    if c.min_hcp not in (None, 0):
        return False
    if c.max_hcp is not None and c.max_hcp < remaining_count * 4:
        return False
    if c.min_controls not in (None, 0):
        return False
    if any(c.suit_min.values()):
        return False
    if any(c.suit_max.values()):
        return False
    if c.exact_suit:
        return False
    if c.specific_cards:
        return False
    if c.balanced is not None:
        return False
    return True


def _reduce_constraint_for_played(
    c: "BidConstraint",
    played: dict,
    remaining_count: int,
) -> Optional["BidConstraint"]:
    """中局扣减：把整手约束按已出牌折算为剩余部分约束。

    物理意义：初始约束 = 已出部分 + 剩余部分。返回副本，不修改原约束。
    折算后若无条件满足则返回 None（采样跳过该位置验证）。
    """
    if not played:
        return c
    reduced = copy.deepcopy(c)
    played_hcp = played.get("hcp", 0)
    played_controls = played.get("controls", 0)
    played_suit = played.get("suit", {})
    # HCP：剩余范围 = [初始min - 已出HCP, 初始max - 已出HCP]
    if reduced.min_hcp is not None:
        reduced.min_hcp = max(0, reduced.min_hcp - played_hcp)
    if reduced.max_hcp is not None:
        reduced.max_hcp = max(reduced.max_hcp - played_hcp, reduced.min_hcp or 0)
    # 控制数同样按已出牌扣减
    if reduced.min_controls is not None:
        reduced.min_controls = max(0, reduced.min_controls - played_controls)
    # 花色张数：suit_min/exact_suit 扣减后不超剩余张数；suit_max 扣减已出张数
    for s in list(reduced.suit_min.keys()):
        reduced.suit_min[s] = max(0, min(reduced.suit_min[s] - played_suit.get(s, 0), remaining_count))
    for s in list(reduced.exact_suit.keys()):
        reduced.exact_suit[s] = max(0, min(reduced.exact_suit[s] - played_suit.get(s, 0), remaining_count))
    for s in list(reduced.suit_max.keys()):
        reduced.suit_max[s] = max(0, reduced.suit_max[s] - played_suit.get(s, 0))
    # 均型是整手 13 张属性，剩余碎片无法判断 → 转为不约束
    reduced.balanced = None
    if _constraint_trivially_satisfied(reduced, remaining_count):
        return None
    return reduced


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
        self.belief_tracker = None  # 已废弃，保留属性向后兼容

    def set_constraints(self, constraints: Dict[str, BidConstraint]) -> None:
        self.constraints = constraints or {}

    def sample(self, state: PlayState, perspective: str) -> Dict[str, List[Card]]:
        """均匀采样一套与当前信息一致的手牌，等级约束验证。

        Phase 0a: 使用均匀随机分配 + 分级硬约束验证回退。
        """
        known_info = _extract_known_info(state, perspective)
        hard_constraints = filter_hard_constraints(self.constraints)
        return self._sample_one(known_info, hard_constraints)

    def sample_n(self, n: int, state: PlayState, perspective: str) -> List[Dict[str, List[Card]]]:
        """生成 n 个独立均匀样本（用于 DD/αμ 引擎）。

        提取一次 known_info，复用 n 次，避免每个样本重复扫描 state。
        """
        known_info = _extract_known_info(state, perspective)
        hard_constraints = filter_hard_constraints(self.constraints)
        results = []
        for _ in range(n):
            results.append(self._sample_one(known_info, hard_constraints))
        return results

    def _sample_one(
        self,
        known_info: dict,
        hard_constraints: Dict[str, "BidConstraint"],
    ) -> Dict[str, List[Card]]:
        """单次采样（复用 known_info，不重复提取）。"""
        # 过滤：已知手牌的位置不验证（手牌由发牌固定，无法通过采样改变）
        known_positions = set(known_info.get("result", {}).keys())
        played_stats = known_info.get("played", {})
        remaining_counts = known_info.get("remaining_counts", {})
        # 中局扣减：把整手约束按已出牌折算为剩余部分约束，再用于验证
        active_constraints = {}
        for pos, c in hard_constraints.items():
            if pos in known_positions:
                continue
            reduced = _reduce_constraint_for_played(
                c, played_stats.get(pos), remaining_counts.get(pos, 0)
            )
            if reduced is None:
                continue
            active_constraints[pos] = reduced
        # Level 1: 硬约束
        for _attempt in range(50):
            world = _sample_uniform(known_info)
            if not active_constraints:
                return world
            if validate_level1(world, active_constraints):
                return world
        # Level 2: 放宽约束
        _warn_fallback("Level 1→2", known_info, self.constraints)
        for _attempt in range(50):
            world = _sample_uniform(known_info)
            if validate_level2(world, active_constraints):
                return world
        # Level 0: 仅 void
        _warn_fallback("Level 2→0", known_info, self.constraints)
        for _attempt in range(20):
            world = _sample_uniform(known_info)
            if validate_voids_only(world, known_info["known_voids"]):
                return world
        # 兜底
        _warn_fallback("FINAL_FALLBACK", known_info, self.constraints)
        return _sample_uniform(known_info)

