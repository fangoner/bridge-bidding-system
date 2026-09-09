import sys

sys.path.insert(0, r"d:\Bridge Card\Bidding System")

from bridge.play_service import PlayService
from bridge.play_types import PlayerRole, Card

roles = {p: PlayerRole.AI.value for p in ("南", "北", "东", "西")}
svc = PlayService(None)

# 第6墩局面（每家在手8张）：南 ♠A8 + 6 张其它；北领出 ♠4 后
 
def mk(cards_str):
    return [Card(c[0], c[1:]) for c in cards_str.split()]

SOUTH = mk("♠A ♠8 ♥5 ♥4 ♥3 ♦6 ♦5 ♣2")
NORTH = mk("♠2 ♠4 ♥7 ♥6 ♦4 ♦3 ♣8 ♣7")

st = svc.initialize({"南": {}, "北": {}}, "4♠", "南", player_roles=roles)
st.hands["南"] = SOUTH
st.hands["北"] = NORTH
# 本墩：北领出 ♠4，东跟 ♠2，轮到南（第三家）
st.current_player = "南"
st.current_trick.leader = "北"
st.current_trick.cards = [("北", Card("♠", "4")), ("东", Card("♠", "2"))]
st.finesse_flow["♠"] = 13  # 飞K流程进行中

forced = svc._finesse_commit_check(st, {"♠": {"对象": 13, "来源": "flow"}})
print("forced =", forced)
print("南现手♠ rank:", sorted(svc._FINESSE_R2V[c.rank] for c in SOUTH if c.suit == "♠"))
print("北现手♠ rank（除本墩♠4）:", sorted(svc._FINESSE_R2V[c.rank] for c in NORTH if c.suit == "♠"))
# 可飞性校验（结构判定）：
from bridge.play_types import PlayState
print("_probe_struct_playable(♠,K) =", svc._probe_struct_playable(st, "♠", 13))
print("DONE")