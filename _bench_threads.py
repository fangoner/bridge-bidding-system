import random, time, ctypes, os
from bridge.play_types import Card, POSITION_ORDER
from bridge.mcts.sampler import ALL_CARDS
from bridge.mcts import direct_dds as DDS

def make_deals(n=800):
    deals = []
    for _ in range(n):
        deck = list(ALL_CARDS)
        random.shuffle(deck)
        hands = {}
        for i, p in enumerate(POSITION_ORDER):
            hands[p] = deck[i*13:(i+1)*13]
        deals.append((hands, "NT", "北", []))
    return deals

def bench_threads(nthreads):
    dll = DDS._load_dll()
    try:
        dll.SetMaxThreads(nthreads)
    except Exception as e:
        print(f"  SetMaxThreads({nthreads}) err: {e}")
        return
    # 先暖一次
    deals = make_deals(800)
    t0 = time.time()
    for s in range(0, 800, 200):
        DDS.solve_all_boards_raw(deals[s:s+200])
    dt = time.time() - t0
    print(f"  threads={nthreads}: total={dt:.2f}s per_deal={dt/800*1000:.2f}ms")

if __name__ == "__main__":
    print("cpu_count:", os.cpu_count())
    for nt in [1, 2, 4, 8]:
        bench_threads(nt)