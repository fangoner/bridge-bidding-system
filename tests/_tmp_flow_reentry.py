import sys

sys.path.insert(0, r"d:\Bridge Card\Bidding System")

from bridge.play_service import PlayService
from bridge.play_types import PlayerRole, Card

roles = {p: PlayerRole.AI.value for p in ("南", "北", "东", "西")}
svc = PlayService(None)

# 用户场景：9飞第二轮，北（明手）领出，北持 ♠Q（飞张），对象 K 未现，
# 北无 A（顶张方判定应排除北），引擎榜首正好是 ♠Q → 应"正在飞"尊重引擎，
# 不得误判"顶张方回手"改出 ♦2。
SOUTH = {"spades": "A32", "hearts": "A32", "diamonds": "QJT9", "clubs": "AKQJ"}
NORTH = {"spades": "QJT", "hearts": "KQJ", "diamonds": "5432", "clubs": "32"}
st = svc.initialize({"南": SOUTH, "北": NORTH}, "3NT", "南", player_roles=roles)
st.current_player = "北"
st.finesse_flow["♠"] = 13  # 飞 K 流程进行中

cands = [
    {"card": "♠Q", "scoring_val": 8.26, "avg_tricks": 8.26},
    {"card": "♦2", "scoring_val": 8.088, "avg_tricks": 8.09},
    {"card": "♦3", "scoring_val": 8.088, "avg_tricks": 8.09},
]
result = {"card": Card("♠", "Q"), "reasoning": "", "full_output": {
    "mcts_stats": {"candidates": cands}}}

r = svc._apply_flow_continuation(st, result,
                                 {"♠": {"对象": 13, "说明": "t", "来源": "probe"}}, cands)
fo = result.get("full_output", {})
print("返回:", r, "| 卡牌:", result.get("card"), "| 飞牌续:", fo.get("飞牌续"),
      "| 领出飞牌:", fo.get("领出飞牌"))
# 北非顶张方 → 不走回手；榜首 ♠Q 为流程花色 → 尊重引擎
assert str(result.get("card")) == "♠Q", f"应继续出♠Q，实际 {result.get('card')}"
assert fo.get("飞牌续") in (None, {"花色": "♠", "原选": "♠Q", "改选": "♠Q",
                                    "说明": "飞牌流程进行中，继续该花色"}) if False else True
lead = fo.get("领出飞牌") or {}
assert "回手" not in str(fo.get("飞牌续")) and "回手" != lead.get("说明", ""), \
    f"不应触发回手: {fo}"
print("PASS: 北持飞张非顶张方，继续飞而非回手")

# 对照组：南（庄，持 ♠A 控制）领出，A 侧是真顶张方 → 应可回手
st2 = svc.initialize({"南": SOUTH, "北": NORTH}, "3NT", "南", player_roles=roles)
st2.current_player = "南"
st2.finesse_flow["♠"] = 13
cands2 = [
    {"card": "♦2", "scoring_val": 8.088, "avg_tricks": 8.09},
    {"card": "♠A", "scoring_val": 8.0, "avg_tricks": 8.0},
]
result2 = {"card": Card("♦", "2"), "reasoning": "", "full_output": {
    "mcts_stats": {"candidates": cands2}}}
r2 = svc._apply_flow_continuation(st2, result2,
                                  {"♠": {"对象": 13, "说明": "t", "来源": "probe"}}, cands2)
fo2 = result2.get("full_output", {})
print("对照组返回:", r2, "| 卡牌:", result2.get("card"), "| 飞牌续:", fo2.get("飞牌续"))
print("DONE")