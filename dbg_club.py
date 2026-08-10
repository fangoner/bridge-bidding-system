import itertools
import random
from bridge.play_types import Card
from bridge.mcts.direct_dds import solve_all_boards_raw

random.seed(7)

ALL_SUITS = ["♠", "♥", "♦", "♣"]
ALL_RANKS = ["A", "K", "Q", "J", "T", "9", "8", "7", "6", "5", "4", "3", "2"]

def mk(pairs):
    return [Card(suit=s, rank=r) for s, r in pairs]

# ── 真实牌局（2NT，北庄家，南北作庄）──
# 初始整手
south_full = mk([("♠","A"),("♠","T"),("♠","7"),("♠","4"),("♠","2"),
                 ("♥","K"),("♥","8"),("♥","5"),
                 ("♦","9"),("♦","5"),
                 ("♣","T"),("♣","8"),("♣","6")])
north_full = mk([("♠","K"),("♠","8"),
                 ("♥","A"),("♥","9"),
                 ("♦","A"),("♦","T"),("♦","6"),("♦","4"),
                 ("♣","A"),("♣","J"),("♣","5"),("♣","4"),("♣","3")])

# 已出牌（含当前墩）
# T1: 东♥Q 南♥5 西♥4 北♥A
# T2: 北♠8 东♦2 南♠A 西♠3
# T3: 南♣6 西♣K 北♣A 东♣2
# T4(当前): 北♣5 东♣7
south_played = mk([("♥","5"),("♠","A"),("♣","6")])
north_played = mk([("♥","A"),("♠","8"),("♣","A"),("♣","5")])
east_played = mk([("♥","Q"),("♦","2"),("♣","2"),("♣","7")])
west_played = mk([("♥","4"),("♠","3"),("♣","K")])

# 剩余手牌（各自移除已出）
south_rem = [c for c in south_full if c not in south_played]
north_rem = [c for c in north_full if c not in north_played]

# 未知牌池 = 52 - 南北整手 - 东西已出
known = set((c.suit, c.rank) for c in south_full + north_full + east_played + west_played)
pool = [(s, r) for s in ALL_SUITS for r in ALL_RANKS if (s, r) not in known]

# 东西剩余张数
east_n = 13 - len(east_played)
west_n = 13 - len(west_played)

def build_world():
    others = list(pool)
    random.shuffle(others)
    east_rem = mk(others[:east_n])
    west_rem = mk(others[east_n:east_n + west_n])
    return {
        "南": list(south_rem),
        "北": list(north_rem),
        "东": east_rem,
        "西": west_rem,
    }

def run_world(world):
    trick_cards = [("北", Card("♣", "5")), ("东", Card("♣", "7"))]
    first = "北"
    trump = "NT"
    solved_list = solve_all_boards_raw([(world, trump, first, trick_cards)])
    solved = solved_list[0]
    if solved is None:
        return None
    score_map = {}
    for suit, rank, equals, score in solved:
        s = {0: "♠", 1: "♥", 2: "♦", 3: "♣"}[suit]
        r = {14: "A", 13: "K", 12: "Q", 11: "J", 10: "T", 9: "9", 8: "8",
             7: "7", 6: "6", 5: "5", 4: "4", 3: "3", 2: "2"}[rank]
        score_map[(s, r)] = score
    return score_map

# 校验手牌完整性
def check(world):
    allk = [c.suit + c.rank for h in world.values() for c in h]
    if len(set(allk)) != len(allk):
        return False, f"重复牌 {len(allk)}/{len(set(allk))}"
    for pos, h in world.items():
        if len(h) != {"南": len(south_rem), "北": len(north_rem),
                      "东": east_n, "西": west_n}[pos]:
            return False, f"{pos} 张数错误 {len(h)}"
    return True, "ok"

N = 50
c8_scores = []
cT_scores = []
both_zero = 0
for _ in range(N):
    world = build_world()
    ok, msg = check(world)
    if not ok:
        print("构造失败:", msg)
        continue
    sm = run_world(world)
    if sm is None:
        continue
    s8 = sm.get(("♣", "8"))
    sT = sm.get(("♣", "T"))
    if s8 is None or sT is None:
        continue
    c8_scores.append(s8)
    cT_scores.append(sT)
    if s8 == 0 and sT == 0:
        both_zero += 1

print(f"东南西北剩余: 南{len(south_rem)} 北{len(north_rem)} 东{east_n} 西{west_n}")
print(f"北剩余梅花: {[c.rank for c in north_rem if c.suit=='♣']}")
print(f"未知牌池 {len(pool)} 张: ♠QJ965 ♥JT7632 ♦KQJ873 ♣Q9")
print(f"有效样本 {len(c8_scores)}/{N}")
print(f"♣8 得分: {c8_scores}")
print(f"♣T 得分: {cT_scores}")
if c8_scores:
    print(f"♣8 平均 {sum(c8_scores)/len(c8_scores):.2f}, 范围 {min(c8_scores)}-{max(c8_scores)}")
    print(f"♣T 平均 {sum(cT_scores)/len(cT_scores):.2f}, 范围 {min(cT_scores)}-{max(cT_scores)}")
    print(f"♣8 优于 ♣T 的世界数: {sum(1 for a,b in zip(c8_scores,cT_scores) if a>b)}")
    print(f"♣T 优于 ♣8 的世界数: {sum(1 for a,b in zip(c8_scores,cT_scores) if b>a)}")
    print(f"两者均为0的世界数: {both_zero}")