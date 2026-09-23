"""DD 版不利分布桶判别子原型：4♠ 清将 vs 顶张，用真 DDSearch（双明手全知）分桶。

背景（见 docs/坐庄评估改造_DD结合αμ与飞牌介入去留_20260922.md，§十/§十一）：
- 之前单明手路径已由用户定调搁置。本项目=只改现有 DD 引擎（双明手全知）+ 既有世界采样，
  把"全样本平均"改成"不利分布桶内条件集"的聚合（E[可成率 | 关键花色恶劣分布]）。
- 本脚本用真 DDSearch.search_perfect（DirectDDS 直调 dds.dll）逐候选逐世界算做成率，
  按对方将牌(♠5张)分布桶（3-2 / 4-1 / 5-0）分桶，比较 ♦A(顶张) 与 ♠3(清将)。
  科学悬念：DD 桶内仍全知，可能连不利分布也"吸收"（4-1 桶也 ~100%）→ 不利桶套在 DD 上不成立；
  若 4-1 桶能把 ♦A 与 ♠3 拉开 → 无需单明手，直接改既有引擎的分桶聚合即可收敛。

共享世界：先采样一批 world 列表复用，两候选在同一批世界上评估（消除采样噪声差异）。

用法：python tests/prototype_dd_adverse_bucket.py
"""

import os
import random
import sys
from typing import Dict, List

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from bridge.play_types import Card, Contract, Trick, PlayState, PlayPhase, POSITION_ORDER, PARTNERS
from bridge.mcts.direct_dds import solve_all_boards_raw
from bridge.mcts.dd_search import _dds_result_to_score_map

TRUMP = "♠"
DECLARER = "南"
DUMMY = "北"
NEED_TRICKS = 10  # 4♠
N_SAMPLES = 250
RNG = random.Random(20260922)

# 复用单明手原型的数据/发牌/分桶函数，保证同一牌例同一套世界
from prototype_single_dummy_4s import SOUTH_CARDS, NORTH_CARDS, ALL_CARDS, sample_world

_DD_POS = {"北": 0, "东": 1, "南": 2, "西": 3}


def dd_value_of_lead(first_card: Card, world: Dict[str, List[Card]]) -> int:
    """合成第2墩北领出，强制北出 first_card 后直接 DDS 求该首牌的双明手值。

    返回庄家方(南/北)总赢墩数。trick_cards=[(北, first_card)]、first_p=北，
    求解全部13墩后读东(防家)各候选的得分，防御方(东)取 max(score_map)=最劣，
    故值 = 13 - max_{东候选}(score_map)。
    """
    deep_hands = {p: [Card(suit=c.suit, rank=c.rank) for c in cs] for p, cs in world.items()}
    state = PlayState(
        contract=Contract(level=4, suit="♠", declarer=DECLARER),
        hands=deep_hands,
    )
    state.current_trick = Trick(trump=TRUMP)
    state.current_player = DUMMY
    state.phase = PlayPhase.PLAYING
    state.declarer_tricks = 0
    state.defender_tricks = 0

    ok = state.play_card(DUMMY, first_card, is_ai=True)
    if not ok:
        return -1

    hands = {p: list(state.hands.get(p, [])) for p in POSITION_ORDER}
    trick_cards = list(state.current_trick.cards)
    trick_leader = state.current_trick.leader
    first_p = trick_leader if trick_cards else None
    solved = solve_all_boards_raw([(hands, TRUMP, first_p, trick_cards)])
    if not solved or solved[0] is None:
        return -1
    score_map = _dds_result_to_score_map(solved[0])
    east_options = state.get_playable_cards("东")
    if not east_options:
        return -1
    max_target = max(score_map.get((c.suit, c.rank), 0) for c in east_options)
    remaining = 13 - (state.declarer_tricks + state.defender_tricks)  # =13
    return remaining - max_target


