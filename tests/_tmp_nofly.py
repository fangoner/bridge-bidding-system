import sys

sys.path.insert(0, r"d:\Bridge Card\Bidding System")

from bridge.play_types import Card
from bridge.mcts.direct_dds import solve_all_boards_raw

ALL_C = {"南": "AJ9", "北": "432", "东": "567", "西": "8TQK"}
ALL_H = {"南": "KQJ", "北": "A32", "东": "456", "西": "789T"}
ALL_D = {"南": "AQJ", "北": "K32", "东": "45", "西": "6789T"}
ALL_B = {"南": "5432", "北": "AKQJ", "东": "6789T", "西": ""}


def mk_hands(remain):
    out = {}
    for pos in ("南", "北", "东", "西"):
        out[pos] = []
        for suit, seq in (("♠", "C"), ("♥", "H"), ("♦", "D"), ("♣", "B")):
            for r in remain.get(seq, {}).get(pos, ""):
                out[pos].append(Card(suit, r))
    return out


def solve_decl(hands, first, remaining, trick_cards=None):
    """DDS 求解剩余 remaining 墩，返回庄家方（南/北阵营）赢墩数。

    score 语义：当前出牌方所在阵营的剩余赢墩（该候选为最优选择，取 max）。
    """
    res = solve_all_boards_raw([(hands, "NT", first, trick_cards or [])])
    if not res or res[0] is None or not res[0]:
        return None
    score = max(sc for _, _, _, sc in res[0])
    if first in ("南", "北"):
        return score
    return remaining - score


SRC = mk_hands({"C": ALL_C, "H": ALL_H, "D": ALL_D, "B": ALL_B})
remaining = 13
full = solve_decl(SRC, "西", remaining)
print(f"① 整副双明手最优：庄家方可赢 {full} 墩（6NT 需 12）")

# ② 弃飞：西♠8 - 北♠2 - 东♠5 - 南♠A（A 直接拿，不飞）
r2 = {
    "C": {"南": "J9", "北": "43", "东": "67", "西": "TQK"},
    "H": ALL_H, "D": ALL_D, "B": ALL_B,
}
h2 = mk_hands(r2)
try:
    d2 = solve_decl(h2, "南", 12)
    print(f"② 弃飞（首轮♠A 拿下、南领出）：庄家方 {d2} + 已赢1 = {1 + d2} 墩")
except Exception as e:
    print("② 失败:", e)

# ③ 飞：首攻西♠8 - 北♠2 - 东♠5 - 南♠J（J 第四家赢）→ 庄家方1墩，南领出
r3 = {
    "C": {"南": "A9", "北": "43", "东": "67", "西": "TQK"},
    "H": ALL_H, "D": ALL_D, "B": ALL_B,
}
h3 = mk_hands(r3)
try:
    d3 = solve_decl(h3, "南", 12)
    print(f"③ 飞♠（J 拿下首墩后南领出）：庄家方 {d3} + 已赢1 = {1 + d3} 墩")
except Exception as e:
    print("③ 失败:", e)