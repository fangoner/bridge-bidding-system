"""复现：4♠ 南庄第4墩南领出（上一墩 ♠T 将吃回手），探针对象为何只有 J 无 K。"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from bridge.play_types import Card, Contract, Trick, PlayState, PlayPhase

# 原始 13 张（与实时牌局一致：西♥AKQ 已出、北♥432 已出、东♥J78 已出、南♥65+♠T 已出）
FULL = {
    "北": [("♠", "A"), ("♠", "2"), ("♥", "4"), ("♥", "3"), ("♥", "2"),
          ("♦", "J"), ("♦", "T"), ("♦", "9"),
          ("♣", "K"), ("♣", "5"), ("♣", "4"), ("♣", "3"), ("♣", "2")],
    "南": [("♠", "Q"), ("♠", "9"), ("♠", "8"), ("♠", "7"), ("♠", "6"),
          ("♠", "5"), ("♠", "T"), ("♥", "6"), ("♥", "5"),
          ("♦", "A"), ("♦", "K"), ("♦", "Q"), ("♣", "A")],
    "东": [("♠", "K"), ("♠", "4"), ("♠", "3"), ("♥", "T"), ("♥", "9"), ("♥", "J"), ("♥", "8"), ("♥", "7"),
          ("♦", "6"), ("♦", "5"), ("♦", "4"), ("♦", "3"), ("♦", "2")],
    "西": [("♠", "J"), ("♠", "T"), ("♥", "A"), ("♥", "K"), ("♥", "Q"),
          ("♦", "8"), ("♦", "7"),
          ("♣", "Q"), ("♣", "J"), ("♣", "T"), ("♣", "9"), ("♣", "8"), ("♣", "6")],
}
PLAYED = {
    "西": [("♥", "A"), ("♥", "K"), ("♥", "Q")],
    "北": [("♥", "4"), ("♥", "3"), ("♥", "2")],
    "东": [("♥", "J"), ("♥", "7"), ("♥", "8")],
    "南": [("♥", "6"), ("♥", "5"), ("♠", "T")],
}


def main():
    from bridge.play_service import PlayService
    from bridge.mcts.dd_search import _honor_missing_of_state

    hands = {p: [Card(s, r) for s, r in cs] for p, cs in FULL.items()}
    for pos, pl in PLAYED.items():
        for s, r in pl:
            hands[pos].remove(Card(s, r))

    state = PlayState(contract=Contract(level=4, suit="♠", declarer="南"), hands=hands)
    t1 = Trick(trump="♠", leader="西")
    for pos, card in [("西", Card("♥", "A")), ("北", Card("♥", "4")), ("东", Card("♥", "J")), ("南", Card("♥", "6"))]:
        t1.add_card(pos, card)
    t2 = Trick(trump="♠", leader="西")
    for pos, card in [("西", Card("♥", "K")), ("北", Card("♥", "3")), ("东", Card("♥", "7")), ("南", Card("♥", "5"))]:
        t2.add_card(pos, card)
    t3 = Trick(trump="♠", leader="西")
    for pos, card in [("西", Card("♥", "Q")), ("北", Card("♥", "2")), ("东", Card("♥", "8")), ("南", Card("♠", "T"))]:
        t3.add_card(pos, card)
    state.tricks = [t1, t2, t3]
    state.current_trick = Trick(trump="♠")
    state.current_player = "南"
    state.phase = PlayPhase.PLAYING
    state.declarer_tricks = 1
    state.defender_tricks = 2

    svc = PlayService(llm_client=None)
    from bridge.mcts.constraints import BidConstraint
    svc.dd_search.sampler.constraints = {
        "西": BidConstraint(position="西", min_hcp=15, max_hcp=17, balanced=True,
                            suit_max={"♠": 5, "♥": 5}, inference_source="meaning_parsed"),
        "东": BidConstraint(position="东", min_hcp=0, suit_min={"♥": 5},
                            inference_source="meaning_parsed"),
    }
    svc.dd_search.sampler.use_played_reduction = True
    win = _honor_missing_of_state(state)
    print(f"窗口 missing = {win}")
    print(f"南现手♠ = {[c for c in state.hands['南'] if c.suit=='♠']}")
    print(f"北现手♠ = {[c for c in state.hands['北'] if c.suit=='♠']}")

    result = svc.dd_search.search(state)
    full = result.get("full_output") or {}
    probe = full.get("finesse_probe") or {}
    import json
    print("PROBE_JSON_START")
    print(json.dumps(probe, ensure_ascii=False, indent=1)[:2400])
    print("PROBE_JSON_END")
    print(f"引擎选牌 = {result.get('card')}")
    out = svc._intervene(state, result, 0.75)
    fo = out.get("full_output") or {}
    print(f"_intervene → {out.get('card')}")
    print(f"  领出飞牌 = {fo.get('领出飞牌')}")
    print(f"  无损清将 = {fo.get('无损清将')}")


if __name__ == "__main__":
    main()