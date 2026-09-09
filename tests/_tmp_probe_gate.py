import sys

sys.path.insert(0, r"d:\Bridge Card\Bidding System")

from bridge.play_service import PlayService
from bridge.play_types import PlayerRole, Card

roles = {p: PlayerRole.AI.value for p in ("南", "北", "东", "西")}
svc = PlayService(None)
svc.dd_search.num_samples = 15
svc.dd_search.min_samples = 5
svc.dd_search.time_limit = 8.0

SOUTH = {"spades": "AT93", "hearts": "A43", "diamonds": "A62", "clubs": "KJ4"}
NORTH = {"spades": "QJ74", "hearts": "K92", "diamonds": "K53", "clubs": "QT32"}

st = svc.initialize({"南": SOUTH, "北": NORTH}, "3NT", "南", player_roles=roles)

st.current_player = "北"
st.current_trick.leader = "西"
st.current_trick.cards.append(("西", Card("♠", "5")))
r = svc.dd_search.search(st)
pb = r["full_output"].get("finesse_probe")
print("场景B(西领出♠,北跟牌) finesse_probe:", pb)
assert pb == {}, f"对方领出不应探测，实际 {pb}"

st2 = svc.initialize({"南": SOUTH, "北": NORTH}, "3NT", "南", player_roles=roles)
st2.current_player = "北"
r2 = svc.dd_search.search(st2)
pb2 = r2["full_output"].get("finesse_probe")
print("场景A(北领出) finesse_probe:", pb2)
assert isinstance(pb2, dict) and pb2 != {}, f"我方领出应可探测到结构，实际 {pb2}"
print("PASS")