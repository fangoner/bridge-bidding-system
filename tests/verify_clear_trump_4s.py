import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from bridge.play_types import Card, Contract, Trick, PlayState, PlayPhase
from bridge.play_service import PlayService


hands = {
    "北": [Card("♠", "J"), Card("♠", "3"),
           Card("♥", "A"), Card("♥", "4"),
           Card("♦", "A"), Card("♦", "K"), Card("♦", "5"),
           Card("♦", "4"), Card("♦", "3"),
           Card("♣", "A"), Card("♣", "7"), Card("♣", "6"), Card("♣", "5")],
    "南": [Card("♠", "K"), Card("♠", "Q"), Card("♠", "T"), Card("♠", "9"),
           Card("♠", "8"), Card("♠", "7"),
           Card("♥", "3"), Card("♥", "2"),
           Card("♦", "2"),
           Card("♣", "K"), Card("♣", "4"), Card("♣", "3"), Card("♣", "2")],
    "东": [Card("♠", "A"), Card("♠", "6"), Card("♠", "5"), Card("♠", "4"),
           Card("♠", "2"), Card("♥", "J"), Card("♥", "10"), Card("♥", "9"),
           Card("♥", "8"), Card("♥", "7"), Card("♥", "6"), Card("♥", "5"),
           Card("♦", "9")],
    "西": [Card("♥", "K"), Card("♥", "Q"), Card("♣", "Q"), Card("♣", "J"),
           Card("♣", "10"), Card("♣", "9"), Card("♣", "8"), Card("♦", "J"),
           Card("♦", "10"), Card("♦", "8"), Card("♦", "7"), Card("♦", "6"),
           Card("♣", "6")],
}


def mc(card, scores):
    n = len(scores)
    return {"card": card, "scores": scores,
            "make_rate_val": sum(1 for x in scores if x >= 10) / n}


def run_4s(cands, probe_delta):
    result = {"card": Card("♦", "A"), "reasoning": "engine",
              "full_output": {"mcts_stats": {"candidates": cands},
                              "finesse_probe": {"♠": {"Δ": probe_delta}}}}
    svc = PlayService(llm_client=None)
    svc.dd_search.last_worlds = []
    state = PlayState(contract=Contract(level=4, suit="♠", declarer="南"),
                      hands={p: list(cs) for p, cs in hands.items()})
    state.current_trick = Trick(trump="♠")
    state.current_player = "北"
    state.phase = PlayPhase.PLAYING
    state.declarer_tricks = 0
    state.defender_tricks = 0
    return svc._intervene(state, result, 0.75)


def main():
    n = 200
    all10 = [10] * n
    top99 = [10] * (n - 2) + [9, 9]
    alt995 = [10] * (n - 1) + [9]
    bad_trump = [10] * (n - 3) + [9, 9, 9]
    c4s = [mc("♦A", top99), mc("♦K", alt995), mc("♠3", all10), mc("♠8", all10)]

    out = run_4s(c4s, 0.02)
    assert str(out.get("card")) == "♠3", out.get("card")
    assert out.get("full_output", {}).get("无损清将")
    print("CASE1 触发清将♠3 PASS")

    out = run_4s([mc("♦A", all10), mc("♦K", all10), mc("♠3", all10), mc("♠8", all10)], 0.02)
    assert str(out.get("card")) == "♦A", out.get("card")
    assert "无损清将" not in out.get("full_output", {})
    print("CASE2 100%稳成退让 PASS")

    out = run_4s([mc("♦A", all10), mc("♦K", all10), mc("♠3", bad_trump), mc("♠8", bad_trump)], 0.02)
    assert str(out.get("card")) == "♦A", out.get("card")
    assert "无损清将" not in out.get("full_output", {})
    print("CASE3 逐世界 diff<0 退让 PASS")

    out = run_4s(c4s, 0.20)
    assert str(out.get("card")) == "♦A", out.get("card")
    assert "无损清将" not in out.get("full_output", {})
    print("CASE4 将牌飞角型(Δ达标)交飞牌层 PASS")

    print("ALL 4 CHECKS PASS")


if __name__ == "__main__":
    main()