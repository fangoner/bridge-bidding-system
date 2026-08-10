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

DECL_ALREADY = 3  # 已取的庄家墩数

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

CONTRACT_NEED = 8
IMP_TABLE = [0,20,50,80,130,200,300,500,750,1000,1300,1600,2000,2400,3000,3600,4200,4900,5900,7000,8000,
             9000,10000,11000,12000]
def raw_to_imp(raw):
    sign = 1 if raw >= 0 else -1
    a = abs(raw)
    k = 0
    for kk in range(len(IMP_TABLE)-1, -1, -1):
        if a >= IMP_TABLE[kk]:
            k = kk
            break
    return sign * k

def imp_score(total_tricks, vul):
    # 庄家方(NS) 2NT 的总分：t>=8 做成，t<8 宕
    if total_tricks >= CONTRACT_NEED:
        raw = 100 + 30*(total_tricks - CONTRACT_NEED)
    else:
        down = CONTRACT_NEED - total_tricks
        raw = -(50 + 50*vul)*down
    return raw, raw_to_imp(raw)

N = 250
res = {"8": {"imp_nv":[], "imp_v":[], "raw_nv":[], "make":0},
       "T": {"imp_nv":[], "imp_v":[], "raw_nv":[], "make":0}}
made8 = madeT = 0
sample_west_void = 0

for _ in range(N):
    w = sampler._sample_one(known_info, {p: c for p, c in constraints.items()})
    if sum(1 for c in w["西"] if c.suit=="♣") == 0:
        sample_west_void += 1
    s8, sT = run_world(w)
    if s8 is None or sT is None:
        continue
    t8 = DECL_ALREADY + s8
    tT = DECL_ALREADY + sT
    for card, t in (("8", t8), ("T", tT)):
        rnv, imp_nv = imp_score(t, vul=0)
        rv, imp_v = imp_score(t, vul=1)
        res[card]["imp_nv"].append(imp_nv)
        res[card]["imp_v"].append(imp_v)
        res[card]["raw_nv"].append(rnv)
        if t >= CONTRACT_NEED:
            res[card]["make"] += 1

avg = lambda x: sum(x)/len(x) if x else float("nan")
print(f"有效世界 {len(res['8']['imp_nv'])}  西缺门样本 {sample_west_void} ({sample_west_void/N*100:.1f}%)")
print("="*60)
for card in ("8", "T"):
    d = res[card]
    n = len(d["imp_nv"])
    print(f"[♣{card}] 平均赢墩={avg([x+DECL_ALREADY for x in ([0] if False else [])]):.2f}  "
          f"E[RAW非局]={avg(d['raw_nv']):+.0f}  E[IMP非局]={avg(d['imp_nv']):.2f}  "
          f"E[IMP有局]={avg(d['imp_v']):.2f}  P(做成)={d['make']/n*100:.1f}%")

# 直接输出每墩平均
t8s, tTs = [], []
# 重算一次存 total
for _ in range(N):
    w = sampler._sample_one(known_info, {p: c for p, c in constraints.items()})
    s8, sT = run_world(w)
    if s8 is None or sT is None:
        continue
    t8s.append(DECL_ALREADY + s8); tTs.append(DECL_ALREADY + sT)
print(f"\n平均总赢墩:  ♣8={avg(t8s):.2f}  ♣T={avg(tTs):.2f}  (差 8-T={avg(t8s)-avg(tTs):+.2f})")