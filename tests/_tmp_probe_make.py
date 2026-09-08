import random
import sys

sys.path.insert(0, r"d:\Bridge Card\Bidding System")

from bridge.play_service import PlayService
from bridge.play_types import PlayerRole, PlayPhase

ALL = "AKQJT98765432"

# 与之前一致的样本 —— 用户指定牌序"南西北东"，南坐庄 6NT，西首攻
# 东西未知：留空由 DD 采样器从剩余 26 张采样
hands = {
    "南": {"spades": "432", "hearts": "A32", "diamonds": "K32", "clubs": "AKQJ"},
    "北": {"spades": "AJ9", "hearts": "KQJ", "diamonds": "AQJ", "clubs": "5432"},
}
roles = {p: PlayerRole.AI.value for p in ("南", "北", "东", "西")}
svc = PlayService(None)
contract_str = "6NT" if "--6nt" in sys.argv else "3NT"
state = svc.initialize(hands, contract_str, "南", player_roles=roles)
needed = state.contract.tricks_needed
print(f"定约 {contract_str}, 需要 {needed} 墩")

# 推进到我方领出（真实时点，固定 seed 可复现）
random.seed(7)
engine = svc.engine
steps = 0
while steps < 40:
    st = engine.get_state()
    if st.phase == PlayPhase.COMPLETE or len(st.tricks) >= 6:
        break
    cp = st.current_player
    pl = engine.get_playable_cards(cp)
    if not pl:
        break
    if (not st.current_trick.cards) and cp in {"南", "北"}:
        break
    engine.play_card(cp, random.choice(pl))
    steps += 1
st2 = engine.get_state()
print(f"触发时点: 当前方={st2.current_player} 已打{len(st2.tricks)}墩 "
      f"({', '.join(f'{p}:{c.suit}{c.rank}' for p, c in st2.current_trick.cards)})\n")

from bridge.mcts import dd_search

orig_final = dd_search._finalize_finesse_probe


def make_rate(lst):
    if not lst:
        return None
    return round(100.0 * sum(1 for t in lst if t >= needed) / len(lst), 1)


def debug_final(probe):
    for suit, by_m in probe.items():
        for m, sides in by_m.items():
            east = sides.get("东") or {}
            west = sides.get("西") or {}
            print(f"── 花色 {suit} 对象 {m} ──")
            for card_str in sorted(set(east) | set(west), key=lambda s: -ALL.index(s[1:])):
                ev = east.get(card_str) or []
                wv = west.get(card_str) or []
                em = make_rate(ev)
                wm = make_rate(wv)
                es = f"E: 做成率{em}%（{len(ev)}世界）" if em is not None else "E: 无数据"
                ws = f"W: 做成率{wm}%（{len(wv)}世界）" if wm is not None else "W: 无数据"
                print(f"    打 {card_str}: {es} ｜ {ws}")
    return orig_final(probe)


dd_search._finalize_finesse_probe = debug_final
dd_search._dd_config.FINESSE_PROBE_DELTA = 0.0
try:
    res = svc._dd_play(st2, dd_samples=200)
    c = res.get("card")
    print(f"\n引擎首选: {c['suit'] + c['rank'] if c else '?'}")
    probe = (res.get("full_output", {}).get("finesse_probe") or {})
    for s, v in probe.items():
        print(f"finalize后: {s} 对象={v.get('对象')} Δ={v.get('Δ')} 引牌={v.get('引牌')}")
finally:
    dd_search._finalize_finesse_probe = orig_final
    dd_search._dd_config.FINESSE_PROBE_DELTA = 0.4