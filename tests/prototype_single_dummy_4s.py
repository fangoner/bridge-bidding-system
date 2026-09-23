"""单明手精修原型：4♠ 清将 vs 顶张方案翻转验证。

背景（见 docs/坐庄评估改造_DD结合αμ与飞牌介入去留_20260922.md）：
- 4♠ 南庄，第2墩北领出。DD 前四名做成率 99.6~99.8% 几乎相同，blended 决胜把 ♦A 排前；
  实战应先清将（♠3→K→Q）避免方块被将吃——但 DD 全知评估看不出清将优势。
- 本脚本从"真实(单明手)视角"模拟：庄家策略只依赖公开信息（庄+明两手+已出牌），
  防家按信号模型防御，统计"可成率"（防家尝试将吃）。若清将路线可成率显著高于顶张路线 → 路径A验证通过。

合成出发点：第2墩北领出，0-0，四手牌（南北固定，东西按公开信息均匀发牌）。
候选首牌强制为北领出牌，后续全部走单明手策略。每次采样一套东西分布，跑完整 13 墩。

用法：python tests/prototype_single_dummy_4s.py
"""

import os
import random
import sys
from typing import Dict, List, Optional

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from bridge.play_types import Card, Contract, Trick, PlayState, PlayPhase, POSITION_ORDER, PARTNERS

TRUMP = "♠"
DECLARER = "南"
DUMMY = "北"
NEED_TRICKS = 10  # 4♠
N_SAMPLES = 250
RNG = random.Random(20260922)

# 固定南北两手
SOUTH_CARDS = [
    Card("♠", "K"), Card("♠", "Q"), Card("♠", "T"), Card("♠", "9"),
    Card("♠", "8"), Card("♠", "7"), Card("♥", "3"), Card("♥", "2"),
    Card("♦", "2"), Card("♣", "K"), Card("♣", "4"), Card("♣", "3"), Card("♣", "2"),
]
NORTH_CARDS = [
    Card("♠", "J"), Card("♠", "3"), Card("♥", "A"), Card("♥", "4"),
    Card("♦", "A"), Card("♦", "K"), Card("♦", "5"), Card("♦", "4"), Card("♦", "3"),
    Card("♣", "A"), Card("♣", "7"), Card("♣", "6"), Card("♣", "5"),
]

ALL_CARDS = [Card(suit=s, rank=r) for s in ["♠", "♥", "♦", "♣"] for r in ["A", "K", "Q", "J", "T", "9", "8", "7", "6", "5", "4", "3", "2"]]


def num_suit(hand: List[Card], suit: str) -> int:
    return sum(1 for c in hand if c.suit == suit)


def opp_trump_remaining(state: PlayState) -> int:
    played = sum(1 for t in state.tricks for _, c in t.cards if c.suit == TRUMP)
    played += sum(1 for _, c in state.current_trick.cards if c.suit == TRUMP)
    ns_remaining = num_suit(state.hands.get(DECLARER, []), TRUMP) + num_suit(state.hands.get(DUMMY, []), TRUMP)
    return 13 - played - ns_remaining


def trick_current_winner(trick: Trick):
    """返回 (位置, 牌)。无视未完成的张数，按将牌/领出规则判定当前最大。"""
    if not trick.cards:
        return None, None
    lead = trick.cards[0][1].suit
    wp, wc = trick.cards[0]
    for p, c in trick.cards[1:]:
        if TRUMP and TRUMP != lead:
            if c.suit == TRUMP and (wc.suit != TRUMP or c.rank_value > wc.rank_value):
                wp, wc = p, c
            elif c.suit == lead and wc.suit != TRUMP and c.rank_value > wc.rank_value:
                wp, wc = p, c
        else:
            if c.suit == lead and c.rank_value > wc.rank_value:
                wp, wc = p, c
    return wp, wc


def is_declarer_side(pos: str) -> bool:
    return pos in (DECLARER, DUMMY)


def cheapest_winning(playable: List[Card], wc, lead_suit) -> Optional[Card]:
    """返回能击败当前赢牌 wc 的最小牌；无法击败返回 None。"""
    beat = []
    for c in playable:
        if wc is None:
            beat.append(c)
            continue
        if TRUMP and lead_suit and TRUMP != lead_suit:
            if c.suit == TRUMP and (wc.suit != TRUMP or c.rank_value > wc.rank_value):
                beat.append(c)
            elif c.suit == lead_suit and wc.suit != TRUMP and c.rank_value > wc.rank_value:
                beat.append(c)
        else:
            if c.suit == lead_suit and c.rank_value > wc.rank_value:
                beat.append(c)
    return min(beat, key=lambda c: c.rank_value) if beat else None


