import sys

sys.path.insert(0, r"d:\Bridge Card\Bidding System")

from bridge.play_service import PlayService
from bridge.play_types import PlayerRole, Card

roles = {p: PlayerRole.AI.value for p in ("南", "北", "东", "西")}
svc = PlayService(None)


def state_of(south, north):
    return svc.initialize({"南": south, "北": north}, "4S", "南", player_roles=roles)


def set_trick(st, cur_player, cards):
    st.current_player = cur_player
    st.current_trick.cards = []
    for pos, card_str in cards:
        st.current_trick.cards.append((pos, Card(card_str[0], card_str[1:])))


FS = {"♦": {"对象": 13, "说明": "test", "来源": "probe", "对象牌": "K"}}

# 用例1：同伙北引 ♦8（<威胁T），西跟 ♦4，南接应持 ♦AQJ3 →
# 威胁=max(敌方剩余非K)=T；引牌8<10 → 出 >10 的最小牌 = J（压威胁，保留Q/A）
st1 = state_of({"spades": "AKQJ", "hearts": "A32", "diamonds": "AQJ3", "clubs": "432"},
               {"spades": "32", "hearts": "KQJ", "diamonds": "8765", "clubs": "AQJ"})
set_trick(st1, "南", [("北", "♦8"), ("西", "♦4")])
r1 = svc._finesse_commit_check(st1, FS)
print("用例1 引8<威胁T 南持AQJ3:", r1)
assert r1 and r1[0] == "♦J", f"期望♦J，实际 {r1}"

# 用例2：同伙北引 ♦Q（>威胁J），西 ♦4，南持 ♦A32 → 引牌已胜，出最小 ♦2
st2 = state_of({"spades": "AKQJ", "hearts": "A32", "diamonds": "A32", "clubs": "432"},
               {"spades": "32", "hearts": "KQJ", "diamonds": "Q876", "clubs": "AQJ"})
set_trick(st2, "南", [("北", "♦Q"), ("西", "♦4")])
r2 = svc._finesse_commit_check(st2, FS)
print("用例2 引Q>威胁J 南持A32:", r2)
assert r2 and r2[0] == "♦2", f"期望♦2(最小跟)，实际 {r2}"

# 用例3：敌方本墩已出对象K（西 ♦K）→ 南持 ♦AQ3 出最小 >K 的顶张 A
st3 = state_of({"spades": "AKQJ", "hearts": "A32", "diamonds": "AQ3", "clubs": "432"},
               {"spades": "32", "hearts": "KQJ", "diamonds": "8765", "clubs": "AQJ"})
set_trick(st3, "南", [("北", "♦8"), ("西", "♦K")])
r3 = svc._finesse_commit_check(st3, FS)
print("用例3 西已出K 南持AQ3:", r3)
assert r3 and r3[0] == "♦A", f"期望♦A(盖)，实际 {r3}"

# 用例4：无牌可压威胁 → 尊重引擎 None（南小牌全 < 敌方威胁）
st4 = state_of({"spades": "AKQJ", "hearts": "A32", "diamonds": "432", "clubs": "432"},
               {"spades": "32", "hearts": "KQJ", "diamonds": "T9876", "clubs": "AQJ"})
set_trick(st4, "南", [("北", "♦9"), ("西", "♦4")])
r4 = svc._finesse_commit_check(st4, FS)
print("用例4 无牌压威胁 南持432:", r4)
assert r4 is None, f"无牌可压应None，实际 {r4}"

# 用例5：对象K已现身 → 不强接应（尊重引擎兑现）
st5 = state_of({"spades": "AKQJ", "hearts": "A32", "diamonds": "AQJ3", "clubs": "432"},
               {"spades": "32", "hearts": "KQJ", "diamonds": "8765", "clubs": "AQJ"})
dummy_trick = type(st5.current_trick)(trump="♠")
dummy_trick.cards = [("东", Card("♦", "K")), ("南", Card("♦", "A"))]
st5.tricks.append(dummy_trick)
set_trick(st5, "南", [("北", "♦8"), ("西", "♦6")])
r5 = svc._finesse_commit_check(st5, FS)
print("用例5 对象K已现身:", r5)
assert r5 is None, f"对象已现应None，实际 {r5}"

print("\nPASS: 接应选牌（威胁比较制）全部通过")