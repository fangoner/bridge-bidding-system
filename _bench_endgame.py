import random, time
from bridge.play_types import Card, POSITION_ORDER, PlayState, PlayPhase, Contract
from bridge.mcts.sampler import ALL_CARDS
from bridge.mcts import direct_dds as DDS

def make_hands():
    deck = list(ALL_CARDS)
    random.shuffle(deck)
    hands = {}
    for i, p in enumerate(POSITION_ORDER):
        hands[p] = deck[i*13:(i+1)*13]
    return hands

# 满局：13墩全在
def bench_full(n=200):
    deals = []
    for _ in range(n):
        deals.append((make_hands(), "NT", "北", []))
    t0 = time.time()
    for s in range(0, n, 200):
        DDS.solve_all_boards_raw(deals[s:s+200])
    print(f"FULL(13墩) n={n}: total={time.time()-t0:.2f}s per_deal={(time.time()-t0)/n*1000:.2f}ms")

# 残局：每家只留 k 张
def bench_short(k, n=200):
    deals = []
    for _ in range(n):
        h = make_hands()
        h2 = {p: h[p][:k] for p in POSITION_ORDER}
        deals.append((h2, "NT", "北", []))
    t0 = time.time()
    for s in range(0, n, 200):
        DDS.solve_all_boards_raw(deals[s:s+200])
    print(f"ENDGAME({k}墩) n={n}: total={time.time()-t0:.2f}s per_deal={(time.time()-t0)/n*1000:.2f}ms")

if __name__ == "__main__":
    bench_full(200)
    bench_short(10, 200)
    bench_short(5, 200)
    bench_short(3, 200)