"""桥牌基本打牌规则校验层。

LLM 出牌后用规则校验，防止犯低级错误。
错误级别:
  - critical: 必须纠正（如第四家能赢定约却不赢、非法牌）
  - error: 明显错误应纠正（如浪费大牌打同伴赢墩、二家不必要打大牌）
  - warning: 可疑但可能是战术选择，记录警告但不强制

校验规则集:
1. 合法性: 推荐牌必须在 playable 中
2. 第二家原则: 小牌跟小、大牌盖大牌、不浪费大牌
3. 第三家原则: 同伴出小要上大牌、同伴赢墩不超打、经济用牌
4. 第四家原则: 能赢则用最小牌赢、同伴赢则出最小牌、不能赢则出安全牌
5. 将牌原则: 将吃用最小将牌、不将吃同伴赢墩、有赢墩不将吃
6. 连接张出牌: AK出K、KQ出Q、QJ出J（不浪费大牌）
7. 赢墩经济: 赢墩永远用恰好能赢的最小牌
8. 垫牌选择: 优先垫输张、保留赢墩潜力、不垫可能做大的牌
9. 防守不帮飞: 不领出/回出庄家可能嵌张的花色
10. 关键墩必赢: 定约成败相关的墩必须赢
"""

from typing import List, Optional, Tuple
from bridge.play_types import Card, PlayState, PARTNERS, RANK_ORDER

RANK_VALUE = {r: i for i, r in enumerate(RANK_ORDER)}


class ValidationResult:
    def __init__(self, valid: bool, violation: str = "", severity: str = "info",
                 suggested_card: Card = None):
        self.valid = valid
        self.violation = violation
        self.severity = severity
        self.suggested_card = suggested_card

    def __repr__(self):
        if self.valid:
            return "ValidationResult(valid=True)"
        return (f"ValidationResult(valid=False, severity={self.severity}, "
                f"violation={self.violation!r}, suggested={self.suggested_card})")


def validate_llm_play(card: Card, playable: List[Card], state: PlayState) -> ValidationResult:
    if card is None:
        return ValidationResult(False, "LLM未返回有效牌", "critical")

    # ── 1. 基本合法性 ──
    if not any(c == card for c in playable):
        return ValidationResult(
            False,
            f"推荐牌{card}不在可出牌列表中",
            "critical",
            suggested_card=playable[0] if playable else None,
        )

    # ── 收集当前墩信息 ──
    trick = state.current_trick
    n_cards = len(trick.cards)
    current = state.current_player
    partner = PARTNERS.get(current)
    declarer = state.contract.declarer
    dummy = state.dummy
    trump = state.contract.suit if state.contract.suit != "NT" else None
    is_declarer_side = current in (declarer, dummy)
    lead_suit = trick.get_lead_suit() if trick.cards else None
    my_hand = state.hands.get(current, [])

    # 计算各方还需墩数
    declarer_needs = max(0, state.contract.tricks_needed - state.declarer_tricks)
    defender_needs = max(0, (14 - state.contract.tricks_needed) - state.defender_tricks)
    tricks_left = 13 - state.declarer_tricks - state.defender_tricks
    is_critical_trick = (declarer_needs <= 1 and is_declarer_side) or \
                        (defender_needs <= 1 and not is_declarer_side)

    # 当前墩最大牌及位置
    best_card, best_pos = _get_current_best(trick, trump) if trick.cards else (None, None)
    winners = _get_winning_cards(playable, best_card, lead_suit, trump) if trick.cards else []
    partner_winning = (best_pos == partner) if best_pos else False

    # ── 2. 最高优先级：垫牌保护（绝对不能垫A/有保护K）──
    if lead_suit and card.suit != lead_suit and (not trump or card.suit != trump):
        result = _check_discard(card, playable, state, trump)
        if result and not result.valid:
            return result

    # ── 3. 最高优先级：不要将吃同伴赢墩 ──
    if trump and card.suit == trump and trick.cards:
        result = _check_ruff_partner(card, playable, state, trump,
                                      best_card, best_pos, partner, partner_winning)
        if result and not result.valid:
            return result

    # ── 4. 第二家（1张已出）──
    if n_cards == 1:
        result = _check_second_hand(card, playable, state, lead_suit, trump,
                                     best_card, best_pos, partner, winners)
        if result and not result.valid:
            return result

    # ── 5. 第三家（2张已出）──
    if n_cards == 2:
        result = _check_third_hand(card, playable, state, lead_suit, trump,
                                    best_card, best_pos, partner, winners, partner_winning)
        if result and not result.valid:
            return result

    # ── 6. 第四家（3张已出）──
    if n_cards == 3:
        result = _check_fourth_hand(card, playable, state, lead_suit, trump,
                                     best_card, best_pos, partner, winners,
                                     partner_winning, is_critical_trick)
        if result and not result.valid:
            return result

    # ── 7. 领出（0张已出）──
    if n_cards == 0:
        result = _check_lead(card, playable, state, trump, my_hand)
        if result and not result.valid:
            return result

    # ── 8. 通用：赢墩时用最小牌 ──
    if trick.cards and winners:
        if card in winners and len(winners) > 1:
            min_winner = min(winners, key=lambda c: c.rank_value)
            if card.rank_value > min_winner.rank_value:
                return ValidationResult(
                    False,
                    f"用{card}赢墩但有更小的赢张{min_winner}，应用最小牌赢墩",
                    "warning",
                    suggested_card=min_winner,
                )

    # ── 9. 通用：将吃用最小足够将牌 ──
    if trump and card.suit == trump and trick.cards and lead_suit and card.suit != lead_suit:
        result = _check_min_trump(card, playable, trump, best_card)
        if result and not result.valid:
            return result

    return ValidationResult(True)


