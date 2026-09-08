import random
import sys

sys.path.insert(0, r"d:\Bridge Card\Bidding System")

from bridge.play_types import Card
from bridge.mcts.direct_dds import solve_all_boards_raw

# 用户牌例：牌序南西北东；南坐庄 6NT；西首攻 ♣8；东西未知需采样
SOUTH = {"♠": "432", "♥": "A32", "♦": "K32", "♣": "AKQJ"}
NORTH = {"♠": "AJ9", "♥": "KQJ", "♦": "AQJ", "♣": "5432"}

N_SAMPLES = 500
NEEDED = 12

RANKS = "AKQJT98765432"
SUITS = "♠♥♦♣"


def build_pool():
    known = set()
    for suit, ranks in SOUTH.items():
        for r in ranks:
            known.add(suit + r)
    for suit, ranks in NORTH.items():
        for r in ranks:
            known.add(suit + r)
    return [s + r for s in SUITS for r in RANKS if s + r not in known]


def rv(c):
    return RANKS.index(str(c)[1:])


def solve_decl_remaining(hands, first, remaining):
    res = solve_all_boards_raw([(hands, "NT", first, [])])
    if not res or res[0] is None or not res[0]:
        return None
    score = max(sc for _, _, _, sc in res[0])
    if first in ("南", "北"):
        return score
    return remaining - score


def swap_card(hands, from_pos, card_suit, card_rank, to_suit_r):
    """在 hands 里把 from_pos 的 (suit,rank) 牌与敌方一张牌交换。"""
    src = None
    for c in hands[from_pos]:
        if c.suit == card_suit and c.rank == card_rank:
            src = c
            break
    if src is None:
        return False
    idx = hands[from_pos].index(src)
    repl = None
    for pos in ("东", "西"):
        for c in hands[pos]:
            if c.suit == to_suit_r[0] and c.rank == to_suit_r[1]:
                repl = (pos, c)
                break
        if repl:
            break
    if repl is None:
        return False
    p2, rc = repl
    hands[p2].remove(rc)
    hands[p2].append(src)
    hands[from_pos][idx] = rc
    return True


def mk_hands(n_spades, west_other, east, east_lead):
    hands = {"南": [], "北": [], "东": [], "西": []}
    for suit, ranks in SOUTH.items():
        for r in ranks:
            if suit == "♣" and r == "J":
                continue  # 首墩南♣J 已出
            hands["南"].append(Card(suit, r))
    north = {"♠": n_spades, "♥": NORTH["♥"], "♦": NORTH["♦"], "♣": NORTH["♣"]}
    for suit, ranks in north.items():
        for r in ranks:
            if suit == "♣" and r == "2":
                continue  # 首墩北♣2 已出
            hands["北"].append(Card(suit, r))
    for c in west_other:  # 西♣8 已出，不在此列
        hands["西"].append(Card(c[0], c[1:]))
    for c in east:
        if str(c) == str(east_lead):
            continue  # 首墩东跟牌已出
        hands["东"].append(Card(c[0], c[1:]))
    return hands


if __name__ == "__main__":
    random.seed(int(sys.argv[1]) if len(sys.argv) > 1 else 42)
    won_orig = 0
    won_nofly = 0
    ok = 0
    n_c8 = 0
    n_east_club = 0
    for _ in range(N_SAMPLES):
        pool = build_pool()
        random.shuffle(pool)
        west = pool[:13]
        east = pool[13:]
        if "♣8" in west:
            n_c8 += 1
        if any(c[0] == "♣" for c in east):
            n_east_club += 1
        if "♣8" not in west:
            continue
        east_clubs = [c for c in east if c[0] == "♣"]
        if not east_clubs:
            continue
        ok += 1
        west_other = [c for c in west if c != "♣8"]
        east_lead = min(east_clubs, key=rv)

        h_orig = mk_hands("AJ9", west_other, east, east_lead)
        h_flip = mk_hands("AJ9", west_other, east, east_lead)  # 先同牌，再交换去飞张
        ok1 = swap_card(h_flip, "北", "♠", "J", ("♠", "7"))
        ok2 = swap_card(h_flip, "北", "♠", "9", ("♠", "8"))
        if not (ok1 and ok2):
            ok -= 1
            continue

        e_orig = solve_decl_remaining(h_orig, "南", 12)
        e_flip = solve_decl_remaining(h_flip, "南", 12)
        if e_orig is None or e_flip is None:
            ok -= 1
            continue
        if 1 + e_orig >= NEEDED:
            won_orig += 1
        if 1 + e_flip >= NEEDED:
            won_nofly += 1

    print(f"采样统计: ♣8在西={n_c8} 东有♣={n_east_club} 有效={ok}/{N_SAMPLES}")
    print(f"原牌（♠AJ9 可飞）: 做成 {won_orig}（{100.0*won_orig/ok:.1f}%）")
    print(f"禁飞牌（♠A87 无飞张）: 做成 {won_nofly}（{100.0*won_nofly/ok:.1f}%）")