def declarer_strategy(pos: str, state: PlayState, mode: str) -> Optional[Card]:
    """单明手庄家启发式策略。mode:
      patient = 连拔优先清将，将牌拔完再建立方块（预期安全线）
      greedy  = 先兑现方块顶张，后清将（DD 全知视角偏好的兑现线，预期被将吃）
    只依赖公开信息（庄+明+已出牌），不看防家手牌。
    """
    playable = state.get_playable_cards(pos)
    if not playable:
        return None
    lead_suit = state.current_trick.get_lead_suit()

    if lead_suit is not None:
        # ---- 跟牌 ----
        wp, wc = trick_current_winner(state.current_trick)
        same_suit = [c for c in playable if c.suit == lead_suit]
        if playable[0].suit == lead_suit:
            # 有同花色：打能赢的最小，否则垫最小
            win = cheapest_winning(playable, wc, lead_suit)
            return win if win is not None else min(playable, key=lambda c: c.rank_value)
        # 缺门
        trumps = [c for c in playable if c.suit == TRUMP]
        partner_wins = wp is not None and is_declarer_side(wp)
        if trumps and not partner_wins and (wc is None or True):
            # 明手/庄已无该花色且当前赢家是对手 → 将吃
            win = cheapest_winning(trumps, wc, lead_suit)
            if win is not None:
                return win
            return min(trumps, key=lambda c: c.rank_value)
        return min(playable, key=lambda c: c.rank_value)

    # ---- 领出新墩 ----
    opp_trumps = opp_trump_remaining(state)
    if mode == "greedy":
        # 抢占线：无视清将，直接兑现方块顶张（DD 全知视角偏好的兑现线，暴露给将吃）
        diamonds = [c for c in playable if c.suit == "♦"]
        if diamonds:
            return max(diamonds, key=lambda c: c.rank_value)
        self_high = [c for c in playable if c.rank in ("A", "K")]
        if self_high:
            return max(self_high, key=lambda c: c.rank_value)
        return min(playable, key=lambda c: c.rank_value)
    # 1) 若防家仍有将牌且本手有将 → 清将
    if opp_trumps > 0:
        trumps = [c for c in playable if c.suit == TRUMP]
        if trumps:
            return min(trumps, key=lambda c: c.rank_value)
    # 2) 将牌已清(或无须清)：现金到 A/K 赢墩（本手）
    self_high = [c for c in playable if c.rank in ("A", "K")]
    if self_high:
        return max(self_high, key=lambda c: c.rank_value)
    partner_hand = list(state.hands.get(PARTNERS.get(pos), []))
    # 3) 交叉将吃：同伴在该花色缺门且仍保有将牌 → 出最小该花色让同伴将吃
    for s in ("♥", "♦", "♣", "♠"):
        lows = [c for c in playable if c.suit == s]
        if lows and any(c.suit == TRUMP for c in partner_hand) \
                and not any(c.suit == s for c in partner_hand):
            return min(lows, key=lambda c: c.rank_value)
    # 4) 引向同伴顶张(单明手：只看自家两手)：同伴在某花色持有两手合成最大 → 出最小该花色
    for s in ("♣", "♥", "♦", "♠"):
        lows = [c for c in playable if c.suit == s]
        if not lows:
            continue
        ns_top = max([c for c in playable + partner_hand if c.suit == s], key=lambda c: c.rank_value)
        if ns_top in partner_hand:
            return min(lows, key=lambda c: c.rank_value)
    # 5) 兜底：出最小，保进手
    return min(playable, key=lambda c: c.rank_value)


def defense_strategy(pos: str, state: PlayState, ruff_log: list) -> Optional[Card]:
    """防家启发式：领出打最小；跟牌打能赢的最小或垫最小；缺门尽量将吃（记录将吃事件）。"""
    playable = state.get_playable_cards(pos)
    if not playable:
        return None
    lead_suit = state.current_trick.get_lead_suit()

    if lead_suit is not None:
        wp, wc = trick_current_winner(state.current_trick)
        if playable[0].suit == lead_suit:
            win = cheapest_winning(playable, wc, lead_suit)
            return win if win is not None else min(playable, key=lambda c: c.rank_value)
        # 缺门
        trumps = [c for c in playable if c.suit == TRUMP]
        partner_wins = wp is not None and not is_declarer_side(wp) and wp != pos
        if trumps and not partner_wins and lead_suit != TRUMP:
            win = cheapest_winning(trumps, wc, lead_suit)
            ruff = win if win is not None else min(trumps, key=lambda c: c.rank_value)
            if state.current_trick.cards and state.current_trick.cards[0][1].suit == "♦":
                ruff_log.append("防家将吃方块")
            return ruff
        return min(playable, key=lambda c: c.rank_value)

    # 领出：出最小
    return min(playable, key=lambda c: c.rank_value)


