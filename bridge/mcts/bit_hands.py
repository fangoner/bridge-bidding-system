"""Bitmap 手牌表示——用 64-bit 整数替代 List[Card]。

编码：4 花色 × 16 位 = 64 位
  bits 0-15:  ♠ (bit 2=2, bit 3=3, ..., bit 14=A)
  bits 16-31: ♥
  bits 32-47: ♦
  bits 48-63: ♣

与 DDS remainCards 格式完全一致，DirectDDS 可零转换接收。

操作：
  clone:     {pos: bits for pos, bits in world.items()}  — 4 个 int 复制
  remove:    hand &= ~card_bit                             — 1 条位指令
  has_suit:  hand & suit_mask != 0                         — 1 条位指令
  count:     (hand >> suit_offset).bit_count()             — Python 3.8+

vs 旧的 List[Card]: clone 需 list() × 4, remove 需 list.remove() O(n),
  has_suit 需遍历列表比较 suit 字段。
"""

from typing import Dict, List, Optional, Set, Tuple
from bridge.play_types import Card

# ── 常量 ──
_RANK_TO_BIT: Dict[str, int] = {
    '2': 2, '3': 3, '4': 4, '5': 5, '6': 6, '7': 7, '8': 8,
    '9': 9, 'T': 10, 'J': 11, 'Q': 12, 'K': 13, 'A': 14,
}
_BIT_TO_RANK: Dict[int, str] = {v: k for k, v in _RANK_TO_BIT.items()}

_SUIT_OFFSET: Dict[str, int] = {'♠': 0, '♥': 16, '♦': 32, '♣': 48}
_SUIT_MASK: Dict[str, int] = {s: 0xFFFF << off for s, off in _SUIT_OFFSET.items()}
_SUIT_NAMES = ['♠', '♥', '♦', '♣']
_SUIT_IDX = {'♠': 0, '♥': 1, '♦': 2, '♣': 3}

# ── Card ↔ Bit ──

def card_to_bit(card: Card) -> int:
    """单张牌 → 绝对 64-bit 位图（含花色偏移）。"""
    suit_off = _SUIT_OFFSET.get(card.suit, 0)
    rank_bit = _RANK_TO_BIT.get(card.rank, 2)
    return (1 << rank_bit) << suit_off


def card_to_suit_rank(card: Card) -> Tuple[int, int]:
    """单张牌 → (suit_idx, rank_bit)。rank_bit = 位位置（2-14），非移位后值。"""
    return _SUIT_IDX.get(card.suit, 0), _RANK_TO_BIT.get(card.rank, 2)


def bit_to_card(card_bit: int) -> Card:
    """绝对 64-bit 位图 → Card。取最低 set bit 的花色+rank。"""
    # 找到哪个 suit 段有 bit
    for s_idx, s_name in enumerate(_SUIT_NAMES):
        shift = s_idx * 16
        suit_bits = (card_bit >> shift) & 0xFFFF
        if suit_bits:
            # 找最低 set bit 的 rank
            rank_val = (suit_bits & -suit_bits).bit_length() - 1
            if rank_val >= 2:
                rank = _BIT_TO_RANK.get(rank_val, '2')
                return Card(suit=s_name, rank=rank)
    raise ValueError(f"Invalid card_bit: {card_bit}")


# ── 手牌 ↔ Bitmap ──

def cards_to_hand_bits(cards: List[Card]) -> int:
    """List[Card] → 64-bit 手牌位图。"""
    bits = 0
    for c in cards:
        bits |= card_to_bit(c)
    return bits


def hand_bits_to_cards(bits: int) -> List[Card]:
    """64-bit 手牌位图 → List[Card]。"""
    cards = []
    for s_idx in range(4):
        shift = s_idx * 16
        suit_bits = (bits >> shift) & 0xFFFF
        for rank_val in range(2, 15):
            if suit_bits & (1 << rank_val):
                cards.append(Card(suit=_SUIT_NAMES[s_idx],
                                  rank=_BIT_TO_RANK[rank_val]))
    return cards


def world_to_bits(world: Dict[str, List[Card]]) -> Dict[str, int]:
    """{pos: List[Card]} → {pos: int}。"""
    return {pos: cards_to_hand_bits(cards) for pos, cards in world.items()}


def world_from_bits(world_bits: Dict[str, int]) -> Dict[str, List[Card]]:
    """{pos: int} → {pos: List[Card]}。"""
    return {pos: hand_bits_to_cards(bits) for pos, bits in world_bits.items()}


def clone_world_bits(world: Dict[str, int]) -> Dict[str, int]:
    """浅拷贝 world 位图（仅复制 4 个 int）。"""
    return dict(world)


# ── 位图操作 ──

def hand_remove_card(hand_bits: int, card: Card) -> int:
    """从手牌位图中移除一张牌。"""
    return hand_bits & ~card_to_bit(card)


def hand_remove_bit(hand_bits: int, card_bit: int) -> int:
    """从手牌位图中移除一个绝对位图。"""
    return hand_bits & ~card_bit


def hand_has_suit(hand_bits: int, suit: str) -> bool:
    """手牌是否有指定花色。"""
    return (hand_bits & _SUIT_MASK.get(suit, 0)) != 0


def hand_get_suit_bits(hand_bits: int, suit: str) -> int:
    """获取指定花色的位图（不含花色偏移，纯 rank bits）。"""
    off = _SUIT_OFFSET.get(suit, 0)
    return (hand_bits >> off) & 0xFFFF


def hand_count(hand_bits: int) -> int:
    """手牌张数。"""
    return (hand_bits & 0xFFFF).bit_count() + \
           ((hand_bits >> 16) & 0xFFFF).bit_count() + \
           ((hand_bits >> 32) & 0xFFFF).bit_count() + \
           ((hand_bits >> 48) & 0xFFFF).bit_count()


