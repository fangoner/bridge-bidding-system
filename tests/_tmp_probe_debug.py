import sys

sys.path.insert(0, r"d:\Bridge Card\Bidding System")

from bridge.play_service import PlayService
from bridge.play_types import PlayerRole, Card
import tests._tmp_engine_run as T

west, east = T.deal_ew(42, T.LEAD)
hands = T.hands_of(west, east)
print("西:", T.fmt_hand([Card(c[0], c[1:]) for c in west]))
print("东:", T.fmt_hand([Card(c[0], c[1:]) for c in east]))

roles = {p: PlayerRole.AI.value for p in ("南", "北", "东", "西")}
svc = PlayService(None)
svc.initialize(hands, T.CONTRACT, T.DECLARER, player_roles=roles)

svc.play_card("西", Card("♥", "K"))
svc.play_card("北", Card("♥", "3"))
svc.play_card("东", Card("♥", "4"))
svc.play_card("南", Card("♠", "J"))

for name in range(8):
    st = svc.engine.get_state()
    cp = st.current_player
    res = svc._dd_play(st, dd_samples=100)
    fo = res.get("full_output") or {}
    probe = fo.get("finesse_probe")
    cands = (fo.get("mcts_stats") or {}).get("candidates") or []
    cards = [c.get("card") for c in cands][:8]
    print(f"#{name} {cp} 候选={cards}")
    print(f"   lead_fly={fo.get('领出飞牌')}")
    p3 = fo.get("finesse_probe_raw") or probe
    print(f"   probe={probe if probe else '空'}")
    cd = res["card"]
    c = Card(cd["suit"], cd["rank"])
    svc.play_card(cp, c, True)