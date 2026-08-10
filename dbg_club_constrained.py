import random
from bridge.play_types import Card
from bridge.mcts.direct_dds import solve_all_boards_raw

random.seed(7)

ALL_SUITS = ["♠", "♥", "♦", "♣"]
ALL_RANKS = ["A", "K", "Q", "J", "T", "9", "8", "7", "6", "5", "4", "3", "2"]
HCP = {"A": 4, "K": 3, "Q": 2, "J": 1, "T": 0, "9": 0, "8": 0, "7": 0,
       "6": 0, "5": 0, "4": 0, "3": 0, "2": 0}

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

def hcp(cards):
    return sum(HCP.get(c.rank, 0) for c in cards)

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
    if solved is None:
        return None
    score_map = {}
    for suit, rank, equals, score in solved:
        s = {0: "♠", 1: "♥", 2: "♦", 3: "♣"}[suit]
        r = {14: "A", 13: "K", 12: "Q", 11: "J", 10: "T", 9: "9", 8: "8",
             7: "7", 6: "6", 5: "5", 4: "4", 3: "3", 2: "2"}[rank]
        score_map[(s, r)] = score
    return score_map

def west_plays_well(world, retry):
    west = world["西"]
    east = world["东"]
    # 约束（已折算剩余部分）：
    # 西整手 HCP 6-10，已出 ♣K=3 → 剩余 HCP ∈ [3,7]
    # 西整手 ♠=6，已出 ♠3 → 剩余 ♠ 恰 = 5
    # 东整手 HCP ≤7，已出 ♥Q=2 → 剩余 HCP ≤ 5
    w_hcp = hcp(west)
    w_sp = sum(1 for c in west if c.suit == "♠")
    e_hcp = hcp(east)
    if not (3 <= w_hcp <= 7):
        return False
    if w_sp != 5:
        return False
    if not (e_hcp <= 5):
        return False
    return True

N = 60
c8_scores = []
cT_scores = []
c8_win = 0
cT_win = 0
tie = 0
worlds = 0
while len(c8_scores) < N:
    world = build_world()
    if not west_plays_well(world, 0):
        continue
    sm = run_world(world)
    if sm is None:
        continue
    s8 = sm.get(("♣", "8"))
    sT = sm.get(("♣", "T"))
    worlds += 1
    if s8 is None or sT is None:
        continue
    c8_scores.append(s8)
    cT_scores.append(sT)
    if s8 > sT:
        c8_win += 1
    elif sT > s8:
        cT_win += 1
    else:
        tie += 1

print(f"有效约束样本 {len(c8_scores)}/{worlds} 构造")
print(f"♣8 平均 {sum(c8_scores)/len(c8_scores):.2f}, 得分 {c8_scores}")
print(f"♣T 平均 {sum(cT_scores)/len(cT_scores):.2f}, 得分 {cT_scores}")
print(f"♣8 优于 ♣T: {c8_win}, ♣T 优于 ♣8: {cT_win}, 平 {tie}")