def iter_card_bits(hand_bits: int) -> List[int]:
    """遍历手牌中每张牌的绝对位图。"""
    result = []
    for s_idx in range(4):
        shift = s_idx * 16
        suit_bits = (hand_bits >> shift) & 0xFFFF
        for rank_val in range(2, 15):
            bit = 1 << rank_val
            if suit_bits & bit:
                result.append(bit << shift)
    return result


def hand_str(hand_bits: int) -> str:
    """调试用：位图 → 可读字符串。"""
    parts = []
    for s_idx, s_name in enumerate(_SUIT_NAMES):
        shift = s_idx * 16
        suit_bits = (hand_bits >> shift) & 0xFFFF
        ranks = []
        for rank_val in range(14, 1, -1):
            if suit_bits & (1 << rank_val):
                ranks.append(_BIT_TO_RANK[rank_val])
        if ranks:
            parts.append(s_name + ''.join(ranks))
        else:
            parts.append(s_name + '-')
    return ' '.join(parts)


# ── 批量转换 ──

def worlds_to_bits(worlds: List[Optional[Dict[str, List[Card]]]]) \
        -> List[Optional[Dict[str, int]]]:
    """worlds 列表：Card → Bitmap 批量转换。None 保持 None。"""
    return [world_to_bits(w) if w is not None else None for w in worlds]


# ── 花色比较辅助 ──

def card_bit_rank(card_bit: int) -> int:
    """从绝对位图取 rank 值（2-14）。"""
    # 找到最高 set bit 的位置（即 rank 值）
    for s_idx in range(4):
        shift = s_idx * 16
        suit_bits = (card_bit >> shift) & 0xFFFF
        if suit_bits:
            return (suit_bits & -suit_bits).bit_length() - 1
    return 2


def card_bit_suit_idx(card_bit: int) -> int:
    """从绝对位图取花色索引 0-3。"""
    for s_idx in range(4):
        if (card_bit >> (s_idx * 16)) & 0xFFFF:
            return s_idx
    return 0


# ── Bitmap 版状态操作（对应 state_utils.apply_play_to_state 等）──

def _trick_winner_bits(trick_cards: List[Tuple[str, int]], trump: str) -> str:
    """从 bitmap trick_cards 确定赢家。trick_cards: [(pos, card_bit), ...]"""
    trump_suit_idx = _SUIT_IDX.get(trump, 4)
    best_pos = trick_cards[0][0]
    best_suit = card_bit_suit_idx(trick_cards[0][1])
    best_rank = card_bit_rank(trick_cards[0][1])

    for pos, cb in trick_cards[1:]:
        s = card_bit_suit_idx(cb)
        r = card_bit_rank(cb)
        if s == best_suit:
            if r > best_rank:
                best_pos, best_rank = pos, r
        elif s == trump_suit_idx:
            best_pos, best_suit, best_rank = pos, s, r
    return best_pos


def apply_play_to_state_bits(
    world_bits: Dict[str, int],
    position: str,
    card: Card,
    current_trick: dict,
    declarer_tricks: int,
    defender_tricks: int,
    contract_suit: str,
    contract_declarer: str,
    dummy: str,
) -> tuple:
    """Bitmap 版 apply_play_to_state。world_bits 被复制后修改（纯函数）。

    Returns: (new_world_bits, new_current_player, new_trick_state,
              new_declarer_tricks, new_defender_tricks, trick_complete)
    """
    from bridge.mcts.state_utils import POSITION_ORDER

    hands = {pos: bits for pos, bits in world_bits.items()}
    trick_cards = list(current_trick["cards"])
    trick_leader = current_trick.get("leader")
    trump = current_trick.get("trump")

    # 添加牌到当前墩
    trick_cards.append((position, card))
    if trick_leader is None:
        trick_leader = position

    # 从手牌中移除（位操作）
    card_bit = card_to_bit(card)
    hands[position] &= ~card_bit

    trick_complete = len(trick_cards) == 4

    if trick_complete:
        winning_pos = _trick_winner_bits(trick_cards, trump)
        if winning_pos in (contract_declarer, dummy):
            declarer_tricks += 1
        else:
            defender_tricks += 1
        new_trick = {"cards": [], "leader": None, "trump": trump}
        return hands, winning_pos, new_trick, declarer_tricks, defender_tricks, True
    else:
        idx = POSITION_ORDER.index(position)
        new_current = POSITION_ORDER[(idx + 1) % 4]
        new_trick = {"cards": trick_cards, "leader": trick_leader, "trump": trump}
        return hands, new_current, new_trick, declarer_tricks, defender_tricks, False


def get_playable_from_bits(hand_bits: int, current_trick: dict) -> List[Card]:
    """Bitmap 版 get_playable_from_hands。返回 Card 列表保持 API 兼容。"""
    trick_cards = current_trick.get("cards", [])
    if trick_cards:
        lead_suit = trick_cards[0][1].suit  # Card 对象，取 suit
        if hand_has_suit(hand_bits, lead_suit):
            # 只跟出同花色
            off = _SUIT_OFFSET.get(lead_suit, 0)
            suit_bits = (hand_bits >> off) & 0xFFFF
            cards = []
            for rank_val in range(2, 15):
                if suit_bits & (1 << rank_val):
                    cards.append(Card(suit=lead_suit,
                                      rank=_BIT_TO_RANK[rank_val]))
            return cards
    # 无跟花色限制，所有牌都可出
    return hand_bits_to_cards(hand_bits)


def get_current_trick_state_bits(state) -> dict:
    """从 PlayState 提取当前墩信息（无变化，同 state_utils 版）。"""
    from bridge.mcts.state_utils import get_current_trick_state
    return get_current_trick_state(state)
