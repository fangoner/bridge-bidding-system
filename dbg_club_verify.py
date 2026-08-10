import random
from bridge.play_types import Card
from bridge.mcts.direct_dds import solve_all_boards_raw

random.seed(7)

ALL_SUITS = ["♠", "♥", "♦", "♣"]
ALL_RANKS = ["A", "K", "Q", "J", "T", "9", "8", "7", "6", "5", "4", "3", "2"]

def mk(pairs):
    return [Card(suit=s, rank=r) for s, r in pairs]

south_full = mk([("♠","A"),("♠","T"),("♠","7"),("♠","4"),("♠","2"),
                 ("♥","K"),("♥","8"),("♥","5"),
                 ("♦","9"),("♦","5"),
                 ("♣","T"),("♣","8"),("♣","6")])
north_full = mk([("♠","K"),("♠","8"),
                 ("♥","A"),("♥","9"),
                 ("♦","A"),("♦","T"),("♦","6"),("♦","4"),
                 ("♣","A"),("♣","J"),("♣","5"),("♣","4"),("♣","3")])

south_played = mk([("♥","5"),("♠","A"),("♣","6")])
north_played = mk([("♥","A"),("♠","8"),("♣","A"),("♣","5")])
east_played = mk([("♥","Q"),("♦","2"),("♣","2"),("♣","7")])
west_played = mk([("♥","4"),("♠","3"),("♣","K")])

south_rem = [c for c in south_full if c not in south_played]
north_rem = [c for c in north_full if c not in north_played]

known = set((c.suit, c.rank) for c in south_full + north_full + east_played + west_played)
pool = [(s, r) for s in ALL_SUITS for r in ALL_RANKS if (s, r) not in known]

east_n = 13 - len(east_played)
west_n = 13 - len(west_played)

def build_world():
    others = list(pool)
    random.shuffle(others)
    east_rem = mk(others[:east_n])
    west_rem = mk(others[east_n:east_n + west_n])
    return {
        "南": list(south_rem),
        "北": list(north_rem),
        "东": east_rem,
        "西": west_rem,
    }

def run_world(world):
    trick_cards = [("北", Card("♣", "5")), ("东", Card("♣", "7"))]
    first = "北"
    trump = "NT"
    solved_list = solve_all_boards_raw([(world, trump, first, trick_cards)])
    solved = solved_list[0]
    score_map = {}
    for suit, rank, equals, score in solved:
        s = {0: "♠", 1: "♥", 2: "♦", 3: "♣"}[suit]
        r = {14: "A", 13: "K", 12: "Q", 11: "J", 10: "T", 9: "9", 8: "8",
             7: "7", 6: "6", 5: "5", 4: "4", 3: "3", 2: "2"}[rank]
        score_map[(s, r)] = score
    return score_map

def show(pos, cards):
    by_suit = {s: [] for s in ALL_SUITS}
    for c in cards:
        by_suit[c.suit].append(c.rank)
    print(f"  {pos}: " + " ".join(
        f"{s}{''.join(sorted(by_suit[s], key=lambda r: ALL_RANKS.index(r)))}" for s in ALL_SUITS if by_suit[s]
    ))

# 找第一个 ♣8 > ♣T 的世界
for i in range(2000):
    world = build_world()
    sm = run_world(world)
    s8 = sm.get(("♣", "8"))
    sT = sm.get(("♣", "T"))
    if s8 is not None and sT is not None and s8 > sT:
        print(f"=== 找到第 {i} 个世界: ♣8={s8}, ♣T={sT} ===")
        for pos in ["北", "东", "南", "西"]:
            show(pos, world[pos])
        print("(北剩余梅花: ", [c.rank for c in world["北"] if c.suit == "♣"], ")")
        print("(南剩余梅花: ", [c.rank for c in world["南"] if c.suit == "♣"], ")")
        print("(东剩余梅花: ", [c.rank for c in world["东"] if c.suit == "♣"], ")")
        print("(西剩余梅花: ", [c.rank for c in world["西"] if c.suit == "♣"], ")")
        break