def suit_split(world: Dict[str, List[Card]], suit: str) -> str:
    """某花色(SELF: 东/西张数)分布桶："3-2"/"4-1"/"5-0" 等 hi-lo 形式。"""
    e = sum(1 for c in world["东"] if c.suit == suit)
    w = sum(1 for c in world["西"] if c.suit == suit)
    hi, lo = max(e, w), min(e, w)
    return f"{hi}-{lo}"


def main():
    print("=" * 76)
    print("DD 版不利分布桶判别子原型：4♠ 南庄，第2墩北领出，真 DDSearch 双明手全知分桶")
    print(f"样本数(共享世界)：{N_SAMPLES}，可成线 ≥{NEED_TRICKS} 墩。按各花色(东/西)分布分桶。")
    print("=" * 76)

    worlds = [sample_world() for _ in range(N_SAMPLES)]

    candidates = [
        ("♠3(清将)", Card("♠", "3")),
        ("♦A(顶张)", Card("♦", "A")),
    ]

    per_world = {lbl: [dd_value_of_lead(card, w) for w in worlds] for lbl, card in candidates}

    labels = list(candidates)[:]
    lbl_names = [lbl for lbl, _ in candidates]
    for lbl in lbl_names:
        made = sum(1 for v in per_world[lbl] if v >= NEED_TRICKS)
        print(f"[{lbl}] 整体做成率 {made/N_SAMPLES*100:6.2f}%")

    suits = ["♠", "♥", "♦", "♣"]
    suit_names = {"♠": "对方将牌", "♥": "红心", "♦": "方块", "♣": "梅花"}
    for suit in suits:
        print("\n" + "=" * 76)
        print(f"按 {suit}({suit_names[suit]}) 东/西分布分桶的做成率（%）与桶内平均赢墩:")
        head = f"{'分布':<6}" + "".join(f"{lbl:>26}" for lbl in lbl_names)
        print(head)
        buckets = sorted({suit_split(w, suit) for w in worlds},
                         key=lambda s: tuple(int(x) for x in s.split("-")))
        for b in buckets:
            row = f"{b:<6}"
            idxs = [i for i, w in enumerate(worlds) if suit_split(w, suit) == b]
            for lbl in lbl_names:
                vals = [per_world[lbl][i] for i in idxs]
                n = len(vals)
                mr = sum(1 for v in vals if v >= NEED_TRICKS) / n * 100 if n else 0.0
                avg = sum(vals) / n if n else 0.0
                row += f"  {n:>3}次 {mr:5.1f}% 均{avg:4.2f}墩"
            print(row)

    print("\n" + "=" * 76)
    print("逐世界比较（同一世界）——『无损失』的可证明判据")
    print("diff = 清将♠3赢墩 − 顶张♦A赢墩。所有 diff≥0 ⇒ 清将在每个分布下都不亏 ⇒ 无损可触发。")
    print("=" * 76)
    diffs = [per_world["♠3(清将)"][i] - per_world["♦A(顶张)"][i] for i in range(N_SAMPLES)]
    ge0 = sum(1 for d in diffs if d >= 0)
    lt0 = sum(1 for d in diffs if d < 0)
    mnd, mxd = min(diffs), max(diffs)
    avgd = sum(diffs) / len(diffs)
    print(f"清将赢墩 ≥ 顶张 的世界：{ge0}（无损失）")
    print(f"清将赢墩 < 顶张 的世界：{lt0}（此分布清将错失将吃/交叉将吃机会 → 不触发）")
    print(f"墩差 最小 {mnd:+d} / 最大 {mxd:+d} / 平均 {avgd:+.2f}")
    if lt0 == 0:
        print("=> 本例『无损失先清将』判定通过（严格成立）。")
    else:
        bad = [i for i, d in enumerate(diffs) if d < 0][:5]
        print(f"  反例世界索引(前5)：{bad}，这些是清将亏墩的分布。")


if __name__ == "__main__":
    main()