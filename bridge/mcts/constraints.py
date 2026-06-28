"""叫牌约束：从叫牌含义中提取的点力/牌型限制，用于MCTS采样过滤。"""
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Set, Tuple

from bridge.play_types import Card, POSITION_ORDER

CONTROL_MAP = {"A": 2, "K": 1}  # A=2控制，K=1控制


@dataclass
class BidConstraint:
    """一个牌手在叫牌中暴露的约束

    扩展字段说明：
    - suit_max: 花色→最多张数（如1NT开叫高花≤4张）
    - exact_suit: 花色→精确张数（如弱二开叫=6张）
    - min_controls: 最少控制数（A=2, K=1）
    - specific_cards: 必须持有的特定牌张集合，格式 {(suit, rank), ...}
                      例如{("♠", "A")}表示必须持有♠A（如2♣强开叫通常有控制）
    - forbidden_hcp: 禁止的点力范围（如逆叫后点力不能低于16）
    - suit_quality: 花色→最低顶张要求（如弱二需要该套≥2个顶张大牌）
                       格式: {suit: min_holding}，min_holding为顶张大牌的组合
    """
    position: str
    min_hcp: Optional[int] = None
    max_hcp: Optional[int] = None
    balanced: Optional[bool] = None  # True=均型, False=非均型, None=未知
    suit_min: Dict[str, int] = field(default_factory=dict)  # 花色→最少张数
    suit_max: Dict[str, int] = field(default_factory=dict)  # 花色→最多张数
    exact_suit: Dict[str, int] = field(default_factory=dict)  # 花色→精确张数
    min_controls: Optional[int] = None  # 最少控制数（A=2, K=1）
    min_hcp_target: Optional[int] = None  # HCP期望中心值（用于采样分布引导，非硬约束）
    specific_cards: Set[Tuple[str, str]] = field(default_factory=set)  # 必须持有的特定牌张
    inference_source: str = "hard_coded"  # 约束来源：hard_coded/negative_inference/hcp_conservation/convention


def validate_sample(
    hands: Dict[str, List[Card]],
    constraints: Dict[str, BidConstraint],
) -> bool:
    """检查采样出的手牌是否满足所有叫牌约束（硬约束验证）。

    Args:
        hands: 完整4家手牌 {position: [Card, ...]}
        constraints: 需要检查的约束 {position: BidConstraint}

    Returns:
        True 如果满足所有硬约束
    """
    for pos, constraint in constraints.items():
        cards = hands.get(pos, [])
        if not cards:
            continue

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
