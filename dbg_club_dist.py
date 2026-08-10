import random
from collections import Counter
from bridge.play_types import Card, POSITION_ORDER
from bridge.mcts.constraints import BidConstraint
from bridge.mcts.sampler import DealSampler, ALL_CARDS

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
assert len(south_rem)==10 and len(north_rem)==9, (len(south_rem), len(north_rem))

known = set((c.suit, c.rank) for c in south_full + north_full + east_played + west_played)
pool = [c for c in ALL_CARDS if (c.suit, c.rank) not in known]
assert len(pool)==19, len(pool)

known_info = {
    "known_cards": set(south_rem + north_rem),
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

N = 250
west_club_len = Counter()
q_loc = Counter()   # 西/东/北/南 持有 ♣Q
nine_loc = Counter()  # 谁持有 ♣9
west_void = 0
east_void = 0
both_q9_west = 0
fallback = 0

worlds = []
for _ in range(N):
    w = sampler._sample_one(known_info, {p: c for p, c in constraints.items()})
    worlds.append(w)
    west = w.get("西", [])
    east = w.get("东", [])
    wcl = sum(1 for c in west if c.suit == "♣")
    ecl = sum(1 for c in east if c.suit == "♣")
    west_club_len[wcl] += 1
    if wcl == 0:
        west_void += 1
    if ecl == 0:
        east_void += 1
    for pos in POSITION_ORDER:
        for c in w[pos]:
            if c.rank == "Q" and c.suit == "♣":
                q_loc[pos] += 1
            if c.rank == "9" and c.suit == "♣":
                nine_loc[pos] += 1
    if wcl == 0 and "♣" not in [c.suit for c in east]:
        pass
    if ("♣","Q") in [(c.suit,c.rank) for c in west] and ("♣","9") in [(c.suit,c.rank) for c in west]:
        both_q9_west += 1

print(f"采样 {N} 个世界")
print(f"西家草花张数分布: {dict(sorted(west_club_len.items()))}")
print(f"西家无草花(缺门)次数: {west_void} ({west_void/N*100:.1f}%)")
print(f"东家无草花次数: {east_void} ({east_void/N*100:.1f}%)")
print(f"♣Q 位置分布: {dict(q_loc)}")
print(f"♣9 位置分布: {dict(nine_loc)}")
print(f"♣Q9 同在西家次数: {both_q9_west}")

def w_wc(w):
    return sum(1 for c in w["西"] if c.suit=="♣")
combo = Counter()
for w in worlds:
    q = next(((pos,c) for pos in POSITION_ORDER for c in w[pos] if c.suit=="♣" and c.rank=="Q"), None)
    n = next(((pos,c) for pos in POSITION_ORDER for c in w[pos] if c.suit=="♣" and c.rank=="9"), None)
    combo[(q[0] if q else "-", n[0] if n else "-")] += 1
print("Q9 组合分布(西,东):")
for k, v in sorted(combo.items()):
    print(f"  Q在{k[0]} 9在{k[1]}: {v} ({v/N*100:.1f}%)")