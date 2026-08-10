import random
from bridge.play_types import Card, POSITION_ORDER
from bridge.mcts.constraints import BidConstraint
from bridge.mcts.sampler import DealSampler, ALL_CARDS
from bridge.mcts.direct_dds import solve_all_boards_raw, _RANK_TO_BIT, _PLAYER_TO_POS

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

POS_IDX = {"北": 0, "东": 1, "南": 2, "西": 3}
IDX_POS = {0: "北", 1: "东", 2: "南", 3: "西"}
SUIT_IDX = {"♠": 0, "♥": 1, "♦": 2, "♣": 3}

def fmt_card(c):
    return c.suit + c.rank

def best_card(hands, leader, trick):
    solved = solve_all_boards_raw([(hands, "NT", leader, trick)])[0]
    if not solved:
        return None
    best = None
    for suit, rank, equals, score in solved:
        s = {0: "♠", 1: "♥", 2: "♦", 3: "♣"}[suit]
        r = {14: "A", 13: "K", 12: "Q", 11: "J", 10: "T", 9: "9", 8: "8",
             7: "7", 6: "6", 5: "5", 4: "4", 3: "3", 2: "2"}[rank]
        cand = Card(s, r)
        if best is None or score > best[1] or (score == best[1] and rank > _RANK_TO_BIT[best[0].rank]):
            best = (cand, score)
    return best[0]

def trick_winner(trick):
    lead_suit = trick[0][1].suit
    win = None
    for pos, c in trick:
        if c.suit != lead_suit:
            continue
        if win is None or _RANK_TO_BIT[c.rank] > _RANK_TO_BIT[win[1].rank]:
            win = (pos, c)
    return win[0]

def run_sim(hands0, forced):
    hands = {p: list(c) for p, c in hands0.items()}
    leader = "北"
    trick = [("北", Card("♣", "5")), ("东", Card("♣", "7"))]
    decl_tricks = 0
    log = []
    first_south_forced = False
    remaining = sum(len(v) for v in hands.values())
    while remaining > 0:
        if len(trick) == 0:
            leader = leader  # already set by winner
        cur_pos = IDX_POS[(POS_IDX[leader] + len(trick)) % 4]
        cur_hand = hands[cur_pos]
        if cur_pos == "南" and not first_south_forced:
            play = Card("♣", forced)
            first_south_forced = True
        else:
            play = best_card(hands, leader, trick)
            if play is None:
                play = cur_hand[0]
        cur_hand.remove(play)
        trick.append((cur_pos, play))
        if len(trick) == 4:
            w = trick_winner(trick)
            log.append((list(trick), w))
            if w in ("北", "南"):
                decl_tricks += 1
            leader = w
            trick = []
        remaining = sum(len(v) for v in hands.values())
    return decl_tricks, log

def fmt_hand(hand):
    by = {"♠": [], "♥": [], "♦": [], "♣": []}
    for c in hand:
        by[c.suit].append(c.rank)
    order = ["A","K","Q","J","T","9","8","7","6","5","4","3","2"]
    return " ".join(s + "".join(sorted(r, key=order.index, reverse=True)) for s, r in by.items())

# 取第一个西缺门世界
w0 = None
for i in range(250):
    w = sampler._sample_one(known_info, {p: c for p, c in constraints.items()})
    if sum(1 for c in w["西"] if c.suit == "♣") == 0:
        w0 = w
        break

print("=== 西缺门世界 ===")
for pos in POSITION_ORDER:
    print(f"{pos}: {fmt_hand(w0[pos])}")
print(f"当前墩: 北♣5 - 东♣7 - 南?    (NT, 北首攻)")
print("="*72)

for forced in ("8", "T"):
    dt, log = run_sim(w0, forced)
    print(f"\n===== 南出 ♣{forced}: 庄家方总赢墩 = {3 + dt} =====")
    for i, (trick, winner) in enumerate(log, 1):
        plays = "  ".join(f"{pos}{fmt_card(c)}" for pos, c in trick)
        tag = "庄" if winner in ("北","南") else "防"
        print(f"  T{i}: {plays}   -> {winner}赢 ({tag})")