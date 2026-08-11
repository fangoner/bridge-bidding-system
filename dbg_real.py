import random
from bridge.play_types import Card
from bridge.mcts.state_utils import SUIT_DISPLAY_ORDER, RANK_DESC
from bridge.mcts.constraints import BidConstraint, _check_constraint
from bridge.mcts.sampler import _sample_mh_repair, _check_feasible, _sample_uniform, _reduce_constraint_for_played, _propose_swap
import bridge.mcts.constraints as C

ALL = [Card(suit=s, rank=r) for s in SUIT_DISPLAY_ORDER for r in RANK_DESC]
HCP = {"A":4,"K":3,"Q":2,"J":1}

def hcp(cards): return sum(HCP.get(c.rank,0) for c in cards)
def dist(cards):
    d={s:0 for s in SUIT_DISPLAY_ORDER}
    for c in cards: d[c.suit]+=1
    return d

def build_pool(spades_high=False, pool_spades=6):
    """构造池：西东共24张(西12东12)。池中♠=pool_spades。"""
    pool = list(ALL)
    random.shuffle(pool)
    spades = [c for c in pool if c.suit=="♠"]
    others = [c for c in pool if c.suit!="♠"]
    if spades_high:
        # 取最高HCP的 pool_spades 张♠
        spades_sorted = sorted(spades, key=lambda c: HCP.get(c.rank,0), reverse=True)
        chosen_sp = spades_sorted[:pool_spades]
    else:
        chosen_sp = spades[:pool_spades]
    need = 24
    chosen_oth = others[:need-len(chosen_sp)]
    p2 = chosen_sp + chosen_oth
    random.shuffle(p2)
    return p2

def make_ki(p2):
    return {
        "known_cards": set(),
        "unknown_pool": p2,
        "remaining_counts": {"北":0,"南":0,"西":12,"东":12},
        "known_voids": {},
        "own_hand": [],
        "dummy_hand": [],
        "result": {},
        "played": {"西":{"hcp":0,"controls":0,"suit":{"♠":0,"♥":0,"♦":0,"♣":0}},
                   "东":{"hcp":0,"controls":0,"suit":{"♠":0,"♥":0,"♦":0,"♣":0}}},
    }

def run(label, ki, active, n=200):
    fe = _check_feasible(active, ki)
    ok=0
    for _ in range(n):
        w,o = _sample_mh_repair(ki, active, max_swaps=300)
        if o: ok+=1
    # Level2 成功率
    l2=0
    sw = active.get("西")
    relaxed = C.relax_constraint(sw) if sw else None
    for _ in range(n):
        w = _sample_uniform(ki)
        if relaxed and _check_constraint(w.get("西",[]), relaxed): l2+=1
    pool=ki["unknown_pool"]
    sp_hcp=sum(hcp([c]) for c in pool if c.suit=="♠")
    nzero=sum(1 for c in pool if c.suit!="♠" and hcp([c])==0)
    print(f"{label}: feasible={fe} 池♠HCP={sp_hcp} 非♠0HCP={nzero} MH成功={ok}/{n} ({ok/n*100:.0f}%) Level2成功={l2}/{n} ({l2/n*100:.0f}%)")

random.seed(42)
base = BidConstraint(position="西", min_hcp=6, max_hcp=10, suit_min={"♠":6}, inference_source="hard_coded_jf")
red = _reduce_constraint_for_played(base, {"hcp":0,"controls":0,"suit":{"♠":0,"♥":1,"♦":0,"♣":0}}, 12)
ac = {"西": red}

# 场景1: 池♠=6, 随机♠HCP
for sc in ["随机♠","高HCP♠"]:
    hi = (sc=="高HCP♠")
    p2 = build_pool(spades_high=hi, pool_spades=6)
    ki = make_ki(p2)
    sp_hcp = sum(HCP.get(c.rank,0) for c in p2 if c.suit=="♠")
    print(f"池♠=6 池♠HCP={sp_hcp} ({sc}):")
    run(f"  MH", ki, ac)
    if hi:
        # 对比 beta 对 MH 收敛的影响
        from bridge.mcts.constraints import validate_hard
        for b in (1.0, 0.0):
            okc=0
            for _ in range(200):
                w,ok = _sample_mh_repair(ki, ac, max_swaps=300, beta=b)
                if ok: okc+=1
            print(f"  beta={b}: MH成功={okc}/200 ({okc/200*100:.0f}%)")

# 场景2: 池♠=7
p2 = build_pool(spades_high=True, pool_spades=7)
ki = make_ki(p2)
sp_hcp = sum(HCP.get(c.rank,0) for c in p2 if c.suit=="♠")
print(f"池♠=7 池♠HCP={sp_hcp} (高HCP♠):")
run(f"  MH", ki, ac)

# 场景3: 真不可行 - 池♠=6全高HCP且非♠也高HCP(0HCP不足6张)
def build_pool_infeasible(pool_spades=6):
    pool=list(ALL); random.shuffle(pool)
    sp=sorted([c for c in pool if c.suit=="♠"], key=lambda c:HCP.get(c.rank,0), reverse=True)[:pool_spades]
    oth=[c for c in pool if c.suit!="♠"]
    oth_hi=sorted(oth, key=lambda c:HCP.get(c.rank,0), reverse=True)
    chosen_oth=oth_hi[:18]  # 全取高HCP非♠，0HCP最少
    p2=list(sp)+chosen_oth; random.shuffle(p2)
    return p2
p2=build_pool_infeasible()
ki=make_ki(p2)
nzero=sum(1 for c in p2 if c.suit!="♠" and HCP.get(c.rank,0)==0)
print(f"池♠=6 (非♠0HCP={nzero}): feasible=",_check_feasible(ac,ki))