# ══════════════════════════════════════════════════════════════
# 第二家规则
# ══════════════════════════════════════════════════════════════
def _check_second_hand(card: Card, playable: List[Card], state: PlayState,
                       lead_suit: str, trump: Optional[str],
                       lead_card: Card, lead_pos: str,
                       partner: str, winners: List[Card]) -> Optional[ValidationResult]:
    """第二家出牌规则:
    - 二家出小: 领出小牌(≤9)时跟小牌
    - 大牌盖大牌: 领出J/Q/K时用大牌盖打
    - 不盖同伴大牌: 同伴领出大牌时不盖
    - 不浪费A打小牌: A要留着吃大牌
    """
    following_suit = [c for c in playable if c.suit == lead_suit]
    if not following_suit:
        return None

    # 同伴领出时，不盖同伴的大牌（除非需要赢这墩）
    if lead_pos == partner:
        if lead_card.rank_value >= RANK_VALUE["J"]:
            if card.rank_value > lead_card.rank_value and card.rank in ("A", "K"):
                smaller_follow = [c for c in following_suit if c.rank_value < lead_card.rank_value]
                if smaller_follow:
                    return ValidationResult(
                        False,
                        f"同伴领出{lead_card}，不必用{card}超打，应出小牌",
                        "warning",
                        suggested_card=min(smaller_follow, key=lambda c: c.rank_value),
                    )
        return None

    # 对手领出
    # 领出小牌（9及以下），二家应跟小牌
    if lead_card.rank_value <= RANK_VALUE["9"]:
        min_follow = min(following_suit, key=lambda c: c.rank_value)
        if card.rank_value >= RANK_VALUE["J"]:
            # 如果手中都是大牌（没有更小的），那没办法
            small_cards = [c for c in following_suit if c.rank_value < RANK_VALUE["J"]]
            if small_cards:
                return ValidationResult(
                    False,
                    f"对手领出小牌{lead_card}，第二家不应出{card}，应跟小牌（二家出小原则）",
                    "error",
                    suggested_card=min(small_cards, key=lambda c: c.rank_value),
                )
        # 即使没出大牌，也应该出最小的
        if card.rank_value > min_follow.rank_value and min_follow.rank_value < RANK_VALUE["J"]:
            return ValidationResult(
                False,
                f"对手领出小牌{lead_card}，有更小的{min_follow}应跟小牌",
                "warning",
                suggested_card=min_follow,
            )
        return None

    # 领出大牌（J及以上）
    # 领出J：用Q/K/A盖（如果有且不是嵌张）
    # 领出Q：用K/A盖
    # 领出K：用A盖
    # 领出A：不盖（浪费）
    if lead_card.rank == "A":
        if card.rank == "A" or card.rank == "K":
            small_cards = [c for c in following_suit if c.rank_value < RANK_VALUE["J"]]
            if small_cards:
                return ValidationResult(
                    False,
                    f"对手领出A{lead_card.suit}，不应浪费{card}，应跟小牌",
                    "error",
                    suggested_card=min(small_cards, key=lambda c: c.rank_value),
                )
        return None

    # KQJ需要盖打
    if lead_card.rank in ("K", "Q", "J"):
        bigger = [c for c in following_suit if c.rank_value > lead_card.rank_value]
        if bigger:
            if card.rank_value < lead_card.rank_value:
                # 如果后面有同伴（第三家）且可能有大牌，不一定要盖
                # 但如果手中有A且对手领K，基本要盖
                if lead_card.rank == "K" and any(c.rank == "A" for c in bigger):
                    min_bigger = min(bigger, key=lambda c: c.rank_value)
                    return ValidationResult(
                        False,
                        f"对手领出{lead_card}，手中有{','.join(str(c) for c in bigger[:3])}"
                        f"应盖打（大牌盖大牌原则）",
                        "warning",
                        suggested_card=min_bigger,
                    )
                # 双张大牌不盖第一张（如Qx盖K的第二张），但这里无法判断长度
                # 所以只给warning不强制
        return None

    return None


