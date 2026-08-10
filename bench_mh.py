import random
from bridge.play_types import Card
from bridge.mcts.constraints import BidConstraint
from bridge.mcts import sampler

random.seed(7)

POS = ["南", "西", "北", "东"]

def full_deck():
    pairs = []
    for s in ["♠", "♥", "♦", "♣"]:
        for r in ["A", "K", "Q", "J", "T", "9", "8", "7", "6", "5", "4", "3", "2"]:
            pairs.append((s, r))
    return [Card(suit=s, rank=r) for s, r in pairs]

def build_known_info(pool, con_pos):
    remaining = {p: 13 for p in POS}
    return {
        "result": {},
        "unknown_pool": [Card(suit=c.suit, rank=c.rank) for c in pool],
        "remaining_counts": remaining,
        "known_voids": {},
        "known_cards": set(),
        "own_hand": [],
        "dummy_hand": [],
        "played": {},
    }

def measure(pool, con, reps=200, beta=1.0):
    def build():
        return build_known_info(pool, con.position)
    active = {con.position: con}
    ok = 0
    for _ in range(reps):
        world, flag = sampler._sample_mh_repair(build(), active, beta=beta)
        if flag:
            ok += 1
    return ok / reps

SCENARIOS = [
    ("1M开叫", BidConstraint(position="南", min_hcp=12, max_hcp=21, suit_min={"♠": 5}, inference_source="hard_coded")),
    ("弱二♠", BidConstraint(position="南", min_hcp=6, max_hcp=10, exact_suit={"♠": 6}, inference_source="hard_coded")),
    ("1NT均型", BidConstraint(position="南", min_hcp=15, max_hcp=17, balanced=True, suit_min={"♠": 2, "♥": 2, "♦": 2, "♣": 2}, suit_max={"♠": 5, "♥": 5}, inference_source="hard_coded")),
    ("技术性加倍", BidConstraint(position="南", min_hcp=12, max_hcp=21, balanced=False, suit_min={"♥": 4, "♣": 3}, suit_max={"♠": 2}, inference_source="hard_coded")),
    ("2阶争叫", BidConstraint(position="南", min_hcp=10, max_hcp=17, suit_min={"♦": 5}, inference_source="hard_coded")),
    ("1NT应6-9", BidConstraint(position="南", min_hcp=6, max_hcp=9, balanced=True, inference_source="hard_coded")),
    ("支持加强♠", BidConstraint(position="南", min_hcp=6, max_hcp=9, suit_min={"♠": 3}, inference_source="hard_coded")),
    ("逆叫16+", BidConstraint(position="南", min_hcp=16, max_hcp=21, balanced=False, suit_min={"♥": 5, "♦": 4}, inference_source="hard_coded")),
]

pool = full_deck()
print("约束场景整体 MH 成功率（完整牌池，南有约束，其余无约束）")
print(f"{'场景':<12}{'beta=1.0':>10}{'beta=0.5':>10}{'beta=0.3':>10}{'beta=0.1':>10}")
for label, con in SCENARIOS:
    row = [label]
    for beta in [1.0, 0.5, 0.3, 0.1]:
        rate = measure(pool, con, reps=200, beta=beta)
        row.append(f"{rate*100:.0f}%")
    print(f"{row[0]:<12}{row[1]:>10}{row[2]:>10}{row[3]:>10}{row[4]:>10}")