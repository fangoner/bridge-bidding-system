import random, time, ctypes, os
from bridge.play_types import Card, POSITION_ORDER
from bridge.mcts.sampler import ALL_CARDS
from bridge.mcts import direct_dds as DDS

def deal_hands():
    deck = list(ALL_CARDS)
    random.shuffle(deck)
    hands = {}
    for i, p in enumerate(POSITION_ORDER):
        hands[p] = deck[i*13:(i+1)*13]
    return hands

def bench(n_boards=2000, trump="NT", first="北", distinct=False):
    deals = []
    for _ in range(n_boards):
        deck = list(ALL_CARDS)
        random.shuffle(deck)
        hands = {}
        for i, p in enumerate(POSITION_ORDER):
            hands[p] = deck[i*13:(i+1)*13]
        deals.append((hands, trump, first, []))
    t0 = time.time()
    res = []
    for s in range(0, n_boards, 200):
        res.extend(DDS.solve_all_boards_raw(deals[s:s+200]))
    dt = time.time() - t0
    ok = sum(1 for r in res if r is not None and len(r) > 0)
    return dt, ok

if __name__ == "__main__":
    print("cpu_count:", os.cpu_count())
    # 第一次：新进程启动即跑
    dt, ok = bench(2000)
    print(f"run1 fresh_process: total={dt:.2f}s per_deal={dt/2000*1000:.2f}ms ok={ok}/2000")
    # 第二次：同一进程再跑
    dt, ok = bench(2000)
    print(f"run2 same_process: total={dt:.2f}s per_deal={dt/2000*1000:.2f}ms ok={ok}/2000")
    # 跑 100 板小批量
    dt, ok = bench(100)
    print(f"run3 n=100: total={dt:.2f}s per_deal={dt/100*1000:.2f}ms ok={ok}/100")