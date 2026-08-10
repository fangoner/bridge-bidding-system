import random, time, ctypes, os
from bridge.play_types import Card, POSITION_ORDER
from bridge.mcts.sampler import ALL_CARDS
from bridge.mcts import direct_dds as DDS

def make_hands():
    deck = list(ALL_CARDS)
    random.shuffle(deck)
    hands = {}
    for i, p in enumerate(POSITION_ORDER):
        hands[p] = deck[i*13:(i+1)*13]
    return hands

def run(n, same):
    base = make_hands()
    deals = []
    for _ in range(n):
        h = base if same else make_hands()
        deals.append((h, "NT", "北", []))
    t0 = time.time()
    for s in range(0, n, 200):
        DDS.solve_all_boards_raw(deals[s:s+200])
    dt = time.time() - t0
    print(f"  same={same} n={n}: total={dt:.2f}s per_deal={dt/n*1000:.2f}ms")

if __name__ == "__main__":
    print("cpu:", os.cpu_count())
    run(800, True)   # 相同手牌
    run(800, False)  # 不同手牌