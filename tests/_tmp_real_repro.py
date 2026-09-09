import sys

sys.path.insert(0, r"d:\Bridge Card\Bidding System")

from bridge.play_service import PlayService
from bridge.play_types import PlayerRole, Card, Trick


def mk(cards_str):
    return [Card(c[0], c[1:]) for c in cards_str.split()]


roles = {p: PlayerRole.AI.value for p in ("南", "北", "东", "西")}
svc = PlayService(None)

# 真实牌面：6♠ 南庄，第6墩决策时刻（南出牌前）
SOUTH = mk("♠A ♠8 ♦A ♦Q ♣A ♣Q ♣J ♣T")   # 决筫时南现手（♠A 尚未出）
NORTH = mk("♠3 ♠2 ♦J ♦T ♦9 ♣3 ♣2")

st = svc.initialize({"南": {}, "北": {}}, "6♠", "南", player_roles=roles)
st.hands["南"] = SOUTH
st.hands["北"] = NORTH


def build_trick(trump, cards):
    t = Trick(trump=trump)
    for p, c in cards:
        t.cards.append((p, c))
    return t


st.tricks = [
    build_trick("♠", [("西", Card("♥", "K")), ("北", Card("♥", "3")), ("东", Card("♥", "7")), ("南", Card("♠", "J"))]),
    build_trick("♠", [("南", Card("♦", "2")), ("西", Card("♦", "5")), ("北", Card("♦", "K")), ("东", Card("♦", "3"))]),
    build_trick("♠", [("北", Card("♠", "5")), ("东", Card("♠", "7")), ("南", Card("♠", "T")), ("西", Card("♠", "Q"))]),
    build_trick("♠", [("西", Card("♥", "Q")), ("北", Card("♥", "2")), ("东", Card("♥", "4")), ("南", Card("♠", "9"))]),
    build_trick("♠", [("南", Card("♣", "9")), ("西", Card("♣", "7")), ("北", Card("♣", "K")), ("东", Card("♣", "4"))]),
]
# 决策时刻：北♠4、东♠6 已出，轮到南（♠A 未出）
st.current_trick = build_trick("♠", [("北", Card("♠", "4")), ("东", Card("♠", "6"))])
st.current_trick.leader = "北"
st.current_player = "南"
st.declarer_tricks = 4
st.defender_tricks = 1
st.finesse_flow["♠"] = 13

print("对象 K 现身?", svc._finesse_obj_played(st, "♠", 13))
print("己方曾领出♠?", svc._our_side_led_suit(st, "♠"))
print("联手♠现手:", sorted(svc._FINESSE_R2V[c.rank] for c in SOUTH + NORTH if c.suit == "♠"))
print("可飞性(_probe_struct_playable):", svc._probe_struct_playable(st, "♠", 13))

forced = svc._finesse_commit_check(st, {"♠": {"对象": 13}})
print("威胁比较制 forced =", forced)

# 完整接应执行（传同一 fs，不再内部二次检测；引牌必胜豁免比值退让）
fs_repro = {"♠": {"对象": 13, "说明": "flow补构", "来源": "flow"}}
result = {
    "card": Card("♠", "A"), "reasoning": "",
    "full_output": {"mcts_stats": {"candidates": [
        {"card": "♠A", "scoring_val": 0.561, "avg_tricks": 11.56},
        {"card": "♠8", "scoring_val": 0.439, "avg_tricks": 11.44},
    ]}},
}
result, committed = svc._apply_finesse_commit(st, result, fs_repro, 0.95)
fo = result.get("full_output", {})
print("committed =", committed, "| 最终出牌 =", result.get("card"))
print("飞牌接应字段:", fo.get("飞牌接应"))
print("DONE")