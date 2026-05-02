"""叫牌约束：从叫牌含义中提取的点力/牌型限制，用于MCTS采样过滤。"""
from dataclasses import dataclass, field
from typing import Dict, List, Optional

from bridge.play_types import Card, POSITION_ORDER


@dataclass
class BidConstraint:
    """一个牌手在叫牌中暴露的约束"""
    position: str
    min_hcp: Optional[int] = None
    max_hcp: Optional[int] = None
    balanced: Optional[bool] = None  # True=均型, False=非均型, None=未知
    suit_min: Dict[str, int] = field(default_factory=dict)  # 花色→最少张数


def validate_sample(
    hands: Dict[str, List[Card]],
    constraints: Dict[str, BidConstraint],
) -> bool:
    """检查采样出的手牌是否满足所有叫牌约束。

    Args:
        hands: 完整4家手牌 {position: [Card, ...]}
        constraints: 需要检查的约束 {position: BidConstraint}

    Returns:
        True 如果满足所有约束
    """
    for pos, constraint in constraints.items():
        cards = hands.get(pos, [])
        if not cards:
            continue

        hcp = _compute_hcp(cards)
        if constraint.min_hcp is not None and hcp < constraint.min_hcp:
            return False
        if constraint.max_hcp is not None and hcp > constraint.max_hcp:
            return False

        for suit, min_len in constraint.suit_min.items():
            count = sum(1 for c in cards if c.suit == suit)
            if count < min_len:
                return False

        if constraint.balanced is not None:
            # 均型: 没有单缺，没有6张+套，没有55双套
            dist = _count_distribution(cards)
            is_balanced = _is_balanced(dist)
            if constraint.balanced and not is_balanced:
                return False
            if not constraint.balanced and is_balanced:
                return False

    return True


HCP_MAP = {"A": 4, "K": 3, "Q": 2, "J": 1}


def _compute_hcp(cards: List[Card]) -> int:
    return sum(HCP_MAP.get(c.rank, 0) for c in cards)


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
    return True