# ══════════════════════════════════════════════════════════════
# 第三家规则
# ══════════════════════════════════════════════════════════════
def _check_third_hand(card: Card, playable: List[Card], state: PlayState,
                      lead_suit: str, trump: Optional[str],
                      best_card: Card, best_pos: str,
                      partner: str, winners: List[Card],
                      partner_winning: bool) -> Optional[ValidationResult]:
    """第三家出牌规则:
    - 同伴领出小牌: 三家出大牌
    - 同伴领出大牌且在赢: 不超打
    - 对手在赢: 用最小有效牌盖打
    - 经济原则: 逼出更大牌用最小牌
    """
    following_suit = [c for c in playable if c.suit == lead_suit]

    # 同伴在赢墩
    if partner_winning:
        # 如果同伴的牌已经是A，绝对不要超打
        if best_card.rank == "A":
            if card.rank_value > best_card.rank_value:
                return ValidationResult(
                    False,
                    f"同伴已出A赢墩，不要用{card}超打",
                    "error",
                    suggested_card=_safest_card(playable, lead_suit, trump),
                )
        # 如果同伴在赢，且我们有A/K等大牌，不要浪费大牌超打
        if card.rank_value > best_card.rank_value and card.rank in ("A", "K"):
            # 检查同伴是否可能被第四家盖过
            # 第四家还有位置，可能有更大的牌
            # 但如果同伴已经出了Q或更大，通常不用超打
            if best_card.rank_value >= RANK_VALUE["Q"]:
                safe_play = _safest_card(playable, lead_suit, trump)
                if safe_play and safe_play != card:
                    return ValidationResult(
                        False,
                        f"同伴出{best_card}目前赢墩，第四家可能盖牌，"
                        f"但不必浪费{card}（可保留看情况）",
                        "warning",
                        suggested_card=safe_play,
                    )
        return None

    # 对手在赢墩（左手敌方领出或第二家敌方大了）
    if following_suit:
        if winners:
            # 我们能赢这墩
            min_winner = min(winners, key=lambda c: c.rank_value)
            if card not in winners:
                # 不一定要必赢，但如果对手在赢且我们有赢张，在关键墩必须赢
                return ValidationResult(
                    False,
                    f"敌方目前赢墩，手中有赢张{min_winner}却出{card}，"
                    f"第三家应上大牌",
                    "warning",
                    suggested_card=min_winner,
                )
        else:
            # 不能赢这墩，出大牌逼庄家大牌（三家打大）
            # 打出最小的能逼出大牌的牌
            big_cards = [c for c in following_suit if c.rank_value >= RANK_VALUE["J"]]
            small_cards = [c for c in following_suit if c.rank_value < RANK_VALUE["J"]]
            if big_cards and card in small_cards:
                # 如果有大牌应该出大牌（除非大牌是A没有保护）
                # 但这有例外：保留A捉K等。只做warning。
                pass

    return None


