"""叫牌约束：从叫牌含义中提取的点力/牌型限制，用于采样过滤。

约束分级体系（Phase 0a）：
  Level 1 (硬约束) — 叫牌明确承诺，采样时必须满足：
    hard_coded* / meaning_parsed / convention_* / cue_bid / overcall_* / unusual_nt
  Level 3 (忽略) — 推理猜测，不参与采样：
    negative_inference / hcp_conservation
"""
from dataclasses import dataclass, field, copy as dc_copy
from typing import Dict, List, Optional, Set, Tuple

from bridge.play_types import Card, POSITION_ORDER

CONTROL_MAP = {"A": 2, "K": 1}  # A=2控制，K=1控制


# ---- 约束来源分类 ----
_HARD_SOURCE_PREFIXES = (
    "hard_coded",      # 叫牌阶段硬编码（含体系后缀 hard_coded_jf / hard_coded_natural）
    "meaning_parsed",   # LLM 叫品含义解析
    "convention_",      # 约定叫识别（convention_takeout_double / convention_stayman 等）
    "cue_bid",          # 扣叫
    "overcall_",        # 争叫（overcall_2level 等）
    "unusual_nt",       # 非寻常无将
)

_IGNORED_SOURCES = {
    "negative_inference",   # 否定推断："他 pass 了大概 ≤7 HCP"——不是事实
    "hcp_conservation",     # 点力守恒链式推理——一步错全盘错
}


def is_hard_source(src: str) -> bool:
    """约束来源是否是 Level 1（硬约束/叫牌明确承诺）。"""
    if not src:
        return False
    if src in _IGNORED_SOURCES:
        return False
    return src.startswith(_HARD_SOURCE_PREFIXES)


def is_ignored_source(src: str) -> bool:
    """约束来源是否应在采样中忽略（Level 3）。"""
    return src in _IGNORED_SOURCES


def filter_hard_constraints(
    constraints: Dict[str, "BidConstraint"],
) -> Dict[str, "BidConstraint"]:
    """从约束字典中筛选仅 Level 1 硬约束（用于均匀采样验证）。"""
    return {
        pos: c for pos, c in constraints.items()
        if is_hard_source(c.inference_source)
    }


