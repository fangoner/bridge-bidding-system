import sys, os, random, time
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from bridge.play_types import Card, PlayState, Contract, PlayPhase, POSITION_ORDER
from bridge.mcts.sampler import DealSampler, _extract_known_info, _sample_uniform
from bridge.mcts.dd_search import _build_dds_data
from bridge.mcts.direct_dds import solve_all_boards_raw

# 复用原场景的完整 52 张构造
HANDS = {
    "南": {"spades": "AKQ", "hearts": "J32", "diamonds": "AKQ", "clubs": "5432"},
    "西": {"spades": "JT9", "hearts": "Q876", "diamonds": "J5", "clubs": "T876"},
    "北": {"spades": "8765", "hearts": "AKQ", "diamonds": "432", "clubs": "AKQ"},
    "东": {"spades": "432", "hearts": "T954", "diamonds": "T987", "clubs": "J5"},
}
SUIT_ORDER = ["♠", "♥", "♦", "♣"]
SUIT_KEY = {"♠": "spades", "♥": "hearts", "♦": "diamonds", "♣": "clubs"}
def build(su):
    return {pos: [Card(suit=s, rank=r) for s in SUIT_ORDER for r in d[SUIT_KEY[s]]]
            for pos, d in su.items()}
full = build(HANDS)

# 已打1墩: 南♠A 西♠T 北♠8 东♠4
from bridge.play_types import Trick
played_trick = [("南", Card("♠","A")), ("西", Card("♠","T")),
                ("北", Card("♠","8")), ("东", Card("♠","4"))]
trick1 = Trick(leader="南", cards=played_trick)
played_flat = [tuple(x) for x in played_trick]  # (pos, card)

fully = {p: [c for c in full[p] if not (c.suit=="♠" and c.rank in ("A","T","8","4"))]
         for p in POSITION_ORDER}
# 防守视角：只知道自己(南)和明手(北)手牌，东西未知
hands = {p: (list(fully[p]) if p in ("南","北") else []) for p in POSITION_ORDER}

state = PlayState(
    hands=hands,
    contract=Contract(suit="NT", level=3, declarer="南"),
)
state.tricks = [trick1]
state.current_trick = Trick(trump="NT", leader=None, cards=[])
state.declarer_tricks = 1
state.defender_tricks = 0
state.phase = PlayPhase.PLAYING
state.current_player = "南"


def run_scenario(label, forced_voids, n=200):
    # 提取真实 known_info
    known_info = _extract_known_info(state, "南")
    # 强制注入 known_voids（模拟场上大量缺门信息）
    known_info["known_voids"] = forced_voids
    print(f"\n===== {label} =====")
    print("known_voids:", forced_voids)

    bad = none_build = solv_none = 0
    incomplete_first5 = []
    t0 = time.time()
    for i in range(n):
        w = _sample_uniform(known_info)
        total = sum(len(v) for v in w.values())
        dup = len({(c.suit, c.rank) for v in w.values() for c in v}) != total
        # 期望剩 48 张（52-4）
        if total != 48 or dup:
            bad += 1
            if len(incomplete_first5) < 5:
                missing = 48 - total if total < 48 else 0
                incomplete_first5.append((i, total, dup, missing))
        hands2, t, first, tc = _build_dds_data(w, played_flat, [], "南", "南", "南", "NT")
        if hands2 is None:
            none_build += 1
    print(f"采样耗时: {time.time()-t0:.2f}s, 世界数: {n}")
    print(f"不完整/重复世界: {bad}/{n}")
    for x in incomplete_first5:
        print(f"  世界{x[0]}: 总张数={x[1]} 重复={x[2]} 缺牌={x[3]}")
    # 用最后 50 个世界直接 DDS（需 endplay 环境，缺失时跳过）
    try:
        t1 = time.time()
        solved = solve_all_boards_raw([(_sample_uniform(known_info), "NT", "南", []) for _ in range(50)])
        print(f"DDS 求解 50 个: {sum(1 for s in solved if s is not None)}/50, 耗时 {time.time()-t1:.2f}s")
    except Exception as e:
        print(f"DDS 求解跳过: {type(e).__name__}: {e}")


# 场景A：少量 void（基线，应接近全部完整）
run_scenario("基线：正常 void（少）", {"南": set(), "东": set()}, n=200)

# 场景B：单家大量 void —— 西 void♥♦（西手里那些♥♦被跳过）
run_scenario("西 void♥♦", {"西": {"♥", "♦"}}, n=200)

# 场景C：两家共享 void —— 西&东都 void♦，♦牌被迫全塞给北/南
run_scenario("西&东 void♦", {"西": {"♦"}, "东": {"♦"}}, n=200)

# 场景D：极端 —— 三家对同一花色 void，该花色牌无处可放
run_scenario("南&西&北 void♠（♠牌无处放）", {"南": {"♠"}, "西": {"♠"}, "北": {"♠"}}, n=200)