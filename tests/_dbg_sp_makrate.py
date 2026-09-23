import os, random, sys
from collections import Counter
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
print("北的候选跟牌:", [str(c) for c in candidates], "，3NT 需", NEED, "墩")

N=2000
rng=random.Random(20260923)
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

bucket=Counter()
makrates={str(c):{} for c in candidates}   # (card, bucket) -> 做成率
bucket_pct={}
LEAD_OWNERS = {"西": 1}  # 西首攻♠8 -> 加算回西家（北的♠T属明手不计入防守方）
for wi,world in enumerate(worlds):
    es=sum(1 for c in world["东"] if c.suit=="♠"); ws=sum(1 for c in world["西"] if c.suit=="♠")
    b=(es, ws + LEAD_OWNERS.get("西", 0)); bucket[b]+=1
for b,nb in bucket.items():
    bucket_pct[b]=nb/N*100

for b in bucket:
    for c in candidates:
        idxs=[wi for wi,world in enumerate(worlds)
              if sum(1 for c2 in world["东"] if c2.suit=="♠")==b[0]
              and (sum(1 for c2 in world["西"] if c2.suit=="♠") + LEAD_OWNERS.get("西",0))==b[1]]
        s=[pick[str(c)][wi] for wi in idxs]
        makrates[str(c)][b]=sum(1 for v in s if v>=NEED)/len(s) if s else 0.0

print()
print("== 黑桃分布桶 → 各候选做成率（≥9墩世界占比）==")
header="分布(东-西) 世界占比"
for c in candidates: header+=f" | {c}"
print(header)
for b in sorted(bucket,key=lambda x:x[0]):
    row=f"东{b[0]}-西{b[1]}  {bucket_pct[b]:5.1f}%"
    for c in candidates:
        row+=f" | {makrates[str(c)][b]*100:5.1f}%"
    print(row)

print()
print("== 全样本整体做成率 ==")
for c in candidates:
    s=pick[str(c)]
    print(f"  {c}: {sum(1 for v in s if v>=NEED)/N*100:.1f}%")