def relax_constraint(c: "BidConstraint") -> "BidConstraint":
    """生成 Level 2 放宽版约束：HCP ±2，suit_min 减半。"""
    relaxed = BidConstraint(position=c.position, inference_source="relaxed")
    if c.min_hcp is not None:
        relaxed.min_hcp = max(0, c.min_hcp - 2)
    if c.max_hcp is not None:
        relaxed.max_hcp = min(37, c.max_hcp + 2)
    if c.min_controls is not None:
        relaxed.min_controls = max(0, c.min_controls - 1)
    relaxed.suit_min = {s: max(1, n // 2) for s, n in c.suit_min.items()}
    # suit_max / exact_suit / specific_cards / balanced 放宽时不保留
    return relaxed


@dataclass
class BidConstraint:
    """一个牌手在叫牌中暴露的约束。

    inference_source 标记约束来源，由约束分级体系使用：
    - Level 1 硬约束（采样验证）：hard_coded*, meaning_parsed, convention_*, cue_bid, overcall_*, unusual_nt
    - Level 3 忽略（不参与采样）：negative_inference, hcp_conservation
    """
    position: str
    min_hcp: Optional[int] = None
    max_hcp: Optional[int] = None
    balanced: Optional[bool] = None
    suit_min: Dict[str, int] = field(default_factory=dict)
    suit_max: Dict[str, int] = field(default_factory=dict)
    exact_suit: Dict[str, int] = field(default_factory=dict)
    min_controls: Optional[int] = None
    min_hcp_target: Optional[int] = None  # 已废弃：Phase 0a 后不再用于分布引导
    specific_cards: Set[Tuple[str, str]] = field(default_factory=set)
    inference_source: str = "hard_coded"


def validate_level1(
    hands: Dict[str, List[Card]],
    constraints: Dict[str, "BidConstraint"],
) -> bool:
    """Level 1 硬约束验证：仅检查叫牌明确承诺（hard_coded / convention / meaning_parsed）。

    忽略 negative_inference 和 hcp_conservation 来源的约束。
    """
    for pos, constraint in constraints.items():
        if not is_hard_source(constraint.inference_source):
            continue
        cards = hands.get(pos, [])
        if not cards:
            continue
        if not _check_constraint(cards, constraint):
            return False
    return True


def validate_level2(
    hands: Dict[str, List[Card]],
    constraints: Dict[str, "BidConstraint"],
) -> bool:
    """Level 2 放宽约束验证：HCP ±2, suit_min 减半。"""
    for pos, constraint in constraints.items():
        if not is_hard_source(constraint.inference_source):
            continue
        cards = hands.get(pos, [])
        if not cards:
            continue
        relaxed = relax_constraint(constraint)
        if not _check_constraint(cards, relaxed):
            return False
    return True


def validate_voids_only(
    hands: Dict[str, List[Card]],
    known_voids: Dict[str, Set[str]],
) -> bool:
    """Level 0 验证：仅检查已知缺门（看到垫牌推得的花色张数 = 0）。"""
    for pos, void_suits in known_voids.items():
        cards = hands.get(pos, [])
        for c in cards:
            if c.suit in void_suits:
                return False
    return True


def _check_constraint(cards: List[Card], constraint: "BidConstraint") -> bool:
    """检查一手牌是否满足单个约束的所有条件。"""
    dist = _count_distribution(cards)
    hcp = _compute_hcp(cards)
    controls = _compute_controls(cards)

    if constraint.min_hcp is not None and hcp < constraint.min_hcp:
        return False
    if constraint.max_hcp is not None and hcp > constraint.max_hcp:
        return False
    if constraint.min_controls is not None and controls < constraint.min_controls:
        return False
    for suit, min_len in constraint.suit_min.items():
        if dist.get(suit, 0) < min_len:
            return False
    for suit, max_len in constraint.suit_max.items():
        if dist.get(suit, 0) > max_len:
            return False
    for suit, exact_len in constraint.exact_suit.items():
        if dist.get(suit, 0) != exact_len:
            return False
    if constraint.balanced is not None:
        is_balanced = _is_balanced(dist)
        if constraint.balanced and not is_balanced:
            return False
        if not constraint.balanced and is_balanced:
            return False
    for (suit, rank) in constraint.specific_cards:
        if not any(c.suit == suit and c.rank == rank for c in cards):
            return False
    return True


def validate_sample(
    hands: Dict[str, List[Card]],
    constraints: Dict[str, "BidConstraint"],
) -> bool:
    """检查采样出的手牌是否满足所有 Level 1 硬约束。

    自动忽略 negative_inference / hcp_conservation 来源的约束。
    等同于 validate_level1()，保留用于向后兼容。
    """
    return validate_level1(hands, constraints)


def compute_sample_violation_score(
    hands: Dict[str, List[Card]],
    constraints: Dict[str, BidConstraint],
) -> float:
    """计算采样违反约束的程度分数（用于粒子软加权）。

    分数越高表示违反越严重，0表示完全满足。
    """
    score = 0.0
    for pos, constraint in constraints.items():
        cards = hands.get(pos, [])
        if not cards:
            continue

        dist = _count_distribution(cards)
        hcp = _compute_hcp(cards)
        controls = _compute_controls(cards)

        if constraint.min_hcp is not None and hcp < constraint.min_hcp:
            score += (constraint.min_hcp - hcp) * 2.0
        if constraint.max_hcp is not None and hcp > constraint.max_hcp:
            score += (hcp - constraint.max_hcp) * 2.0

        if constraint.min_controls is not None and controls < constraint.min_controls:
            score += (constraint.min_controls - controls) * 1.5

        for suit, min_len in constraint.suit_min.items():
            deficit = min_len - dist.get(suit, 0)
            if deficit > 0:
                score += deficit * 3.0

        for suit, max_len in constraint.suit_max.items():
            excess = dist.get(suit, 0) - max_len
            if excess > 0:
                score += excess * 3.0

        for suit, exact_len in constraint.exact_suit.items():
            diff = abs(dist.get(suit, 0) - exact_len)
            if diff > 0:
                score += diff * 4.0

        if constraint.balanced is not None:
            is_balanced = _is_balanced(dist)
            if constraint.balanced and not is_balanced:
                score += 5.0
            if not constraint.balanced and is_balanced:
                score += 2.0

        for (suit, rank) in constraint.specific_cards:
            if not any(c.suit == suit and c.rank == rank for c in cards):
                score += 8.0  # 缺失特定大牌重罚

    return score


HCP_MAP = {"A": 4, "K": 3, "Q": 2, "J": 1}


def _compute_hcp(cards: List[Card]) -> int:
    return sum(HCP_MAP.get(c.rank, 0) for c in cards)


def _compute_controls(cards: List[Card]) -> int:
    return sum(CONTROL_MAP.get(c.rank, 0) for c in cards)


def _count_distribution(cards: List[Card]) -> Dict[str, int]:
    dist = {"♠": 0, "♥": 0, "♦": 0, "♣": 0}
    for c in cards:
        dist[c.suit] = dist.get(c.suit, 0) + 1
    return dist


def _is_balanced(dist: Dict[str, int]) -> bool:
    counts = list(dist.values())
    if any(c >= 6 for c in counts):
        return False
    if any(c <= 1 for c in counts):
        return False
    # 55双套也不是均型
    if sorted(counts, reverse=True)[:2] == [5, 5]:
        return False
    # 允许5332（5张低花）的半均型
    sorted_counts = sorted(counts, reverse=True)
    if sorted_counts[0] == 5 and sorted_counts[1] == 3 and sorted_counts[2] == 3 and sorted_counts[3] == 2:
        return True
    return True
