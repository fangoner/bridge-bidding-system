import random
from collections import Counter
from bridge.play_types import Card, POSITION_ORDER
from bridge.mcts.constraints import BidConstraint
from bridge.mcts.sampler import DealSampler, ALL_CARDS
from bridge.mcts.direct_dds import solve_all_boards_raw

random.seed(11)

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
east_played = mk([("♥","Q"),("♦","2"),("♣","2"),("♣","7")])
west_played = mk([("♥","4"),("♠","3"),("♣","K")])

south_rem = [c for c in south_full if c not in mk([("♥","5"),("♠","A"),("♣","6")])]
north_rem = [c for c in north_full if c not in mk([("♥","A"),("♠","8"),("♣","A"),("♣","5")])]

known = set((c.suit, c.rank) for c in south_full + north_full + east_played + west_played)
pool = [c for c in ALL_CARDS if (c.suit, c.rank) not in known]

known_info = {
    "unknown_pool": list(pool),
    "remaining_counts": {"北": 9, "东": 9, "南": 10, "西": 10},
    "known_voids": {},
    "own_hand": list(north_rem),
    "dummy_hand": list(south_rem),
    "result": {"北": list(north_rem), "南": list(south_rem)},
    "played": {
        "西": {"hcp": 3, "controls": 1, "suit": {"♠":1,"♥":1,"♦":0,"♣":1}},
        "东": {"hcp": 2, "controls": 0, "suit": {"♠":0,"♥":1,"♦":1,"♣":2}},
        "北": {"hcp": 0, "controls": 0, "suit": {"♠":0,"♥":0,"♦":0,"♣":0}},
        "南": {"hcp": 0, "controls": 0, "suit": {"♠":0,"♥":0,"♦":0,"♣":0}},
    },
}

constraints = {
    "西": BidConstraint(position="西", min_hcp=6, max_hcp=10, exact_suit={"♠": 6}, inference_source="hard_coded"),
    "东": BidConstraint(position="东", max_hcp=7, inference_source="hard_coded"),
}

sampler = DealSampler()
sampler.set_constraints(constraints)

def run_world(world):
    trick_cards = [("北", Card("♣", "5")), ("东", Card("♣", "7"))]
    solved = solve_all_boards_raw([(world, "NT", "北", trick_cards)])[0]
    if solved is None:
        return None, None
    sm = {}
    for suit, rank, equals, score in solved:
        s = {0: "♠", 1: "♥", 2: "♦", 3: "♣"}[suit]
        r = {14: "A", 13: "K", 12: "Q", 11: "J", 10: "T", 9: "9", 8: "8",
             7: "7", 6: "6", 5: "5", 4: "4", 3: "3", 2: "2"}[rank]
        sm[(s, r)] = score
    return sm.get(("♣", "8")), sm.get(("♣", "T"))

N = 250
s8_all, sT_all = [], []
w_void8, w_voidT = [], []   # 西缺门
w_club8, w_clubT = [], []   # 西有草花
cnt = Counter()

for _ in range(N):
    w = sampler._sample_one(known_info, {p: c for p, c in constraints.items()})
    west_clubs = sum(1 for c in w["西"] if c.suit == "♣")
    s8, sT = run_world(w)
    if s8 is None or sT is None:
        continue
    s8_all.append(s8); sT_all.append(sT)
    if s8 > sT:
        cnt["8>T"] += 1
    elif sT > s8:
        cnt["T>8"] += 1
    else:
        cnt["="] += 1
    if west_clubs == 0:
        w_void8.append(s8); w_voidT.append(sT)
    else:
        w_club8.append(s8); w_clubT.append(sT)

def avg(x):
    return sum(x)/len(x) if x else float("nan")

print(f"有效世界 {len(s8_all)}")
print(f"全样本:  ♣8 avg={avg(s8_all):.2f}  ♣T avg={avg(sT_all):.2f}  差(8-T)={avg(s8_all)-avg(sT_all):+.2f}")
print(f"  分布: {dict(cnt)}")
print(f"西缺门(n={len(w_void8)}): ♣8 avg={avg(w_void8):.2f}  ♣T avg={avg(w_voidT):.2f}  差={avg(w_void8)-avg(w_voidT):+.2f}")
print(f"西有草花(n={len(w_club8)}): ♣8 avg={avg(w_club8):.2f}  ♣T avg={avg(w_clubT):.2f}  差={avg(w_club8)-avg(w_clubT):+.2f}")

# 按西缺门拆分的 8>T 分布
void_better8 = 0
club_better8 = 0
void_betterT = 0
club_betterT = 0
for _ in range(N):
    w = sampler._sample_one(known_info, {p: c for p, c in constraints.items()})
    west_clubs = sum(1 for c in w["西"] if c.suit == "♣")
    s8, sT = run_world(w)
    if s8 is None or sT is None:
        continue
    if west_clubs == 0:
        if s8 > sT: void_better8 += 1
        elif sT > s8: void_betterT += 1
    else:
        if s8 > sT: club_better8 += 1
        elif sT > s8: club_betterT += 1
print(f"西缺门: 8>T={void_better8}, T>8={void_betterT}")
print(f"西有草花: 8>T={club_better8}, T>8={club_betterT}")