# ══════════════════════════════════════════════════════════════
# 第四家规则
# ══════════════════════════════════════════════════════════════
def _check_fourth_hand(card: Card, playable: List[Card], state: PlayState,
                       lead_suit: str, trump: Optional[str],
                       best_card: Card, best_pos: str,
                       partner: str, winners: List[Card],
                       partner_winning: bool,
                       is_critical_trick: bool) -> Optional[ValidationResult]:
    """第四家出牌规则:
    - 同伴赢墩: 出最小牌
    - 敌方赢墩:
      - 关键墩必须赢
      - 非关键墩用最小能赢的牌赢
    - 不能赢: 出安全小牌
    """
    if partner_winning:
        # 同伴在赢墩，出最小的牌
        min_card = min(playable, key=lambda c: (c.suit_order, c.rank_value))
        if card.rank_value >= RANK_VALUE["Q"] and min_card.rank_value < card.rank_value:
            return ValidationResult(
                False,
                f"同伴已赢这墩，不要浪费大牌{card}，应跟最小牌",
                "error",
                suggested_card=min_card,
            )
        return None

    # 敌方在赢墩
    if winners:
        # 我们能赢这墩
        min_winner = min(winners, key=lambda c: c.rank_value)
        if is_critical_trick:
            # 关键墩必须赢
            if card not in winners:
                return ValidationResult(
                    False,
                    f"这墩关系定约成败！有赢张{min_winner}却出{card}，必须赢墩",
                    "critical",
                    suggested_card=min_winner,
                )
        if card in winners:
            # 赢墩用最小牌
            if card.rank_value > min_winner.rank_value:
                return ValidationResult(
                    False,
                    f"赢墩应用最小牌{min_winner}，不必用{card}",
                    "warning",
                    suggested_card=min_winner,
                )
        else:
            # 非关键墩但能赢，默认应该赢（除非明显要忍让）
            return ValidationResult(
                False,
                f"敌方赢墩，手中有赢张{min_winner}应赢墩",
                "warning",
                suggested_card=min_winner,
            )
    else:
        # 不能赢这墩，出最安全的牌（最小牌）
        min_card = min(playable, key=lambda c: (c.suit_order, c.rank_value))
        if card.rank_value >= RANK_VALUE["Q"] and min_card.rank_value < card.rank_value:
            return ValidationResult(
                False,
                f"此墩无法赢，不应垫大牌{card}，应垫小牌",
                "warning",
                suggested_card=min_card,
            )

    return None


