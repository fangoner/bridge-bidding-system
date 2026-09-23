import os, random, sys
from collections import Counter
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from bridge.play_types import Card, Contract, PlayState, PlayPhase, Trick
from bridge.mcts.dd_search import DDSearch

# ==== 第一墩完成，第二墩西攻7，北跟牌位 ====
# 东西初始黑桃共 7 张: A K J 9 8 7 6
# 第一墩: 西8 - 北5 - 东6 - 南3（西赢）；第二墩: 西7 领出
# 北剩 T/Q/4；南剩 ♠2；东西已出(西8,7 / 东6) → 东西剩余黑桃 A K J 9(4张) 分给东西
north = [Card("♠","T"),Card("♠","Q"),Card("♠","4"),
         Card("♥","Q"),Card("♥","4"),Card("♥","3"),
         Card("♦","A"),Card("♦","K"),Card("♦","4"),
         Card("♣","4"),Card("♣","3"),Card("♣","2")]           # 12张(出5后)
south = [Card("♠","2"),Card("♥","A"),Card("♥","K"),Card("♥","2"),
         Card("♦","Q"),Card("♦","3"),Card("♦","2"),
         Card("♣","K"),Card("♣","Q"),Card("♣","J"),Card("♣","T"),Card("♣","9")]  # 12张(出3后)
east_f = Card("♠","6")   # 第一墩东6
west_f = Card("♠","8")   # 第一墩西8
north_f = Card("♠","5")  # 第一墩北5
south_f = Card("♠","3")  # 第一墩南3
lead2 = Card("♠","7")    # 第二墩西攻7

# 剩余未知牌: 西剩11张(13-8-7)，东剩12张(13-6)
RANKS=list("AKQJT98765432"); SUITS=list("♠♥♦♣")
def remaining():
    used=set()
    for c in north+south: used.add((c.suit,c.rank))
    for c in (east_f, west_f, north_f, south_f, lead2): used.add((c.suit,c.rank))
    return [Card(s,r) for s in SUITS for r in RANKS if (s,r) not in used]

def deal(rng):
    rem=remaining(); rng.shuffle(rem)
    return {"南":south,"北":north,"西":rem[:11],"东":rem[11:]}

NEED=9
candidates=[Card("♠","T"),Card("♠","Q"),Card("♠","4")]

# 第一墩（已完成的完整墩）出牌顺序：西8 - 北5 - 东6 - 南2（西赢）
t1=Trick(trump="NT"); t1.leader="西"
t1.cards=[("西",west_f),("北",north_f),("东",east_f),("南",south_f)]

state=PlayState(contract=Contract(level=3,suit="NT",declarer="南"),
                hands={"南":south,"北":north,"西":[],"东":[]}, vulnerability="NV")
state.dummy="北"; state.current_player="北"; state.lead_player="西"
state.phase=PlayPhase.PLAYING
state.tricks=[t1]
state.current_trick=Trick(trump="NT"); state.current_trick.cards=[("西",lead2)]
state.current_trick.leader="西"
state.declarer_tricks=0; state.defender_tricks=1   # 第一墩西8胜
state.finesse_flow={}; state.finesse_flow_ends={}

N=4000
rng=random.Random(20260927)
worlds_raw=[deal(rng) for _ in range(N)]

def ok_constraint(w):
    # 第一墩西8(长四: 3大+8)，第二墩西7 → 7必属西 → 西=3大+8+7=5张，东=6+1大=2张
    es=[c for c in w["东"] if c.suit=="♠"]
    ws=[c for c in w["西"] if c.suit=="♠"]
    if (len(es)+1, len(ws)+2) != (2, 5):
        return False
    h=sum(1 for c in ws if c.rank_value > 6)  # 西比8大的数（=3）
    return h>=3

worlds=[w for w in worlds_raw if ok_constraint(w)]
print(f"约束过滤: {len(worlds)}/{N} 世界满足首攻长四")

dd=DDSearch(num_samples=N,min_samples=15,time_limit=120.0,endgame_card_threshold=4,
            max_enumerations=5000)
res=dd.search(state,perspective="北",actual_turn="北",preset_worlds=worlds)
fo=res.get("full_output",{})
if "mcts_stats" not in fo:
    print("search res:", {k:v for k,v in res.items() if k!="full_output"})
    print("fo:", {k:v for k,v in fo.items() if k!="候选对比"})
    raise SystemExit("no mcts_stats")
mcts=fo["mcts_stats"]
pick={c["card"]: c["scores"] for c in mcts["candidates"]}
for c in candidates:
    assert len(pick.get(str(c),[]))==len(worlds), (str(c), len(pick.get(str(c),[])))

print(f"== 确定分布(东2-西5) 下 北跟牌 Q/T/4 做成率 (有效{len(worlds)}世界, 需{NEED}墩) ==")
print("== 细分: 东初始黑桃 = 6 + 剩余1张大牌 ∈{A,K,J,9} ==")
bucket=Counter(); makrates={str(c):{} for c in candidates}; bucket_pct={}
for wi,w in enumerate(worlds):
    east_sp=[c for c in w["东"] if c.suit=="♠"]
    # 东初始 = 6 + 剩余;找剩余那张大牌
    rem=[c.rank for c in east_sp if c.rank in "AKJ9"]
    big=rem[0] if rem else "?"
    b=big; bucket[b]+=1
for b,nb in bucket.items(): bucket_pct[b]=nb/len(worlds)*100
for b in bucket:
    for c in candidates:
        idxs=[wi for wi,w in enumerate(worlds)
              if any(cc.rank==b for cc in w["东"] if cc.suit=="♠")]
        s=[pick[str(c)][wi] for wi in idxs]
        makrates[str(c)][b]=sum(1 for v in s if v>=NEED)/len(s) if s else 0.0
hdr="东持大牌 世界占比"
for c in candidates: hdr+=f" | {c}"
print(hdr)
for b in ["A","K","J","9"]:
    if b not in bucket: continue
    row=f"东持♠{b}   {bucket_pct[b]:5.1f}%"
    for c in candidates: row+=f" | {makrates[str(c)][b]*100:5.1f}%"
    print(row)
print()
print("== 全样本(确定分布) ==")
for c in candidates:
    s=pick[str(c)]
    print(f"  {c}: 做成率 {sum(1 for v in s if v>=NEED)/len(s)*100:.1f}%  平均 {sum(s)/len(s):.2f}墩")
print()
# 交叉: 东持啥 vs 推荐
print("== 各世界最优牌(做成率口径) 分布 ==")
from collections import Counter as C2
best=C2()
for wi in range(len(worlds)):
    rates={str(c): pick[str(c)][wi] for c in candidates}
    m=max(rates.values())
    top=[k for k,v in rates.items() if v==m]
    best[tuple(sorted(top))]+=1
for k,v in best.most_common():
    print(f"  {'|'.join(k)}: {v/len(worlds)*100:.1f}%")