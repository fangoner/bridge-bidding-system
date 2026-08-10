import random
from collections import Counter
from bridge.play_types import Card
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

DECL = 3
CONTRACT = 8

def run_world(world):
    trick_cards = [("北", Card("♣", "5")), ("东", Card("♣", "7"))]
    solved = solve_all_boards_raw([(world, "NT", "北", trick_cards)])[0]
    if solved is None:
        return None
    sm = {}
    for suit, rank, equals, score in solved:
        s = {0: "♠", 1: "♥", 2: "♦", 3: "♣"}[suit]
        r = {14: "A", 13: "K", 12: "Q", 11: "J", 10: "T", 9: "9", 8: "8",
             7: "7", 6: "6", 5: "5", 4: "4", 3: "3", 2: "2"}[rank]
        sm[(s, r)] = score
    return sm

# 拆分统计
cells = {
    "西缺门": {"8": [], "T": []},
    "西不缺": {"8": [], "T": []},
}
for _ in range(250):
    w = sampler._sample_one(known_info, {p: c for p, c in constraints.items()})
    west_clubs = sum(1 for c in w["西"] if c.suit == "♣")
    east_clubs = [c for c in w["东"] if c.suit == "♣"]
    sm = run_world(w)
    if sm is None:
        continue
    grp = "西缺门" if west_clubs == 0 else "西不缺"
    t8 = DECL + sm.get(("♣","8"), 0)
    tT = DECL + sm.get(("♣","T"), 0)
    cells[grp]["8"].append(t8)
    cells[grp]["T"].append(tT)

rank = ["8", "9", "T", "J", "Q", "K", "A"]
label = lambda r: {8:"8",9:"9",10:"T",11:"J",12:"Q",13:"K",14:"A"}[r]

for grp in ("西缺门", "西不缺"):
    n = len(cells[grp]["8"])
    print(f"\n===== {grp}: {n} 个世界 =====")
    for card in ("8", "T"):
        d = cells[grp][card]
        avg = sum(d)/len(d)
        made = sum(1 for t in d if t >= CONTRACT)
        dist = Counter(d)
        print(f"  出♣{card}: 平均={avg:.2f}  做成率={made/n*100:.1f}%  P(宕)={100-made/n*100:.1f}%")
        print(f"     赢墩分布: " + ", ".join(f"{k}墩×{v}" for k, v in sorted(dist.items())))