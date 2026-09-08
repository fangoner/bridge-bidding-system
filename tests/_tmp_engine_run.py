import random
import sys

sys.path.insert(0, r"d:\Bridge Card\Bidding System")

from bridge.play_service import PlayService
from bridge.play_types import PlayerRole, PlayPhase, Card

# 用户 6NT 例（南坐庄，西首攻？未知，用 seed 固定）
# 南：♠AK32 ♥K32 ♦432 ♣KQJ   北：♠54 ♥AQJ ♦AQT987 ♣A2
SOUTH = {"♠": "AK32", "♥": "K32", "♦": "432", "♣": "KQJ"}
NORTH = {"♠": "54", "♥": "AQJ", "♦": "AQT987", "♣": "A2"}
RANKS = "AKQJT98765432"
SUITS = "♠♥♦♣"
CONTRACT = "6NT"
DECLARER = "南"
LEAD = None


def build_pool():
    known = set()
    for suit, ranks in SOUTH.items():
        for r in ranks:
            known.add(suit + r)
    for suit, ranks in NORTH.items():
        for r in ranks:
            known.add(suit + r)
    return [s + r for s in SUITS for r in RANKS if s + r not in known]


def deal_ew(seed, lead=None):
    random.seed(seed)
    while True:
        pool = build_pool()
        random.shuffle(pool)
        west = pool[:13]
        east = pool[13:]
        if lead is None:
            return west, east
        if lead in west:
            return west, east


def hands_of(west, east):
    sym = {"s": "♠", "h": "♥", "d": "♦", "c": "♣"}
    h = {"南": {}, "北": {}, "西": {}, "东": {}}
    for pos, by_suit in (("南", SOUTH), ("北", NORTH)):
        for s, ranks in by_suit.items():
            key = {"♠": "spades", "♥": "hearts", "♦": "diamonds", "♣": "clubs"}[s]
            h[pos][key] = ranks
    for pos, arr in (("西", west), ("东", east)):
        by = {}
        for cs in arr:
            by.setdefault(sym.get(cs[0], cs[0]), []).append(cs[1:])
        keymap = {"♠": "spades", "♥": "hearts", "♦": "diamonds", "♣": "clubs"}
        h[pos] = {keymap[s]: "".join(sorted(rs, key=lambda r: -RANKS.index(r)))
                  for s, rs in by.items()}
        for s in "♠♥♦♣":
            h[pos].setdefault(keymap[s], "")
    return h


def fmt_hand(lst):
    by = {}
    for c in lst:
        by.setdefault(c.suit, []).append(c.rank)
    return " ".join(f"{s}{''.join(r for r in sorted(by.get(s, []), key=lambda x: -RANKS.index(x)))}"
                    for s in SUITS if by.get(s))


def main(seed=42, samples=100):
    west, east = deal_ew(seed, LEAD)
    hands = hands_of(west, east)
    keymap = {"♠": "spades", "♥": "hearts", "♦": "diamonds", "♣": "clubs"}
    print("=== 真实 DD 引擎出牌路径 ===")
    for p in ("南", "北", "西", "东"):
        parts = []
        for suit in "♠♥♦♣":
            rs = hands[p].get(keymap[suit], "")
            if rs:
                parts.append(suit + rs)
        print(f"{p}: {' '.join(parts)}")
    print(f"定约 {CONTRACT} {DECLARER}坐庄，西首攻{LEAD}\n")

    roles = {p: PlayerRole.AI.value for p in ("南", "北", "东", "西")}
    svc = PlayService(None)
    svc.initialize(hands, CONTRACT, DECLARER, player_roles=roles)

    step = 0
    first_lead = True
    while step < 60:
        st = svc.engine.get_state()
        if st.phase == PlayPhase.COMPLETE:
            break
        cp = st.current_player
        pl = svc.engine.get_playable_cards(cp)
        if not pl:
            break

        if first_lead and cp == "西" and LEAD:
            svc.play_card("西", Card(LEAD[0], LEAD[1:]))
            print(f"首攻: 西 {LEAD}")
            first_lead = False
            step += 1
            continue

        res = svc._dd_play(st, dd_samples=samples)
        card_d = res.get("card")
        if card_d is None:
            card_d = pl[0].to_dict()
            print(f"[异常] {cp} 无决策，fallback {card_d}")
        c = Card(card_d["suit"], card_d["rank"])
        ok, msg = svc.play_card(cp, c, True)
        if not ok:
            print(f"[失败] {cp} 出 {c}: {msg}")
            break

        fo = res.get("full_output") or {}
        lead_fly = fo.get("领出飞牌")
        flow = fo.get("飞牌流程")
        probe = fo.get("finesse_probe")
        lead_txt = ""
        if lead_fly:
            lead_txt = f"｜领出飞牌:{lead_fly}"
        flow_txt = ""
        if flow:
            flow_txt = f"｜流程:{flow}"
        probe_txt = f"｜probe:{probe}" if probe else ""
        print(f"#{step} {cp} 出 {c}{lead_txt}{flow_txt}{probe_txt}")
        step += 1

    st = svc.engine.get_state()
    print(f"\n结果: 庄家方 {st.declarer_tricks} 墩 / 需 {st.contract.tricks_needed} 墩 —— "
          + ("做成" if st.declarer_tricks >= st.contract.tricks_needed else "宕"))


if __name__ == "__main__":
    seed = int(sys.argv[1]) if len(sys.argv) > 1 else 42
    samples = int(sys.argv[2]) if len(sys.argv) > 2 else 100
    main(seed, samples)