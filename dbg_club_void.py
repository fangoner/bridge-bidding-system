import random
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

def fmt(hand):
    by = {"♠": [], "♥": [], "♦": [], "♣": []}
    for c in hand:
        by[c.suit].append(c.rank)
    order = ["A","K","Q","J","T","9","8","7","6","5","4","3","2"]
    return " ".join(s + "".join(sorted(r, key=order.index, reverse=True)) for s, r in by.items())

# 找出西缺门的世界的 8/T 得分
w_void = []
for i in range(250):
    w = sampler._sample_one(known_info, {p: c for p, c in constraints.items()})
    if sum(1 for c in w["西"] if c.suit == "♣") != 0:
        continue
    sm = run_world(w)
    if sm is None:
        continue
    s8 = sm.get(("♣","8")); sT = sm.get(("♣","T"))
    w_void.append((w, s8, sT))

print(f"西缺门世界数: {len(w_void)}")
avg = lambda x: sum(x)/len(x) if x else float("nan")
print(f"剩余墩:  ♣8平均={avg([x[1] for x in w_void]):.2f}  ♣T平均={avg([x[2] for x in w_void]):.2f}")
print(f"总赢墩:  ♣8平均={avg([DECL+x[1] for x in w_void]):.2f}  ♣T平均={avg([DECL+x[2] for x in w_void]):.2f}")
print("="*70)

# 打印第一个西缺门世界的完整手牌
w, s8, sT = w_void[0]
print("=== 西缺门世界示例 ===")
for pos in POSITION_ORDER:
    print(f"{pos}: {fmt(w[pos])}")
print(f"北已出: ♥A ♠8 ♣A ♣5")
print(f"南已出: ♥5 ♠A ♣6")
print(f"东已出: ♥Q ♦2 ♣2 ♣7")
print(f"西已出: ♥4 ♠3 ♣K")
print(f"当前墩: 北♣5 - 东♣7 - 南?")
print(f"剩余赢墩: 出♣8={s8} -> 总{DECL+s8}  出♣T={sT} -> 总{DECL+sT}")