# ══════════════════════════════════════════════════════════════
# 领出规则
# ══════════════════════════════════════════════════════════════
def _check_lead(card: Card, playable: List[Card], state: PlayState,
                trump: Optional[str], my_hand: List[Card]) -> Optional[ValidationResult]:
    """领出规则:
    - 不领出裸A（短套A）
    - 不从嵌张领大牌（如AQ领Q、KJ领J）
    - 连接张领大不领小（AK领K不领A，KQ领Q）
    """
    suit_cards = [c for c in my_hand if c.suit == card.suit]
    suit_len = len(suit_cards)
    ranks_in_suit = sorted([c.rank_value for c in suit_cards], reverse=True)

    # 领A：不领单张/双张A（容易被将吃或浪费）
    if card.rank == "A" and suit_len <= 2:
        # 例外：有将定约且A是将牌，可以领
        if trump and card.suit == trump:
            return None
        # 领A通常要求AK连张或长度足够
        has_king = any(c.rank == "K" for c in suit_cards)
        if not has_king and suit_len < 4:
            return ValidationResult(
                False,
                f"从{card.suit}套{card.rank}{'单张' if suit_len==1 else '双张'}领A风险大，"
                f"建议领安全花色",
                "warning",
            )

    # 领K：检查是否有A（AK领K是标准，但K单张/无A保护不领K）
    if card.rank == "K" and suit_len >= 2:
        has_ace = any(c.rank == "A" for c in suit_cards)
        has_queen = any(c.rank == "Q" for c in suit_cards)
        if not has_ace and not has_queen:
            # 孤立K领出风险大，但不强制禁止
            pass

    # 不从AQ嵌张领Q
    if card.rank == "Q":
        has_ace = any(c.rank == "A" for c in suit_cards)
        has_jack = any(c.rank == "J" for c in suit_cards)
        has_king = any(c.rank == "K" for c in suit_cards)
        if has_ace and not has_king and not has_jack:
            return ValidationResult(
                False,
                f"从AQ嵌张领Q是帮庄家飞牌，风险大",
                "warning",
            )

    # 不从KJ嵌张领J
    if card.rank == "J":
        has_king = any(c.rank == "K" for c in suit_cards)
        has_queen = any(c.rank == "Q" for c in suit_cards)
        if has_king and not has_queen:
            return ValidationResult(
                False,
                f"从KJ嵌张领J是帮庄家飞牌，风险大",
                "warning",
            )

    return None


# ══════════════════════════════════════════════════════════════
# 将牌检查
# ══════════════════════════════════════════════════════════════
def _check_ruff_partner(card: Card, playable: List[Card], state: PlayState,
                        trump: str, best_card: Card, best_pos: str,
                        partner: str, partner_winning: bool) -> Optional[ValidationResult]:
    """高优先级：同伴赢墩时不要将吃。"""
    if partner_winning and card.suit == trump:
        lead_suit = state.current_trick.get_lead_suit()
        if best_card and best_card.suit != trump:
            return ValidationResult(
                False,
                f"同伴{partner}正用{best_card}赢墩，不要将吃同伴",
                "error",
                suggested_card=_safest_card(playable, lead_suit, trump),
            )
    return None


def _check_min_trump(card: Card, playable: List[Card], trump: str,
                     best_card: Optional[Card]) -> Optional[ValidationResult]:
    """通用：将吃用最小足够将牌。"""
    trump_cards = [c for c in playable if c.suit == trump]
    if not trump_cards:
        return None
    need_value = best_card.rank_value if best_card and best_card.suit == trump else -1
    sufficient_trumps = [c for c in trump_cards if c.rank_value > need_value]
    if sufficient_trumps:
        best_trump = min(sufficient_trumps, key=lambda c: c.rank_value)
        if card.rank_value > best_trump.rank_value:
            return ValidationResult(
                False,
                f"将吃应用最小足够将牌{best_trump}，不必用{card}",
                "warning",
                suggested_card=best_trump,
            )
    return None


# ══════════════════════════════════════════════════════════════
# 垫牌检查
# ══════════════════════════════════════════════════════════════
def _check_discard(card: Card, playable: List[Card], state: PlayState,
                   trump: Optional[str]) -> Optional[ValidationResult]:
    """垫牌规则:
    - 不垫A
    - 不垫K（除非K确定被捉）
    - 不垫有保护的大牌
    - 优先垫最短套的小牌
    """
    if card.rank == "A":
        # 除非这墩已经被同伴用A赢了，否则垫A基本是错的
        small_cards = [c for c in playable
                       if c.rank_value <= RANK_VALUE["9"]]
        if small_cards:
            return ValidationResult(
                False,
                f"不应垫A！垫小牌",
                "critical",
                suggested_card=_choose_discard(playable),
            )

    if card.rank == "K":
        small_cards = [c for c in playable
                       if c.rank_value <= RANK_VALUE["9"]]
        if small_cards:
            # 检查K是否可能有赢墩潜力
            suit_cards = [c for c in state.hands.get(state.current_player, [])
                         if c.suit == card.suit]
            if len(suit_cards) >= 2:  # K有保护
                return ValidationResult(
                    False,
                    f"有保护的K不应垫掉，垫小牌",
                    "error",
                    suggested_card=_choose_discard(playable),
                )

    if card.rank == "Q":
        small_cards = [c for c in playable
                       if c.rank_value <= RANK_VALUE["7"]]
        if small_cards:
            suit_cards = [c for c in state.hands.get(state.current_player, [])
                         if c.suit == card.suit]
            if len(suit_cards) >= 3:  # Q有足够保护
                return ValidationResult(
                    False,
                    f"有保护的Q不应垫掉，垫小牌",
                    "warning",
                    suggested_card=_choose_discard(playable),
                )

    return None


