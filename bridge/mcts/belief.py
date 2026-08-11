"""叫牌/打牌过程中的已知事实提取工具。

Phase 0a 重写：BeliefTracker 已移除（均匀采样不需要粒子加权）。
保留 void 收集和信号证据收集两个工具函数。

void 收集 → 用于均匀采样的仅 void 验证（void 是硬事实）
信号收集 → 用于 LLM prompt 注入（不影响采样）
"""

from typing import Dict, List, Set, Tuple

from bridge.play_types import Card, PlayState


def collect_voids(state: PlayState) -> Dict[str, Set[str]]:
    """从已完成的墩和当前墩中提取 void 信息。

    当某位置不跟领出花色时，该位置在该花色上为 void。
    这是硬事实，不是推理——看到了就必须遵守。

    Returns:
        {position: set(suits)} — 每个位置已知 void 的花色集合
    """
    voids: Dict[str, Set[str]] = {}

    def _check_trick(cards: list):
        if not cards:
            return
        lead_suit = cards[0][1].suit
        for pos, card in cards:
            if card.suit != lead_suit:
                voids.setdefault(pos, set()).add(lead_suit)

    for trick in state.tricks:
        _check_trick(trick.cards)
    _check_trick(state.current_trick.cards)
    return voids


def collect_signal_evidence(state: PlayState) -> List[Tuple[str, str, bool]]:
    """从已完成的墩和当前墩中收集防守方信号证据。

    防守方跟领出花色时：
    - 高牌（≥8）= 欢迎 → 暗示该花色较长
    - 低牌（<8）= 不欢迎 → 暗示该花色较短

    注意：信号可靠性低，不用于采样。仅用于 LLM prompt 注入。

    Returns:
        [(position, suit, is_high)] — 信号证据列表
    """
    declarer = state.contract.declarer
    dummy = state.dummy
    evidence: List[Tuple[str, str, bool]] = []

    def _check_trick(cards: list):
        if not cards:
            return
        lead_suit = cards[0][1].suit
        for pos, card in cards:
            if pos in (declarer, dummy):
                continue
            if card.suit != lead_suit:
                continue
            is_high = card.rank_value >= 7  # T=10 rank_value, 8+ is high (T/J/Q/K/A)
            evidence.append((pos, lead_suit, is_high))

    for trick in state.tricks:
        _check_trick(trick.cards)
    _check_trick(state.current_trick.cards)
    return evidence
