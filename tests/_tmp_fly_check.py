import sys

sys.path.insert(0, r"d:\Bridge Card\Bidding System")

from bridge.play_service import PlayService
from bridge.play_types import PlayerRole

SOUTH = {"spades": "AK32", "hearts": "K32", "diamonds": "432", "clubs": "KQJ"}
NORTH = {"spades": "54", "hearts": "AQJ", "diamonds": "AQT987", "clubs": "A2"}
roles = {p: PlayerRole.AI.value for p in ("南", "北", "东", "西")}
svc = PlayService(None)
state = svc.initialize({"南": SOUTH, "北": NORTH}, "6NT", "南", player_roles=roles)

# 模拟探针报 ♠(T) 与 ♦(J)（探针对象是字符 'T'/'J'）
fake_result = {"full_output": {"finesse_probe": {"♠": {"对象": "T", "Δ": 0.40, "引牌": "♠3"},
                                                  "♦": {"对象": "J", "Δ": 0.55, "引牌": "♦2"}}}}
detected = svc._detect_finesse_struct(state, fake_result)
print("探测结果:", detected)
assert "♠" not in detected, "♠(T) 无间张应被可飞性校验排除"
assert "♦" in detected, "♦(J) 有 T 间张应保留"
print("PASS: ♠(T) 排除，♦(J) 保留")