# ══════════════════════════════════════════════════════════════
# 辅助函数
# ══════════════════════════════════════════════════════════════
def _get_current_best(trick, trump: Optional[str]) -> Tuple[Optional[Card], Optional[str]]:
    """获取当前墩的最大牌和位置。"""
    if not trick.cards:
        return None, None
    lead_suit = trick.get_lead_suit()
    best_card, best_pos = trick.cards[0][1], trick.cards[0][0]
    for pos, c in trick.cards[1:]:
        if _card_beats(c, best_card, lead_suit, trump):
            best_card, best_pos = c, pos
    return best_card, best_pos


def _card_beats(card: Card, target: Card, lead_suit: str, trump: Optional[str]) -> bool:
    if trump:
        if card.suit == trump and target.suit != trump:
            return True
        if card.suit != trump and target.suit == trump:
            return False
        if card.suit == trump and target.suit == trump:
            return card.rank_value > target.rank_value
    if card.suit == target.suit:
        return card.rank_value > target.rank_value
    if card.suit != lead_suit:
        return False
    if target.suit != lead_suit and (not trump or target.suit != trump):
        return True
    return False


def _get_winning_cards(playable: List[Card], best_card: Optional[Card],
                       lead_suit: str, trump: Optional[str]) -> List[Card]:
    """找出playable中能赢过当前best_card的牌。"""
    if best_card is None:
        return []
    return [c for c in playable if _card_beats(c, best_card, lead_suit, trump)]


def _safest_card(playable: List[Card], lead_suit: str, trump: Optional[str]) -> Card:
    """选择最安全的牌（通常是最小的跟牌/垫牌）。"""
    if lead_suit:
        same_suit = [c for c in playable if c.suit == lead_suit]
        if same_suit:
            return min(same_suit, key=lambda c: c.rank_value)
    non_trump = [c for c in playable if not trump or c.suit != trump]
    if non_trump:
        return min(non_trump, key=lambda c: (c.suit_order, c.rank_value))
    return min(playable, key=lambda c: c.rank_value)


def _choose_discard(playable: List[Card]) -> Card:
    """垫牌时选择最合适的牌（最小、最短套的小牌）。"""
    # 优先垫最小的牌
    # 优先垫已经垫过/明手已大的花色（这里信息不够，简单选最小牌）
    small_cards = [c for c in playable if c.rank_value <= RANK_VALUE["7"]]
    if small_cards:
        return min(small_cards, key=lambda c: (c.suit_order, c.rank_value))
    medium_cards = [c for c in playable if c.rank_value <= RANK_VALUE["9"]]
    if medium_cards:
        return min(medium_cards, key=lambda c: (c.suit_order, c.rank_value))
    return min(playable, key=lambda c: (c.suit_order, c.rank_value))


