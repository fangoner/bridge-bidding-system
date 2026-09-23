import os, random, sys
from collections import Counter
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from bridge.play_types import Card, Contract, PlayState, PlayPhase, Trick
from bridge.mcts.dd_search import DDSearch

# 北(明手)13张原手牌；南13张
north = [Card("♠","T"),Card("♠","Q"),Card("♠","5"),Card("♠","4"),
         Card("♥","Q"),Card("♥","4"),Card("♥","3"),
         Card("♦","A"),Card("♦","K"),Card("♦","4"),
         Card("♣","4"),Card("♣","3"),Card("♣","2")]
south = [Card("♠","3"),Card("♠","2"),Card("♥","A"),Card("♥","K"),Card("♥","2"),
         Card("♦","Q"),Card("♦","3"),Card("♦","2"),
         Card("♣","K"),Card("♣","Q"),Card("♣","J"),Card("♣","T"),Card("♣","9")]

# 东/西采样：去掉南13+北13+已出西♠8 → 25 张。西剩12(已出8)，东13
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
print("构建", len(worlds), "世界（东西黑桃共6张 A K J 9 7 6）")

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
fo=res.get("full_output",{})
if "candidates_key" not in fo and fo.get("推荐出牌"):
    pass
# 直接拿 candidates（child_stats），含每世界 scores
mcts=fo.get("mcts_stats") or {}
if not mcts:
    print("res:", {k:v for k,v in res.items() if k!='full_output'})
    print("fo:", {k:v for k,v in fo.items() if k!='候选对比'})
    raise SystemExit
cands=mcts["candidates"]
print("候选数:", len(cands))
pick={c["card"]: c["scores"] for c in cands}
print("各候选 scores 长度:", {k:len(v) for k,v in pick.items()})
for c in candidates: assert len(pick[str(c)])==N, str(c)

bucket=Counter(); result={}
for wi,world in enumerate(worlds):
    es=sum(1 for c in world["东"] if c.suit=="♠"); ws=sum(1 for c in world["西"] if c.suit=="♠")
    b=(es,ws); bucket[b]+=1
    per=[pick[str(c)][wi] for c in candidates]
    win=sum(1 for s in per if s>=NEED)
    cls="全赢" if win==len(candidates) else ("全输" if win==0 else "临界")
    result.setdefault(b,Counter())[cls]+=1

print("\n== 黑桃分布桶 → 全赢/临界/全输 比例 ==")
for b in sorted(result,key=lambda x:x[0]):
    c=result[b]; sp=bucket[b]/N*100; tot=sum(c.values())
    print(f"东{b[0]}张-西{b[1]}张 (世界占{sp:5.1f}%): 全赢 {c['全赢']/tot*100:5.1f}% | "
          f"临界 {c['临界']/tot*100:5.1f}% | 全输 {c['全输']/tot*100:5.1f}%")
aw=sum(v['全赢'] for v in result.values()); cr=sum(v['临界'] for v in result.values()); lo=sum(v['全输'] for v in result.values())
print(f"\n== 全样本 {N} 世界: 全赢 {aw/N*100:.1f}% | 临界 {cr/N*100:.1f}% | 全输 {lo/N*100:.1f}% ==")