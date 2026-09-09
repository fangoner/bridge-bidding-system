import sys

sys.path.insert(0, r"d:\Bridge Card\Bidding System")

import config
from bridge.play_service import PlayService
from bridge.play_types import PlayerRole

roles = {p: PlayerRole.AI.value for p in ("南", "北", "东", "西")}
svc = PlayService(None)
svc.dd_search.num_samples = 40
svc.dd_search.min_samples = 15
svc.dd_search.time_limit = 15.0

SOUTH = {"spades": "AT93", "hearts": "A43", "diamonds": "A62", "clubs": "KJ4"}
NORTH = {"spades": "QJ74", "hearts": "K92", "diamonds": "K53", "clubs": "QT32"}


def run_case(tag):
    st = svc.initialize({"南": SOUTH, "北": NORTH}, "3NT", "南", player_roles=roles)
    st.current_player = "北"
    r = svc._dd_play(st, None, None)
    fo = r.get("full_output") or {}
    finesse_keys = [k for k in fo if any(t in k for t in ("飞牌", "probe"))]
    print(f"===== {tag} =====")
    print("推荐出牌:", r.get("card"))
    print("finesse_probe:", fo.get("finesse_probe"))
    print("飞牌相关字段:", {k: fo.get(k) for k in finesse_keys})
    print()


config.DD_FINESSE_ENABLE = False
run_case("开关=关 (DD_FINESSE_ENABLE=False)")

config.DD_FINESSE_ENABLE = True
run_case("开关=开 (DD_FINESSE_ENABLE=True)")

config.DD_FINESSE_ENABLE = True
print("DONE")