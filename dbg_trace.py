import random
from bridge.play_types import Card
from bridge.mcts.state_utils import SUIT_DISPLAY_ORDER, RANK_DESC
from bridge.mcts.constraints import BidConstraint
from bridge.mcts.sampler import _sample_mh_repair, _check_feasible, _sample_uniform, _reduce_constraint_for_played, _propose_swap

ALL = [Card(suit=s, rank=r) for s in SUIT_DISPLAY_ORDER for r in RANK_DESC]
HCP = {"A":4,"K":3,"Q":2,"J":1}
def hcp(cards): return sum(HCP.get(c.rank,0) for c in cards)
def dist(cards):
    d={s:0 for s in SUIT_DISPLAY_ORDER}
    for c in cards: d[c.suit]+=1
    return d

random.seed(42)
pool=[c for c in ALL]
random.shuffle(pool)
sp=sorted([c for c in pool if c.suit=="♠"], key=lambda c:HCP.get(c.rank,0), reverse=True)
oth=[c for c in pool if c.suit!="♠"]
chosen=sp[:6]+oth[:18]
random.shuffle(chosen)
ki={"known_cards":set(),"unknown_pool":chosen,
    "remaining_counts":{"北":0,"南":0,"西":12,"东":12},
    "known_voids":{},"own_hand":[],"dummy_hand":[],"result":{},
    "played":{"西":{"hcp":0,"controls":0,"suit":{s:0 for s in SUIT_DISPLAY_ORDER}},
              "东":{"hcp":0,"controls":0,"suit":{s:0 for s in SUIT_DISPLAY_ORDER}}}}
base=BidConstraint(position="西",min_hcp=6,max_hcp=10,suit_min={"♠":6},inference_source="hard_coded_jf")
red=_reduce_constraint_for_played(base,{"hcp":0,"controls":0,"suit":{"♠":0,"♥":1,"♦":0,"♣":0}},12)
ac={"西":red}
sp_hcp=sum(HCP.get(c.rank,0) for c in chosen if c.suit=="♠")
non_sp_0hcp=sum(1 for c in chosen if c.suit!="♠" and HCP.get(c.rank,0)==0)
from bridge.mcts.sampler import _position_hcp_feasible
print("池♠HCP=",sp_hcp," 非♠0HCP张数=",non_sp_0hcp," feasible=",_check_feasible(ac,ki),
      " pos_feasible=",_position_hcp_feasible(red, chosen, 12))
# 单样本跟踪
w= _sample_uniform(ki)
from bridge.mcts.constraints import validate_hard
print("初始西♠=",dist(w["西"])["♠"],"西HCP=",hcp(w["西"]),"hard=",validate_hard(w,ac))
# 手动跑300步，打印每10步
for step in range(300):
    if validate_hard(w,ac):
        print(f"step{step}: 满足! 西♠={dist(w['西'])['♠']} HCP={hcp(w['西'])}"); break
    prop=_propose_swap(w,ac,["西","东"])
    if prop is None:
        print(f"step{step}: propose=None"); break
    v,d,i,j=prop
    w[v][i],w[d][j]=w[d][j],w[v][i]
    if step%15==0:
        print(f"step{step}: 西♠={dist(w['西'])['♠']} HCP={hcp(w['西'])} (swap {v}[{i}]<->{d}[{j}])")