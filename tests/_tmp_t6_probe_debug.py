import sys

sys.path.insert(0, r"d:\Bridge Card\Bidding System")

from bridge.play_service import PlayService
from bridge.play_types import PlayerRole, Card, Trick
from bridge.mcts.dd_search import _honor_missing_of_state

roles = {p: PlayerRole.AI.value for p in ("南", "北", "东", "西")}
svc = PlayService(None)
svc.dd_search.num_samples = 324
svc.dd_search.min_samples = 100
svc.dd_search.time_limit = 30.0


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
t1 = Trick(trump="♠")
for p, c in [("西", Card("♥", "K")), ("北", Card("♥", "3")),
             ("东", Card("♥", "7")), ("南", Card("♠", "J"))]:
    t1.cards.append((p, c))
st.tricks = [t1]
st.current_trick = Trick(trump="♠")
st.current_player = "南"
st.declarer_tricks = 1
st.defender_tricks = 0

print("declarer:", st.contract.declarer, "| dummy:", st.dummy, "| current_player:", st.current_player)
print("current_trick.cards:", st.current_trick.cards)
print("honor_missing:", {s: m for s, m in _honor_missing_of_state(st).items()})

rs = svc.dd_search.search(st)
fo = rs.get("full_output") or {}
print("当前侧 search probe:", fo.get("finesse_probe"))

rs2 = svc.dd_search.search(st, perspective="北", actual_turn="北")
fo2 = rs2.get("full_output") or {}
print("队友侧 search probe:", fo2.get("finesse_probe"))
print("DONE")