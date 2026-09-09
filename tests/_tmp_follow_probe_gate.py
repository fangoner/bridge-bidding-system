import sys

sys.path.insert(0, r"d:\Bridge Card\Bidding System")

from bridge.play_service import PlayService
from bridge.play_types import PlayerRole, Card

roles = {p: PlayerRole.AI.value for p in ("南", "北", "东", "西")}
svc = PlayService(None)
svc.dd_search.num_samples = 64
svc.dd_search.time_limit = 8.0

# 用户场景：南领出 ♠7 飞 Q，西家出 ♠Q 盖住，北家（明手）第三家跟牌，
# 手中 ♠J2 应放小 ♠2；旧代码在跟牌时探测到"飞T"（Q 一出滑窗下移），
# 强制北家出 ♠J 盖 T——这是错误的。
st = svc.initialize(
    {"南": {"spades": "K987"},
     "北": {"spades": "J2"}}, "6S", "南", player_roles=roles)
st.current_player = "北"
st.current_trick.cards = [("南", Card("♠", "7")), ("西", Card("♠", "Q"))]

res = svc.dd_search.search(st)
fo = res.get("full_output") or {}
probe = fo.get("finesse_probe") or {}
print("跟牌时 finesse_probe:", probe)
assert not probe, f"跟牌时不应探测，实际 {probe}"

from bridge.play_service import FINESSE_RATIO
res2 = svc._apply_finesse_tactics(st, res, FINESSE_RATIO)
inner = res2.get("full_output") or {}
print("跟牌决策:", res2.get("card"), "| 飞牌接应:", inner.get("飞牌接应"))
assert inner.get("飞牌接应") is None, f"跟牌时不应有飞牌接应，实际 {inner.get('飞牌接应')}"

print("\nPASS: 跟牌时探针不触发、无强制接应，尊重引擎")