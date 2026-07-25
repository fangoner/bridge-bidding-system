"""防守信号模型。

显式编码三类桥牌防守信号：
1. 态度信号（Attitude）：跟领出花色时，高牌=欢迎续攻，低牌=不欢迎
2. 张数信号（Count）：同花色先大后小=偶数张，先小后大=奇数张
3. 花色偏好信号（Suit Preference）：特定情境下（如将吃后垫牌、首攻方第二墩），
   高牌=高级别花色(♠>♥)，低牌=低级别花色(♦>♣)

本模块负责：
- 从已完成的墩中提取信号证据
- 生成可注入 LLM 防守提示词的文本（同伴已发信号）
- 提供给采样器作为软约束（已在 belief.py 中实现权重调整）

信号解读规则遵循标准自然叫牌法的防守信号约定。
"""

from typing import List, Dict, Tuple, Optional, Set
from collections import defaultdict

from bridge.play_types import Card, PlayState, POSITION_ORDER, PARTNERS
from config import SIGNAL_MIN_RANK


# 花色级别（用于花色偏好信号解读）
SUIT_RANK = {"♣": 1, "♦": 2, "♥": 3, "♠": 4}


class SignalEvidence:
    """单条信号证据。"""

    def __init__(self, signal_type: str, position: str, suit: str,
                 is_high: bool, trick_num: int, context: str = ""):
        self.signal_type = signal_type  # "attitude" | "count" | "suit_preference"
        self.position = position        # 发信号的位置
        self.suit = suit                # 相关花色
        self.is_high = is_high          # 高牌=True，低牌=False
        self.trick_num = trick_num      # 第几墩
        self.context = context          # 上下文描述（如"将吃后垫牌"）

    def interpret(self) -> str:
        """解读信号含义为自然语言。"""
        if self.signal_type == "attitude":
            if self.is_high:
                return f"欢迎续攻{self.suit}（暗示{self.suit}较长或有实力）"
            else:
                return f"不欢迎续攻{self.suit}（暗示{self.suit}较短或无实力）"
        elif self.signal_type == "count":
            if self.is_high:
                return f"{self.suit}偶数张（先大后小）"
            else:
                return f"{self.suit}奇数张（先小后大）"
        elif self.signal_type == "suit_preference":
            if self.is_high:
                return f"偏好高级别花色（♠/♥）"
            else:
                return f"偏好低级别花色（♦/♣）"
        return "未知信号"

    def __repr__(self):
        return (f"Signal({self.signal_type}, {self.position}, {self.suit}, "
                f"{'高' if self.is_high else '低'}, 墩{self.trick_num})")


def collect_all_signals(state: PlayState) -> List[SignalEvidence]:
    """从已完成的墩和当前墩中收集所有防守方信号证据。

    信号优先级（同一张牌只解读一种信号）：
    1. 态度信号：防守方跟领出花色时（首墩或新花色领出时最有效）
    2. 张数信号：态度已明确后，同花色第二次跟牌时
    3. 花色偏好信号：将吃后垫牌、或不能跟花色时垫牌

    Returns:
        SignalEvidence 列表，按墩数排序
    """
    declarer = state.contract.declarer
    dummy = state.dummy
    defenders = [p for p in POSITION_ORDER if p not in (declarer, dummy)]

    # 记录每个防守方在每个花色上的跟牌历史（用于张数信号判断）
    # {position: {suit: [(trick_num, card), ...]}}
    follow_history: Dict[str, Dict[str, List[Tuple[int, Card]]]] = defaultdict(
        lambda: defaultdict(list))

    signals: List[SignalEvidence] = []

    def _process_trick(trick_cards: list, trick_idx: int):
        if not trick_cards:
            return
        lead_suit = trick_cards[0][1].suit

        for pos, card in trick_cards:
            if pos not in defenders:
                continue

            # 情况1：跟领出花色 → 态度信号
            if card.suit == lead_suit:
                is_high = card.rank_value >= SIGNAL_MIN_RANK
                # 判断是否是该花色第一次跟牌（态度信号），还是第二次（张数信号）
                history = follow_history[pos][lead_suit]
                if len(history) == 0:
                    # 第一次跟该花色 → 态度信号
                    signals.append(SignalEvidence(
                        signal_type="attitude",
                        position=pos, suit=lead_suit,
                        is_high=is_high, trick_num=trick_idx,
                        context=f"第{trick_idx}墩跟{lead_suit}态度信号"
                    ))
                else:
                    # 第二次跟该花色 → 张数信号
                    prev_card = history[-1][1]
                    # 先大后小=偶数张，先小后大=奇数张
                    is_even = prev_card.rank_value > card.rank_value
                    signals.append(SignalEvidence(
                        signal_type="count",
                        position=pos, suit=lead_suit,
                        is_high=is_even,  # is_high 在 count 语境下表示"偶数张"
                        trick_num=trick_idx,
                        context=f"第{trick_idx}墩跟{lead_suit}张数信号"
                    ))
                follow_history[pos][lead_suit].append((trick_idx, card))

            # 情况2：不跟领出花色（垫牌/将吃后垫牌）→ 花色偏好信号
            elif card.suit != lead_suit and card.suit != state.contract.suit:
                # 垫牌花色偏好：高牌=高级别，低牌=低级别
                is_high = card.rank_value >= SIGNAL_MIN_RANK
                signals.append(SignalEvidence(
                    signal_type="suit_preference",
                    position=pos, suit=card.suit,
                    is_high=is_high, trick_num=trick_idx,
                    context=f"第{trick_idx}墩垫{card.suit}花色偏好信号"
                ))

    # 处理已完成墩
    for trick_idx, trick in enumerate(state.tricks, 1):
        _process_trick(trick.cards, trick_idx)

    # 处理当前墩（如果当前墩是第 N 墩，trick_idx = len(tricks)+1）
    if state.current_trick.cards:
        current_trick_idx = len(state.tricks) + 1
        _process_trick(state.current_trick.cards, current_trick_idx)

    return signals


