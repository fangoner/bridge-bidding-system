"""LLM 出牌输出校验层。

LLM 出牌后用规则校验，违规时回退到 DD 或 _select_best_card。
当前只有解析失败才兜底，逻辑错误不兜底。

校验规则：
1. 推荐牌是否在 playable 中（基本合法性）
2. 是否违反跟牌规则（必须跟领出花色，除非 void）
3. 是否犯"小牌盖大牌"错误（第二家跟小牌盖同伴大牌等明显错误）
4. 是否在能赢墩时出小牌输墩（第四家能赢却出小牌）
5. 是否违反将牌规则（有将定约中不当使用将牌）

校验失败时的回退策略：
- 优先回退到 DD（如果可用）
- DD 不可用则回退到 _select_best_card（规则化选牌）
"""

from typing import List, Optional, Tuple
from bridge.play_types import Card, PlayState, PlayPhase, PARTNERS


class ValidationResult:
    """校验结果。"""

    def __init__(self, valid: bool, violation: str = "", severity: str = ""):
        self.valid = valid          # 是否通过校验
        self.violation = violation  # 违规描述
        self.severity = severity    # "error" | "warning" | "info"

    def __repr__(self):
        if self.valid:
            return "ValidationResult(valid=True)"
        return f"ValidationResult(valid=False, severity={self.severity}, violation={self.violation!r})"


def validate_llm_play(card: Card, playable: List[Card], state: PlayState) -> ValidationResult:
    """校验 LLM 推荐的出牌是否合法且合理。

    Args:
        card: LLM 推荐的牌
        playable: 当前合法可出的牌列表
        state: 当前 PlayState

    Returns:
        ValidationResult
    """
    if card is None:
        return ValidationResult(False, "LLM未返回有效牌", "error")

    # ── 规则1：推荐牌必须在 playable 中（基本合法性）──
    if card not in playable:
        # 检查是否是同花色同点数但对象不同（Card 的 __eq__ 已处理）
        in_playable = any(c == card for c in playable)
        if not in_playable:
            return ValidationResult(
                False,
                f"推荐牌{card}不在可出牌列表中（合法选择: {[str(c) for c in playable[:5]]}）",
                "error"
            )

    # ── 规则2：跟牌规则（必须跟领出花色，除非 void）──
    # 这条规则由 engine.get_playable_cards() 保证，playable 已经过滤
    # 但 LLM 可能返回不在 playable 中的牌（已在规则1拦截），所以这里不需要重复检查

    # ── 规则3：第四家"能赢却出小牌输墩"检测 ──
    violation = _check_fourth_hand_winning(card, playable, state)
    if violation:
        return ValidationResult(False, violation, "warning")

    # ── 规则4：第二家"小牌盖大牌"错误检测 ──
    # 注意：这里只检测明显错误，不干预合理的"二家小"策略
    violation = _check_second_hand_cover(card, playable, state)
    if violation:
        return ValidationResult(False, violation, "warning")

    # ── 规则5：将牌使用合理性（有将定约）──
    violation = _check_trump_usage(card, playable, state)
    if violation:
        return ValidationResult(False, violation, "warning")

    return ValidationResult(True)


def _check_fourth_hand_winning(card: Card, playable: List[Card], state: PlayState) -> str:
    """检测第四家（最后出牌）是否能赢墩却出小牌输墩。

    第四家应该出"恰好能赢的最小牌"，如果手中有能赢的牌却出了不能赢的牌，
    这是明显错误（除非有特殊战术理由，如忍让）。

    Returns:
        违规描述字符串，无违规返回空字符串
    """
    current_trick = state.current_trick
    if len(current_trick.cards) != 3:
        return ""  # 不是第四家

    if not current_trick.cards:
        return ""

    lead_suit = current_trick.get_lead_suit()
    trump = state.contract.suit if state.contract.suit != "NT" else None

    # 找当前墩已出的最大牌
    best_card = None
    best_pos = None
    for pos, c in current_trick.cards:
        if best_card is None:
            best_card = c
            best_pos = pos
            continue
        # 将牌大于非将牌
        if trump and c.suit == trump and best_card.suit != trump:
            best_card = c
            best_pos = pos
        elif c.suit == lead_suit and best_card.suit == lead_suit:
            if c.rank_value > best_card.rank_value:
                best_card = c
                best_pos = pos
        elif trump and c.suit == trump and best_card.suit == trump:
            if c.rank_value > best_card.rank_value:
                best_card = c
                best_pos = pos

    # 检查当前出牌者是否能赢墩
    current_player = state.current_player
    declarer = state.contract.declarer
    dummy = state.dummy

    # 找出能赢墩的牌
    winners = []
    for c in playable:
        if _card_beats(c, best_card, lead_suit, trump):
            winners.append(c)

    if not winners:
        return ""  # 没有能赢的牌，出什么都行

    # 如果有能赢的牌，但 LLM 选的牌不能赢，且当前墩对己方重要，标记警告
    if not _card_beats(card, best_card, lead_suit, trump):
        # 判断这墩对谁重要
        # 如果同伴（partner）已经出了大牌可能赢墩，第四家不需要再赢
        partner = PARTNERS.get(current_player)
        if best_pos == partner:
            return ""  # 同伴在赢墩，不需要盖牌

        # 如果是防守方且这墩能击宕定约，必须赢
        is_defender = current_player not in (declarer, dummy)
        if is_defender:
            defender_needs = max(0, (14 - state.contract.tricks_needed) - state.defender_tricks)
            if defender_needs <= 1:
                return (f"第四家有能赢的牌{[str(w) for w in winners[:3]]}但选了{card}，"
                        f"防守方还需{defender_needs}墩击宕，应赢墩")

        # 庄家方残局阶段也必须赢
        declarer_needs = max(0, state.contract.tricks_needed - state.declarer_tricks)
        if not is_defender and declarer_needs <= 1:
            return (f"第四家有能赢的牌{[str(w) for w in winners[:3]]}但选了{card}，"
                    f"庄家方还需{declarer_needs}墩成约，应赢墩")

    return ""