def suggest_rule_based_play(playable: List[Card], state: PlayState) -> Card:
    """基于规则的推荐出牌。用于LLM校验失败时的回退策略。

    比简单的_select_best_card更智能，遵循桥牌基本规则。
    """
    if len(playable) == 1:
        return playable[0]

    trick = state.current_trick
    n_cards = len(trick.cards)
    current = state.current_player
    partner = PARTNERS.get(current)
    trump = state.contract.suit if state.contract.suit != "NT" else None
    lead_suit = trick.get_lead_suit() if trick.cards else None
    declarer = state.contract.declarer
    dummy = state.dummy
    is_declarer_side = current in (declarer, dummy)
    my_hand = state.hands.get(current, [])

    declarer_needs = max(0, state.contract.tricks_needed - state.declarer_tricks)
    defender_needs = max(0, (14 - state.contract.tricks_needed) - state.defender_tricks)
    is_critical_trick = (declarer_needs <= 1 and is_declarer_side) or \
                        (defender_needs <= 1 and not is_declarer_side)

    best_card, best_pos = _get_current_best(trick, trump) if trick.cards else (None, None)
    winners = _get_winning_cards(playable, best_card, lead_suit, trump) if trick.cards else []
    partner_winning = (best_pos == partner) if best_pos else False
    following_suit = [c for c in playable if c.suit == lead_suit] if lead_suit else []

    # ── 领出 ──
    if n_cards == 0:
        return _suggest_lead(playable, state, my_hand, trump)

    # ── 同伴赢墩：出最小安全牌 ──
    if partner_winning:
        if following_suit:
            return min(following_suit, key=lambda c: c.rank_value)
        return _choose_discard(playable)

    # ── 有赢张 ──
    if winners:
        min_winner = min(winners, key=lambda c: c.rank_value)
        # 关键墩必须赢
        if is_critical_trick:
            return min_winner
        # 第四家通常要赢
        if n_cards == 3:
            return min_winner
        # 第三家如果对手在赢要赢
        if n_cards == 2 and best_pos not in (None, partner):
            return min_winner
        # 第二家如果有必要（比如对手领K且有A）
        if n_cards == 1 and best_card and best_card.rank in ("K", "Q", "J"):
            bigger = [c for c in following_suit if c.rank_value > best_card.rank_value]
            if bigger:
                return min(bigger, key=lambda c: c.rank_value)
        return min_winner

    # ── 没有赢张 ──
    if following_suit:
        # 第三家：三家打大（即使赢不了也要出大的逼庄家大牌）
        if n_cards == 2 and best_pos != partner:
            big_cards = [c for c in following_suit if c.rank_value >= RANK_VALUE["J"]]
            if big_cards:
                # 如果出J/Q能逼出K/A就出，否则出小
                return min(big_cards, key=lambda c: c.rank_value)
        # 第二家：跟最小牌
        return min(following_suit, key=lambda c: c.rank_value)

    # 垫牌或将吃
    return _choose_discard(playable)


def _suggest_lead(playable: List[Card], state: PlayState, my_hand: List[Card],
                  trump: Optional[str]) -> Card:
    """领出时的推荐。"""
    # 简单策略：优先领最长套的第四大牌，没有就领安全小牌
    # 统计各花色长度
    from collections import defaultdict
    suit_len = defaultdict(int)
    suit_ranks = defaultdict(list)
    for c in my_hand:
        suit_len[c.suit] += 1
        suit_ranks[c.suit].append(c)

    # 排除将牌花色（将牌首攻需要理由，简化处理：只在长将牌时考虑）
    leadable_suits = [s for s in suit_len if s != trump]

    # 找最长套
    if leadable_suits:
        longest_suit = max(leadable_suits, key=lambda s: (suit_len[s], -SUIT_ORDER_HELPER.get(s, 0)))
        suit_cards = sorted(suit_ranks[longest_suit], key=lambda c: c.rank_value)
        # 领第四大牌（长四），如果不够4张领最小
        if len(suit_cards) >= 4:
            # 长四是倒数第4大的牌（即第4小的牌）
            lead_card = suit_cards[3] if len(suit_cards) > 3 else suit_cards[0]
            # 但如果长四是大牌(≥J)，领小牌
            small = [c for c in suit_cards if c.rank_value <= RANK_VALUE["9"]]
            if small:
                lead_card = small[0]
        else:
            small = [c for c in suit_cards if c.rank_value <= RANK_VALUE["9"]]
            lead_card = small[0] if small else suit_cards[0]
        # 检查领出的牌是否在playable中
        if any(c == lead_card for c in playable):
            return lead_card

    # 默认出最小牌
    return min(playable, key=lambda c: (c.suit_order, c.rank_value))


SUIT_ORDER_HELPER = {"♣": 0, "♦": 1, "♥": 2, "♠": 3}