def get_partner_signals(state: PlayState, current_player: str) -> List[SignalEvidence]:
    """获取当前出牌者的同伴已发的所有信号。

    Args:
        state: 当前 PlayState
        current_player: 当前出牌者位置

    Returns:
        同伴发出的信号列表（按墩数排序）
    """
    partner = PARTNERS.get(current_player)
    if partner is None:
        return []

    all_signals = collect_all_signals(state)
    return [s for s in all_signals if s.position == partner]


def format_partner_signals_for_prompt(state: PlayState, current_player: str) -> str:
    """格式化同伴已发信号，用于注入 LLM 防守提示词。

    Args:
        state: 当前 PlayState
        current_player: 当前出牌者位置

    Returns:
        格式化的信号文本（如无信号返回空字符串）
    """
    # 只对防守方有意义
    declarer = state.contract.declarer
    dummy = state.dummy
    if current_player in (declarer, dummy):
        return ""

    partner_signals = get_partner_signals(state, current_player)
    if not partner_signals:
        return ""

    lines = ["\n\n## 同伴已发防守信号（按墩顺序）"]
    for s in partner_signals:
        lines.append(f"- 第{s.trick_num}墩 {s.position} {s.context}: {s.interpret()}")

    lines.append("\n**信号解读要点**:")
    lines.append("- 态度信号优先于张数信号，首次跟花色时解读为态度")
    lines.append("- 同伴欢迎的花色优先续攻，不欢迎的花色应转攻")
    lines.append("- 张数信号帮助判断该花色分布，用于读牌和后续防守策略")
    return "\n".join(lines)


def get_signal_constraints(state: PlayState) -> Dict[str, Dict[str, int]]:
    """从信号证据中提取对采样器的软约束。

    Returns:
        {position: {suit: expected_length_hint}}
        expected_length_hint: 正数=偏长，负数=偏短，0=中性
    """
    signals = collect_all_signals(state)
    constraints: Dict[str, Dict[str, int]] = defaultdict(lambda: defaultdict(int))

    for s in signals:
        if s.signal_type == "attitude":
            # 态度信号：高牌=欢迎=偏长，低牌=不欢迎=偏短
            constraints[s.position][s.suit] += 1 if s.is_high else -1
        elif s.signal_type == "count":
            # 张数信号：偶数张（is_high=True）通常意味着4/6张，
            # 奇数张（is_high=False）通常意味着3/5张
            # 这里只做轻微调整，因为张数信号信息量较小
            if s.is_high:
                constraints[s.position][s.suit] += 0.5
            else:
                constraints[s.position][s.suit] -= 0.5

    return dict(constraints)