def _check_second_hand_cover(card: Card, playable: List[Card], state: PlayState) -> str:
    """检测第二家是否犯了"小牌盖大牌"错误。

    标准防守原则：第二家跟小牌（保留大牌）。
    但如果领出的是大牌（如K），第二家有A却出小牌让K赢墩，这是错误（应该盖A）。
    注意：这只检测明显错误，不干预合理的"二家小"策略。

    Returns:
        违规描述字符串，无违规返回空字符串
    """
    current_trick = state.current_trick
    if len(current_trick.cards) != 1:
        return ""  # 不是第二家

    lead_card = current_trick.cards[0][1]
    lead_pos = current_trick.cards[0][0]
    lead_suit = lead_card.suit

    # 只检测同花色跟牌（不检测将吃情况）
    if card.suit != lead_suit:
        return ""

    # 领出的是大牌（J以上）
    if lead_card.rank_value < 9:  # J=9
        return ""

    # 第二家手中有比领出牌更大的牌，但选了更小的牌
    bigger_cards = [c for c in playable
                    if c.suit == lead_suit and c.rank_value > lead_card.rank_value]
    if not bigger_cards:
        return ""  # 没有更大的牌

    # 如果选的牌比领出牌小，且手中有更大的牌
    if card.rank_value < lead_card.rank_value:
        # 判断是否是合理的"二家小"策略
        # 如果领出的是A，第二家有K，出小牌是合理的（不浪费K）
        if lead_card.rank == "A":
            return ""

        # 如果领出的是K，第二家有A，应该盖A（否则K赢墩）
        if lead_card.rank == "K" and any(c.rank == "A" for c in bigger_cards):
            # 但如果是防守方且领出的是同伴，不应该盖（同伴在赢墩）
            current_player = state.current_player
            partner = PARTNERS.get(current_player)
            if lead_pos == partner:
                return ""  # 同伴领出K，不应盖A
            return (f"第二家有A但选了{card}，领出{lead_card}会赢墩，应盖A")

    return ""


def _check_trump_usage(card: Card, playable: List[Card], state: PlayState) -> str:
    """检测将牌使用是否合理（有将定约）。

    检测场景：
    - 防守方在非将牌花色有牌时，不应该用将牌将吃（除非能赢墩）
    - 庄家方在能跟花色时，不应该用将牌将吃（除非战术需要）

    注意：这条规则较宽松，只检测明显错误。

    Returns:
        违规描述字符串，无违规返回空字符串
    """
    trump = state.contract.suit
    if trump == "NT":
        return ""  # 无将定约

    current_trick = state.current_trick
    if not current_trick.cards:
        return ""  # 领出阶段不检测将牌使用

    lead_suit = current_trick.get_lead_suit()

    # 如果选的是将牌，但手中有领出花色的牌，这是违规（必须跟花色）
    # 但这条规则由 engine.get_playable_cards() 保证，playable 已经过滤
    # 所以这里只检测：选将牌将吃时，是否真的需要将吃

    if card.suit != trump:
        return ""  # 不是将牌，不检测

    # 选了将牌将吃，检查是否合理
    # 如果手中有领出花色的牌，不可能选将牌（playable 已过滤）
    # 所以这里能选将牌，说明手中没有领出花色的牌（void）

    # 将吃是否合理：如果当前墩同伴在赢，不需要将吃
    current_player = state.current_player
    partner = PARTNERS.get(current_player)

    # 找当前墩已出的最大牌
    best_card = None
    best_pos = None
    for pos, c in current_trick.cards:
        if best_card is None:
            best_card = c
            best_pos = pos
            continue
        if trump and c.suit == trump and best_card.suit != trump:
            best_card = c
            best_pos = pos
        elif c.suit == lead_suit and best_card.suit == lead_suit:
            if c.rank_value > best_card.rank_value:
                best_card = c
                best_pos = pos

    # 如果同伴在赢墩，且赢的牌已经够大，不需要将吃
    if best_pos == partner:
        # 同伴在赢墩，检查是否真的需要将吃
        # 如果同伴的牌已经很大（如A），不需要将吃
        if best_card.rank_value >= 12:  # A=12, K=11
            return (f"同伴{partner}已出{best_card}赢墩，不需要将吃{card}，"
                    f"应垫其他花色小牌")

    return ""


def _card_beats(card: Card, target: Card, lead_suit: str, trump: Optional[str]) -> bool:
    """判断 card 是否能赢过 target（在当前墩规则下）。

    Args:
        card: 要判断的牌
        target: 当前最大牌
        lead_suit: 领出花色
        trump: 将牌花色（None表示无将定约）
    """
    # 将牌大于非将牌
    if trump:
        if card.suit == trump and target.suit != trump:
            return True
        if card.suit != trump and target.suit == trump:
            return False
        if card.suit == trump and target.suit == trump:
            return card.rank_value > target.rank_value

    # 同花色比较
    if card.suit == target.suit:
        return card.rank_value > target.rank_value

    # card 不是将牌，也不是 target 花色，不能赢
    if card.suit != lead_suit:
        return False

    # card 是领出花色，target 不是（target 是将牌的情况已处理）
    if target.suit != lead_suit and (not trump or target.suit != trump):
        return True  # target 既不是将牌也不是领出花色，不可能（除非是第一张）

    return False
