from typing import Dict, List, Optional

from bridge.play_types import Card, PlayState, POSITION_ORDER

try:
    from endplay import Deal
    from endplay.types import Denom, Player
    ENDPLAY_AVAILABLE = True
except ImportError:
    ENDPLAY_AVAILABLE = False

SUIT_TO_SYMBOL = {"S": "♠", "H": "♥", "D": "♦", "C": "♣"}
SYMBOL_TO_SUIT = {"♠": "spades", "♥": "hearts", "♦": "diamonds", "♣": "clubs"}
SUIT_DISPLAY_ORDER = ["♠", "♥", "♦", "♣"]
RANK_DESC = ["A", "K", "Q", "J", "T", "9", "8", "7", "6", "5", "4", "3", "2"]

POSITION_TO_PLAYER = {"北": Player.north, "东": Player.east, "南": Player.south, "西": Player.west}
SUIT_TO_DENOM = {"♠": Denom.spades, "♥": Denom.hearts, "♦": Denom.diamonds, "♣": Denom.clubs, "NT": Denom.nt}


def cards_to_hand_str(cards: List[Card]) -> str:
    """Card列表 → SHDC顺序的手牌字符串，如 'AQJ5 KQJ8 765 43'"""
    groups = {s: [] for s in SUIT_DISPLAY_ORDER}
    for c in cards:
        groups[c.suit].append(c.rank)
    parts = []
    for s in SUIT_DISPLAY_ORDER:
        ranks = groups[s]
        ranks.sort(key=lambda r: RANK_DESC.index(r) if r in RANK_DESC else 99)
        parts.append("".join(ranks) if ranks else "-")
    return " ".join(parts)


def hand_str_to_cards(s: str) -> List[Card]:
    """'AQJ5 KQJ8 765 -' → List[Card]"""
    cards = []
    parts = s.strip().split()
    for i, suit in enumerate(SUIT_DISPLAY_ORDER):
        if i >= len(parts):
            break
        ranks_str = parts[i]
        if ranks_str in ("-", "", "—"):
            continue
        for rank in ranks_str:
            if rank.upper() in "AKQJT98765432":
                cards.append(Card(suit=suit, rank=rank.upper()))
    return cards


def clone_hands(hands: Dict[str, List[Card]]) -> Dict[str, List[Card]]:
    """浅拷贝手牌字典。Card是值对象（__eq__按值），无需重建。"""
    return {pos: list(cards) for pos, cards in hands.items()}


def trick_winner(trick_cards: list, trump: str) -> str:
    """判断一墩的赢家位置。

    Args:
        trick_cards: [(position, Card), ...] 至少1张牌
        trump: 将牌花色，"NT"表示无将

    Returns:
        赢家位置字符串（"北"/"东"/"南"/"西"）
    """
    if not trick_cards:
        return ""
    lead_suit = trick_cards[0][1].suit
    winning_pos, winning_card = trick_cards[0]
    for pos, card in trick_cards[1:]:
        if trump and trump != "NT":
            if card.suit == trump:
                if winning_card.suit != trump or card.rank_value > winning_card.rank_value:
                    winning_pos, winning_card = pos, card
            elif card.suit == lead_suit and winning_card.suit != trump:
                if card.rank_value > winning_card.rank_value:
                    winning_pos, winning_card = pos, card
        else:
            if card.suit == lead_suit and card.rank_value > winning_card.rank_value:
                winning_pos, winning_card = pos, card
    return winning_pos


def playstate_to_deal(state: PlayState) -> Optional["Deal"]:
    """从PlayState当前手牌构造endplay Deal对象"""
    if not ENDPLAY_AVAILABLE:
        return None
    # 按北东南西顺序构建PBN手牌
    pbn_hands = []
    for pos_cn in ["北", "东", "南", "西"]:
        cards = state.hands.get(pos_cn, [])
        hand_str = cards_to_hand_str(cards)
        # PBN格式：S.H.D.C，用.分隔，空花色用空字符串
        parts = hand_str.split()
        parts = ["" if p == "-" else p for p in parts]
        while len(parts) < 4:
            parts.append("")
        pbn_hands.append(".".join(parts))
    pbn_str = f"N:{' '.join(pbn_hands)}"
    return Deal(pbn_str)


def suit_to_endplay_denom(suit: str) -> "Denom":
    """花色符号 → endplay Denom"""
    if not ENDPLAY_AVAILABLE:
        return None
    return SUIT_TO_DENOM.get(suit, Denom.nt)


def position_to_endplay_player(pos: str) -> "Player":
    """中文位置 → endplay Player"""
    if not ENDPLAY_AVAILABLE:
        return None
    return POSITION_TO_PLAYER.get(pos, Player.north)


def get_current_trick_state(state: PlayState) -> dict:
    """提取当前墩的精简状态，用于MCTS节点"""
    trick = state.current_trick
    return {
        "cards": list(trick.cards),  # List[(pos, Card)]
        "leader": trick.leader,
        "trump": trick.trump,
    }


def apply_play_to_state(
    hands: Dict[str, List[Card]],
    position: str,
    card: Card,
    current_trick: dict,
    declarer_tricks: int,
    defender_tricks: int,
    contract_suit: str,
    contract_declarer: str,
    dummy: str,
) -> tuple:
    """在给定手牌状态上执行一次出牌，返回更新后的所有状态。

    这是一个纯函数，不修改输入——返回新的副本。
    用于MCTS在节点间传播状态。

    Returns:
        (new_hands, new_current_player, new_trick_state,
         new_declarer_tricks, new_defender_tricks, trick_complete)
    """
    hands = clone_hands(hands)
    trick_cards = list(current_trick["cards"])
    trick_leader = current_trick.get("leader")
    trump = current_trick.get("trump")

    # 添加牌到当前墩
    trick_cards.append((position, card))
    if trick_leader is None:
        trick_leader = position

    # 从手牌中移除
    hands[position].remove(card)

    trick_complete = len(trick_cards) == 4

    if trick_complete:
        winning_pos = trick_winner(trick_cards, trump)
        if winning_pos in (contract_declarer, dummy):
            declarer_tricks += 1
        else:
            defender_tricks += 1

        new_trick = {"cards": [], "leader": None, "trump": trump}
        new_current = winning_pos
        return hands, new_current, new_trick, declarer_tricks, defender_tricks, True
    else:
        idx = POSITION_ORDER.index(position)
        new_current = POSITION_ORDER[(idx + 1) % 4]
        new_trick = {
            "cards": trick_cards,
            "leader": trick_leader,
            "trump": trump,
        }
        return hands, new_current, new_trick, declarer_tricks, defender_tricks, False


def get_playable_from_hands(hands: Dict[str, List[Card]], position: str,
                             current_trick: dict) -> List[Card]:
    """从手牌状态获取合法出牌（跟花色规则）"""
    hand = hands.get(position, [])
    if not hand:
        return []
    trick_cards = current_trick.get("cards", [])
    if not trick_cards:
        return list(hand)
    lead_suit = trick_cards[0][1].suit
    same = [c for c in hand if c.suit == lead_suit]
    return same if same else list(hand)
