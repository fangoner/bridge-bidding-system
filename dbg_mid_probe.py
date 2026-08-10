import time, random
from bridge.play_types import Card, POSITION_ORDER
from bridge.mcts.state_utils import SUIT_DISPLAY_ORDER, RANK_DESC
from bridge.mcts.constraints import BidConstraint, _is_balanced
from bridge.mcts.sampler import _sample_mh_repair, _check_feasible, _sample_uniform, _reduce_constraint_for_played

ALL = [Card(suit=s, rank=r) for s in SUIT_DISPLAY_ORDER for r in RANK_DESC]
HCP = {"A":4,"K":3,"Q":2,"J":1}
CTRL = {"A":2,"K":1}
SUITS = list(SUIT_DISPLAY_ORDER)

def hcp(cards): return sum(HCP.get(c.rank,0) for c in cards)
def dist(cards):
    d={s:0 for s in SUITS}
    for c in cards: d[c.suit]+=1
    return d

def gen_hand(pool, hcp_min, hcp_max, balanced=None):
    for _ in range(20000):
        random.shuffle(pool)
        hand = pool[:13]
        h = hcp(hand)
        if h < hcp_min or h > hcp_max: continue
        if balanced is not None and _is_balanced(dist(hand)) != balanced: continue
        return hand
    return None

def run(label, ki, active, n=100):
    fe = _check_feasible(active, ki)
    ok=0; t0=time.time()
    for _ in range(n):
        w,o = _sample_mh_repair(ki, active, max_swaps=300)
        if o: ok+=1
    dt=time.time()-t0
    print(f"{label}: feasible={fe} success={ok}/{n} ({ok/n*100:.0f}%) avg={dt/n*1000:.1f}ms/样本")

random.seed(1)
pool = list(ALL)
# 北 16-19 均型（庄家，已知）
north = gen_hand(pool, 16, 19, balanced=True)
pool = [c for c in pool if c not in north]
# 南 <=4HCP（明手，已知）
south = gen_hand(pool, 0, 4)
pool = [c for c in pool if c not in south]

# 参数化：控制池中剩余♠数量，模拟最坏情况
for target_spades in (10, 8, 7, 6, 5):
    p2 = list(pool)
    # 移除多余♠使剩余♠=target
    spades_in = [c for c in p2 if c.suit=="♠"]
    others_in = [c for c in p2 if c.suit!="♠"]
    # 先保证♠: 需要 pool 大小 = rem_w+rem_e = 24
    # 从♠中取 target，从others取剩余
    need = 24
    if len(spades_in) < target_spades:
        continue
    chosen_sp = spades_in[:target_spades]
    need_from_o = need - len(chosen_sp)
    chosen_oth = others_in[:need_from_o]
    p2 = chosen_sp + chosen_oth
    random.shuffle(p2)

    ki = {
        "known_cards": set(north+south),
        "unknown_pool": p2,
        "remaining_counts": {"北":0,"南":0,"西":12,"东":12},
        "known_voids": {},
        "own_hand": [],
        "dummy_hand": [],
        "result": {"北": north, "南": south},
        "played": {"北":{"hcp":hcp(north),"controls":0,"suit":dist(north)},
                   "南":{"hcp":hcp(south),"controls":0,"suit":dist(south)},
                   "西":{"hcp":0,"controls":0,"suit":{"♠":0,"♥":0,"♦":0,"♣":0}},
                   "东":{"hcp":0,"controls":0,"suit":{"♠":0,"♥":0,"♦":0,"♣":0}}},
    }
    con_w = BidConstraint(position="西", min_hcp=6, max_hcp=10, suit_min={"♠":6}, inference_source="hard_coded_jf")
    ac = {}
    red_w = _reduce_constraint_for_played(con_w, {"hcp":0,"controls":0,"suit":{"♠":0,"♥":1,"♦":0,"♣":0}}, 12)
    if red_w: ac["西"] = red_w
    sp_in = sum(1 for c in p2 if c.suit=="♠")
    hcp_in = sum(HCP.get(c.rank,0) for c in p2)
    print(f"池剩余♠={sp_in} 剩余HCP={hcp_in}:")
    run(f"  西♠6/6-10HCP", ki, ac)

# 也测均匀采样本身成功率
ok=0
for _ in range(200):
    w = _sample_uniform(ki)
    from bridge.mcts.constraints import _check_constraint
    if _check_constraint(w.get("西",[]), red_w): ok+=1
print(f"  [对照] 纯均匀采样西约束满足率: {ok}/{200} ({ok/200*100:.0f}%)")