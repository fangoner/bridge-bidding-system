import sys

sys.path.insert(0, r"d:\Bridge Card\Bidding System")

from bridge.play_service import PlayService
from bridge.play_types import PlayerRole, Card
from bridge.mcts.dd_search import _honor_missing_of_state

SOUTH = {"spades": "AK32", "hearts": "K32", "diamonds": "432", "clubs": "KQJ"}
NORTH = {"spades": "54", "hearts": "AQJ", "diamonds": "AQT987", "clubs": "A2"}
roles = {p: PlayerRole.AI.value for p in ("南", "北", "东", "西")}
svc = PlayService(None)
state = svc.initialize({"南": SOUTH, "北": NORTH}, "6NT", "南", player_roles=roles)

m = _honor_missing_of_state(state)
print("无流程 missing:", m)
assert m.get("♠") == ["Q"], "♠ 应只监控 AKQ 窗口内的缺 Q"
assert m.get("♦") == ["K"], "♦ 应只监控 AKQ 窗口内的缺 K"
assert "♥" not in m and "♣" not in m, "♥/♣ 顶三张齐全不监控"

# 模拟 ♦ 飞牌流程进行中（对象 K），K 尚未现
state.finesse_flow["♦"] = 13
m2 = _honor_missing_of_state(state)
print("♦流程中(K未现) missing:", m2.get("♦"))
assert m2.get("♦") == ["K"], "飞牌花色 K 未现 → 仍监控 K"

# 模拟 K 已现身（被打出）：窗口应下滑为 AQJ，监控 J
state.tricks.append(type(state.tricks[0] if state.tricks else state.current_trick)(
    cards=[("东", Card("♦", "K"))], leader="东", trump="NT"))
m3 = _honor_missing_of_state(state)
print("♦流程中(K已出) missing:", m3.get("♦"))
assert m3.get("♦") == ["J"], "K 出掉后窗口滑到 AQJ，监控 J"

# 非飞牌花色 ♠ 即使 Q 已出也不下移补 J/T
state.tricks.append(type(state.tricks[0])(
    cards=[("北", Card("♠", "Q"))], leader="北", trump="NT"))
m4 = _honor_missing_of_state(state)
print("♠Q已出 missing:", m4.get("♠"))
assert "♠" not in m4 or m4.get("♠") == [], "♠ 非飞牌花色 Q 出掉后不补位（无 J/T 监控）"

print("PASS: 滑动窗口逻辑正确")