def sample_world() -> Dict[str, List[Card]]:
    """按公开信息均匀发东西两手（简化：26 张未知牌均匀两分）。"""
    ns_keys = {(c.suit, c.rank) for c in SOUTH_CARDS + NORTH_CARDS}
    pool = [c for c in ALL_CARDS if (c.suit, c.rank) not in ns_keys]
    RNG.shuffle(pool)
    west = pool[:13]
    east = pool[13:]
    return {
        "南": list(SOUTH_CARDS),
        "北": list(NORTH_CARDS),
        "西": west,
        "东": east,
    }


def replay(first_card: Card, mode: str) -> dict:
    """在随机世界（东西按公开信息发牌）上，从第2墩北领出开始完整模拟。
    返回 {"made": bool, "ruff_events": int, "decl_tricks": int, "trump_split": str}
    """
    world = sample_world()
    state = PlayState(
        contract=Contract(level=4, suit="♠", declarer=DECLARER),
        hands={p: list(cs) for p, cs in world.items()},
    )
    # 合成第2墩北领出：0-0，北出牌
    state.current_trick = Trick(trump=TRUMP)
    state.current_player = DUMMY
    state.phase = PlayPhase.PLAYING
    state.declarer_tricks = 0
    state.defender_tricks = 0

    ruff_log: list = []

    # 强制首牌
    ok = state.play_card(DUMMY, first_card, is_ai=True)
    if not ok:
        return {"made": False, "ruff_events": len(ruff_log), "decl_tricks": state.declarer_tricks,
                "trump_split": trump_split(world)}

    guard = 0
    while state.phase.value != "complete" and guard < 60:
        guard += 1
        pos = state.current_player
        if pos is None:
            break
        playable = state.get_playable_cards(pos)
        if not playable:
            break
        if is_declarer_side(pos):
            choice = declarer_strategy(pos, state, mode)
        else:
            choice = defense_strategy(pos, state, ruff_log)
        if choice is None or choice not in playable:
            break
        state.play_card(pos, choice, is_ai=True)

    made = state.declarer_tricks >= NEED_TRICKS
    return {"made": made, "ruff_events": len(ruff_log), "decl_tricks": state.declarer_tricks,
            "trump_split": trump_split(world)}


def trump_split(world: Dict[str, List[Card]]) -> str:
    """将牌(♠实质为缺门对方将牌5张)的分布桶："3-2"(较均)/"4-1"(恶劣)/"5-0"(极恶劣)。"""
    e = sum(1 for c in world["东"] if c.suit == TRUMP)
    w = sum(1 for c in world["西"] if c.suit == TRUMP)
    hi, lo = max(e, w), min(e, w)
    return f"{hi}-{lo}"


def run(candidate: Card, mode: str) -> dict:
    """跑 N_SAMPLES 世界，按将牌分布分桶统计可成率与将吃事件。"""
    by_bucket: Dict[str, Dict[str, int]] = {}
    ruffs = 0
    for _ in range(N_SAMPLES):
        res = replay(candidate, mode)
        b = res["trump_split"]
        cell = by_bucket.setdefault(b, {"made": 0, "n": 0, "ruff": 0})
        cell["n"] += 1
        cell["made"] += 1 if res["made"] else 0
        cell["ruff"] += res["ruff_events"]
        ruffs += res["ruff_events"]
    return {
        "make_rate": sum(c["made"] for c in by_bucket.values()) / N_SAMPLES,
        "ruff_total": ruffs,
        "by_bucket": by_bucket,
    }


def main():
    print("=" * 72)
    print("单明手精修原型：4♠ 南庄，第2墩北领出，东西按公开信息均匀发牌")
    print(f"样本数(每候选)：{N_SAMPLES}，可成线 ≥{NEED_TRICKS} 墩。按对方将牌(5张)分布分桶。")
    print("=" * 72)

    cases = [
        ("♠3(清将·patient)", Card("♠", "3"), "patient"),
        ("♦A(顶张·patient)", Card("♦", "A"), "patient"),
        ("♦A(顶张·greedy)", Card("♦", "A"), "greedy"),
    ]

    results = {}
    for label, card, mode in cases:
        r = run(card, mode)
        results[label] = r
        print(f"[{label}] 整体可成率 {r['make_rate']*100:6.2f}%  将吃事件 {r['ruff_total']}")

    buckets = ["3-2", "4-1", "5-0"]
    print("\n按对方将牌分布分桶的可成率（%）：")
    head = f"{'分布':<6}" + "".join(f"{c:>16}" for c in results)
    print(head)
    for b in buckets:
        row = f"{b:<6}"
        for lbl, r in results.items():
            cell = r["by_bucket"].get(b)
            n = cell["n"] if cell else 0
            mr = (cell["made"] / n * 100) if cell and n else 0.0
            row += f"  {n:>3}次 {mr:5.1f}%"
        print(row)


if __name__ == "__main__":
    main()