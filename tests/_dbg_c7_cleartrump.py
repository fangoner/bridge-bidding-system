"""C7 live 精确复现（第2墩北领出, 第1墩已打完 + 叫牌约束）：
为什么 live 下段2 无损清将退让、引擎出 ♦A？

对比无约束复现（diff 全≥0、返回 ♠3）——验证约束/已打牌是否让 逐世界 diff 出现负数。
"""

import os
import sys
from collections import Counter

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from bridge.play_types import Card, Contract, Trick, PlayState, PlayPhase, POSITION_ORDER
from bridge.play_service import PlayService, _CLEAR_TRUMP_EPS
from bridge.mcts.constraints import BidConstraint
from config import FINESSE_PROBE_DELTA, DD_NUM_SAMPLES

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


def build_state(play_trick1: bool, constraints: bool):
    svc = PlayService(llm_client=None)
    svc.dd_search.num_samples = DD_NUM_SAMPLES
    state = PlayState(contract=Contract(level=4, suit="♠", declarer="南"),
                      hands={p: list(cs) for p, cs in hands.items()})
    state.current_trick = Trick(trump="♠")
    state.current_player = "北"
    state.phase = PlayPhase.PLAYING
    state.declarer_tricks = 0
    state.defender_tricks = 0
    if play_trick1:
        played = [("西", Card("♥", "K")), ("北", Card("♥", "A")),
                  ("东", Card("♥", "5")), ("南", Card("♥", "3"))]
        for pos, card in played:
            state.hands[pos].remove(card)
        state.tricks.append(Trick(trump="♠", cards=played, leader="西"))
        state.current_trick = Trick(trump="♠")
        state.current_player = "北"
        state.declarer_tricks = 1
    if constraints:
        svc.dd_search.sampler.constraints = {
            "南": BidConstraint(position="南", min_hcp=6, max_hcp=10,
                                suit_min={"♠": 6}, inference_source="meaning_parsed"),
            "北": BidConstraint(position="北", min_hcp=16, max_hcp=19,
                                balanced=True, suit_min={"♠": 2},
                                inference_source="meaning_parsed"),
        }
    else:
        svc.dd_search.sampler.constraints = {}
    return svc, state


def run(svc, state, tag):
    print("\n" + "=" * 78)
    print(f"[{tag}]")
    result = svc.dd_search.search(state)
    full = result.get("full_output") or {}
    cands = (full.get("mcts_stats") or {}).get("candidates") or []
    need = state.contract.tricks_needed
    print(f"引擎已选: {result.get('card')}  candidates={len(cands)}")
    for c in cands[:8]:
        sc = c.get("scores") or []
        mr = (sum(1 for x in sc if x >= need) / len(sc)) if sc else 0.0
        print(f"  {str(c['card']):>4}  {len(sc)}世界 make={mr:.4f} "
              f"avg={sum(sc)/len(sc):.2f}")
    with_sc = [c for c in cands if c.get("scores")]
    rates = [sum(1 for x in c["scores"] if x >= need) / len(c["scores"])
             for c in with_sc[:4]]
    print(f"门A top4极差={max(rates)-min(rates):.4f} "
          f"(过<=0.03: {max(rates)-min(rates) <= _CLEAR_TRUMP_EPS})")
    probe = full.get("finesse_probe") or {}
    t_info = probe.get("♠") or {}
    delta = t_info.get("Δ") or 0
    print(f"门B ♠Δ={delta:.3f} (过<0.10: {delta < FINESSE_PROBE_DELTA})")
    r2v = svc._FINESSE_R2V
    trump_cards = [c for c in cands if str(c["card"])[0] == "♠"]
    if trump_cards:
        clear = min(trump_cards, key=lambda c: r2v.get(str(c["card"])[1:], 0))
        base = next((c for c in cands if str(c["card"])[0] != "♠"), None)
        if base and clear.get("scores"):
            d = [a - b for a, b in zip(clear["scores"], base["scores"])]
            neg = [x for x in d if x < 0]
            print(f"清将={clear['card']} vs 基准={base['card']}: "
                  f"min={min(d)} max={max(d)} 负世界={len(neg)}({len(neg)/len(d)*100:.1f}%) "
                  f"分布={dict(sorted(Counter(d).items()))}")
    cur = result.get("card")
    if trump_cards and cur is not None:
        print(f"引擎牌==清将牌? {str(cur) == str(clear['card'])}")
    out = svc._intervene(state, result, 0.75)
    fo = out.get("full_output", {})
    print(f"最终选牌: {out.get('card')}  清将注记: {fo.get('无损清将')}  "
          f"领出飞牌: {fo.get('领出飞牌')}")


if __name__ == "__main__":
    run(*build_state(False, False), "无约束·无第1墩")
    run(*build_state(True, False), "有第1墩·无约束")
    run(*build_state(False, True), "无第1墩·有约束")
    run(*build_state(True, True), "有第1墩·有约束 (live精确)")