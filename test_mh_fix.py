import random
from bridge.play_types import Card
from bridge.mcts.constraints import BidConstraint
from bridge.mcts import sampler

random.seed(42)

def make_cards(pairs):
    return [Card(suit=s, rank=r) for s, r in pairs]

# 池：6♠(0HCP) + 4♥(A,Q=6HCP + 2低) + 2♦低 + 1♣低 = 13 张，总 HCP=6
pool = make_cards([
    ("♠","2"),("♠","3"),("♠","4"),("♠","5"),("♠","6"),("♠","7"),
    ("♥","A"),("♥","Q"),("♥","2"),("♥","3"),
    ("♦","2"),("♦","3"),
    ("♣","2"),
])

def run(pool_cards, remaining, con, reps=200, beta=1.0):
    def build():
        return {
            "result": {},
            "unknown_pool": [Card(suit=c.suit, rank=c.rank) for c in pool_cards],
            "remaining_counts": remaining,
            "known_voids": {},
            "known_cards": set(),
            "own_hand": [],
            "dummy_hand": [],
            "played": {},
        }
    active = {con.position: con}
    ok = 0
    for _ in range(reps):
        world, ok_flag = sampler._sample_mh_repair(build(), active, beta=beta)
        if ok_flag:
            ok += 1
    label = f"{con.position} min={con.min_hcp} max={con.max_hcp} suit={dict(con.suit_min)}"
    print(f"beta={beta} | {label}: MH 成功率 = {ok}/{reps} = {ok/reps*100:.1f}%")

# 场景1：死锁场景（sp 缺长 + HCP 压在下限）
run(pool, {"西": 10, "东": 3},
    BidConstraint(position="西", min_hcp=6, suit_min={"♠": 6}, inference_source="hard_coded"))

# 场景2：sp 缺长 + HCP 上下限都有（验证不越过 max 振荡）
pool2 = make_cards([
    ("♠","A"),("♠","Q"),("♠","J"),("♠","T"),("♠","9"),("♠","8"),  # 6♠ 7HCP
    ("♥","2"),("♥","3"),("♥","4"),("♦","2"),("♦","3"),("♣","2"),("♣","3"),
])
run(pool2, {"西": 10, "东": 3},
    BidConstraint(position="西", min_hcp=4, max_hcp=8, suit_min={"♠": 6}, inference_source="hard_coded"))