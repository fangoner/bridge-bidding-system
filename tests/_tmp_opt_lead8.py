import sys

sys.path.insert(0, r"d:\Bridge Card\Bidding System")

from bridge.play_types import Card
from bridge.mcts.direct_dds import solve_all_boards_raw
import tests._tmp_engine_run as T


def decl_opt_lead8(seed):
    west, east = T.deal_ew(seed)
    h = T.hands_of(west, east)
    k = {"spades": "♠", "hearts": "♥", "diamonds": "♦", "clubs": "♣"}
    cards = {"南": [], "北": [], "西": [], "东": []}
    for p in h:
        for dsuit, ranks in h[p].items():
            for r in ranks:
                cards[p].append(Card(k[dsuit], r))
    # 固定首墩：西♣8 - 北♣2 - 东跟♣ - 南♣A（A 最大赢），此后南领出
    # 先移除首墩已出的牌
    west_c8 = next(c for c in cards["西"] if c.suit == "♣" and c.rank == "8")
    north_c2 = next(c for c in cards["北"] if c.suit == "♣" and c.rank == "2")
    cards["西"].remove(west_c8)
    cards["北"].remove(north_c2)
    east_clubs = [c for c in cards["东"] if c.suit == "♣"]
    if east_clubs:
        e_min = min(east_clubs, key=lambda c: "AKQJT98765432".index(c.rank))
        cards["东"].remove(e_min)
    south_ca = next(c for c in cards["南"] if c.suit == "♣" and c.rank == "A")
    cards["南"].remove(south_ca)
    res = solve_all_boards_raw([(cards, "NT", "南", [])])
    score = max(sc for _, _, _, sc in res[0])
    return 1 + score  # 首墩♣A已赢


import sys as _s
for seed in [int(a) for a in _s.argv[1:]] or [42, 7, 0]:
    d = decl_opt_lead8(seed)
    print(f"seed {seed}: 固定首攻♣8后庄家方最优 {d} 墩（需12）")