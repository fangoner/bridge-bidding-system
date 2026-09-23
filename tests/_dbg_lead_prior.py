import os, random, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from bridge.play_types import Card, Contract, PlayState, PlayPhase, Trick
from bridge.mcts.dd_search import DDSearch

north = [Card("♠","T"),Card("♠","Q"),Card("♠","5"),Card("♠","4"),
         Card("♥","Q"),Card("♥","4"),Card("♥","3"),
         Card("♦","A"),Card("♦","K"),Card("♦","4"),
         Card("♣","4"),Card("♣","3"),Card("♣","2")]
south = [Card("♠","3"),Card("♠","2"),Card("♥","A"),Card("♥","K"),Card("♥","2"),
         Card("♦","Q"),Card("♦","3"),Card("♦","2"),
         Card("♣","K"),Card("♣","Q"),Card("♣","J"),Card("♣","T"),Card("♣","9")]

RANKS=list("AKQJT98765432"); SUITS=list("♠♥♦♣")
def remaining():
    used=set()
    for c in south+north: used.add((c.suit,c.rank))
    used.add(("♠","8"))
    return [Card(s,r) for s in SUITS for r in RANKS if (s,r) not in used]

def deal(rng):
    rem=remaining(); rng.shuffle(rem)
    return {"南":south,"北":north,"西":rem[:12],"东":rem[12:]}

NEED=9
candidates=[Card("♠","T"),Card("♠","Q"),Card("♠","5"),Card("♠","4")]

N=4000
rng=random.Random(20260926)
worlds=[deal(rng) for _ in range(N)]

state=PlayState(contract=Contract(level=3,suit="NT",declarer="南"),
                hands={"南":south,"北":north,"西":[],"东":[]}, vulnerability="NV")
state.dummy="北"; state.current_player="北"; state.lead_player="西"
state.phase=PlayPhase.PLAYING
state.current_trick=Trick(trump="NT"); state.current_trick.cards=[("西",Card("♠","8"))]
state.current_trick.leader="西"
state.declarer_tricks=0; state.defender_tricks=0
state.finesse_flow={}; state.finesse_flow_ends={}

dd=DDSearch(num_samples=N,min_samples=15,time_limit=120.0,endgame_card_threshold=4,
            max_enumerations=5000)
res=dd.search(state,perspective="北",actual_turn="北",preset_worlds=worlds)
mcts=res["full_output"]["mcts_stats"]
cands=mcts["candidates"]
pick={c["card"]: c["scores"] for c in cands}
for c in candidates: assert len(pick[str(c)])==N, str(c)

# 首攻长四先验：攻♠8 => 西黑桃比8大的(A/K/J/9)恰3张 且 西黑桃>=4张
LEAD="8"
bigger_ranks={r for r in RANKS if RANKS.index(r) < RANKS.index(LEAD)}  # A K J 9
def long_four(west):
    sp=[c for c in west if c.suit=="♠"]
    n=len(sp)+1  # +已首攻的8
    h=sum(1 for c in sp if c.rank in bigger_ranks)
    return n>=4 and h==3

flag=[long_four(w["西"]) for w in worlds]
n_ok=sum(flag)
print(f"首攻长四一致世界: {n_ok}/{N} ({n_ok/N*100:.1f}%)  其余 {N-n_ok} 为短套/非长四")
ok_idx=[i for i,f in enumerate(flag) if f]
rest_idx=[i for i,f in enumerate(flag) if not f]

def makrate(idxs):
    return {str(c): sum(pick[str(c)][i]>=NEED for i in idxs)/len(idxs)*100 if idxs else 0.0
            for c in candidates}

print()
print("== 候选做成率：全样本 vs 首攻长四一致子集 vs 其余 ==")
print(f"{'候选':<6} {'全样本':>8} {'长四一致':>9} {'其余(非长四)':>12}")
for c in candidates:
    print(f"{str(c):<6} {makrate(range(N))[str(c)]:>7.1f}% "
          f"{makrate(ok_idx)[str(c)]:>8.1f}% {makrate(rest_idx)[str(c)]:>11.1f}%")

print()
print("== 长四一致子集内的黑桃分布（含首攻8）==")
from collections import Counter
dist=Counter()
for i in ok_idx:
    w=worlds[i]
    es=sum(1 for c in w["东"] if c.suit=="♠"); ws=sum(1 for c in w["西"] if c.suit=="♠")
    dist[(es,ws+1)]+=1
for k in sorted(dist,key=lambda x:x[0]):
    print(f"  东{k[0]}-西{k[1]}: {dist[k]/n_ok*100:5.1f}%")
print()
print(f"全样本整体: T={makrate(range(N))['♠T']:.1f}%  Q={makrate(range(N))['♠Q']:.1f}%  5/4={makrate(range(N))['♠5']:.1f}%")
print(f"长四一致子集: T={makrate(ok_idx)['♠T']:.1f}%  Q={makrate(ok_idx)['♠Q']:.1f}%  5/4={makrate(ok_idx)['♠5']:.1f}%")