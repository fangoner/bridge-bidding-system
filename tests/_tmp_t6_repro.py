import sys

sys.path.insert(0, r"d:\Bridge Card\Bidding System")

from bridge.play_service import PlayService
from bridge.play_types import PlayerRole, Card, Trick

roles = {p: PlayerRole.AI.value for p in ("南", "北", "东", "西")}
svc = PlayService(None)
svc.dd_search.num_samples = 60
svc.dd_search.min_samples = 20
svc.dd_search.time_limit = 20.0


def mk(cards):
    """cards: [('♠','A'), ...] → [Card, ...]"""
    return [Card(s, r) for s, r in cards]


SOUTH = mk([("♠", "A"), ("♠", "J"), ("♠", "T"), ("♠", "9"), ("♠", "8"),
            ("♥", "T"), ("♦", "A"), ("♦", "Q"), ("♦", "2"),
            ("♣", "A"), ("♣", "Q"), ("♣", "J"), ("♣", "T")])
NORTH = mk([("♠", "5"), ("♠", "4"), ("♠", "3"), ("♠", "2"),
            ("♥", "3"), ("♥", "2"), ("♦", "K"), ("♦", "J"), ("♦", "T"), ("♦", "9"),
            ("♣", "K"), ("♣", "3"), ("♣", "2")])

st = svc.initialize({"南": {}, "北": {}}, "6♠", "南", player_roles=roles)
st.hands["南"] = SOUTH
st.hands["北"] = NORTH

# 第1墩：西首攻 ♥K — 北♥3 — 东♥7 — 南♠J 将吃
t1 = Trick(trump="♠")
for p, c in [("西", Card("♥", "K")), ("北", Card("♥", "3")),
             ("东", Card("♥", "7")), ("南", Card("♠", "J"))]:
    t1.cards.append((p, c))
st.tricks = [t1]
st.current_trick = Trick(trump="♠")  # 第2墩，南领出
st.current_player = "南"
st.declarer_tricks = 1
st.defender_tricks = 0
st.phase = "playing"

import config as _cfg
print("DD_FINESSE_ENABLE =", getattr(_cfg, "DD_FINESSE_ENABLE", "N/A(旧版)"))

r = svc._dd_play(st, None, None)
fo = r.get("full_output") or {}
print("推荐出牌:", r.get("card"))
print("finesse_probe:", fo.get("finesse_probe"))
for k in ("领出飞牌", "领出过手", "飞牌续", "窗口期启动"):
    if fo.get(k):
        print(f"{k}:", fo.get(k))
print("DONE")