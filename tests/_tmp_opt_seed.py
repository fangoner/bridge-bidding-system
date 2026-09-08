import sys
import random

sys.path.insert(0, r"d:\Bridge Card\Bidding System")

from tests import _tmp_engine_run as T

from bridge.play_types import Card
from bridge.mcts.direct_dds import solve_all_boards_raw


def decl_opt(seed):
    west, east = T.deal_ew(seed)
    h = T.hands_of(west, east)
    cards = {"南": [], "北": [], "西": [], "东": []}
    k = {"spades": "♠", "hearts": "♥", "diamonds": "♦", "clubs": "♣"}
    for p in h:
        for suit, ranks in h[p].items():
            for r in ranks:
                cards[p].append(Card(k[suit], r))
    res = solve_all_boards_raw([(cards, "NT", "西", [])])
    score = max(sc for _, _, _, sc in res[0])
    return 13 - score  # 庄家方最优赢墩（西首攻最优）


for seed in range(30):
    try:
        d = decl_opt(seed)
        print(f"seed {seed}: 庄家方最优 {d} 墩")
    except Exception as e:
        print(f"seed {seed}: err {e}")