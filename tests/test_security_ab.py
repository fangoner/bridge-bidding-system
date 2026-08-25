"""残局（剩余≤4墩）下安全加权 vs 期望IMP 的 A/B 对照扫描。

对一副完整 52 张发牌，用状态机打到剩余 4 墩（庄家南进手），
对同一批实际残局世界，分别用 imp / security 打分全部候选出牌，
对比二者选牌是否不同。

关键：枚举 / 采样 + DDS 只做一次，两种模式在同一批 card_scores 上各自打分。
"""

import copy
import random
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from bridge.play_types import Contract, PlayState, Card, PlayerRole, POSITION_ORDER
from bridge.mcts.sampler import DealSampler
from bridge.mcts import dd_search as D

ORDER = ["北", "东", "南", "西"]
RV = {"2": 2, "3": 3, "4": 4, "5": 5, "6": 6, "7": 7, "8": 8,
      "9": 9, "T": 10, "J": 11, "Q": 12, "K": 13, "A": 14}


def mk_deck():
    deck = (["♠2", "♠3", "♠4", "♠5", "♠6", "♠7", "♠8", "♠9", "♠T", "♠J", "♠Q", "♠K", "♠A"]
            + ["♥2", "♥3", "♥4", "♥5", "♥6", "♥7", "♥8", "♥9", "♥T", "♥J", "♥Q", "♥K", "♥A"]
            + ["♦2", "♦3", "♦4", "♦5", "♦6", "♦7", "♦8", "♦9", "♦T", "♦J", "♦Q", "♦K", "♦A"]
            + ["♣2", "♣3", "♣4", "♣5", "♣6", "♣7", "♣8", "♣9", "♣T", "♣J", "♣Q", "♣K", "♣A"])
    random.shuffle(deck)
    return {ORDER[i]: deck[i * 13:(i + 1) * 13] for i in range(4)}


def lowest(hand, suit):
    pool = [c for c in hand if c.suit == suit] if suit else list(hand)
    if not pool:
        pool = list(hand)
    return min(pool, key=lambda c: RV[c.rank])


def build_to_endgame(seed):
    random.seed(seed)
    raw = mk_deck()
    hands = {p: [Card.from_str(c) for c in h] for p, h in raw.items()}
    ct = Contract(level=3, suit="NT", declarer="南")
    roles = {p: PlayerRole.AI.value for p in ORDER}
    roles["南"] = PlayerRole.HUMAN.value
    st = PlayState(contract=ct, hands=hands, player_roles=roles, vulnerability="NV")
    # 打到 9 墩完成（剩余 4 墩）——按完成墩计数器控制，而非牌张数
    while st.declarer_tricks + st.defender_tricks < 9:
        cur = st.current_player
        if not st.hands.get(cur):
            return None
        suit = st.current_trick.get_lead_suit() if st.current_trick.cards else None
        st.play_card(cur, lowest(st.hands[cur], suit))
    rem = 13 - (st.declarer_tricks + st.defender_tricks)
    if rem != 4 or st.current_player != "南":
        return None
    return st


def clone(st):
    s2 = PlayState(contract=Contract(level=3, suit="NT", declarer="南"),
                   hands={p: list(h) for p, h in st.hands.items()},
                   player_roles=st.player_roles, vulnerability="NV")
    s2.tricks = [copy.deepcopy(t) for t in st.tricks]
    s2.current_trick = copy.deepcopy(st.current_trick)
    s2.current_player = st.current_player
    s2.declarer_tricks = st.declarer_tricks
    s2.defender_tricks = st.defender_tricks
    s2.phase = st.phase
    return s2


def eval_modes(st):
    pers = "南"
    playable = st.get_playable_cards(pers)
    ts = D.get_current_trick_state(st)
    tc = ts["cards"]
    tl = ts.get("leader")
    ap = []
    for tr in st.tricks:
        ap.extend(tr.cards)
    ap.extend(tc)
    cs = {str(c): {"scores": [], "weighted_sum": 0.0, "total_weight": 0.0,
                   "mn": 99, "mx": -1} for c in playable}
    world_count = 0
    # 残局：优先精确枚举（等价于完备世界）；不可行则采样
    worlds = D.DDSearch()._enumerate_endgame_worlds(st, pers)
    if worlds:
        worlds = worlds[:500]  # 限量
    else:
        worlds = DealSampler().sample_n(80, st, pers)
    for i, world in enumerate(worlds):
        D._dd_eval_one_world(world, ap, tc, tl, playable, st, pers, pers,
                             st.contract.declarer, st.dummy, "NT", cs, 1.0, i + 1)
        world_count += 1
    need = st.contract.tricks_needed
    sl = [cs[str(c)]["scores"] for c in playable]
    nw = min((len(s) for s in sl), default=0)
    if nw < 8:
        return None
    # 临界掩码：硬过滤，只保留该 world 下所有候选可达墩最大值落在 [need-k, need+k]
    mask = D._critical_mask(sl, need, 1)
    crit_n = sum(mask) if mask else 0
    out = {}

    # 对三种基础口径各跑 全量 vs 临界过滤 两组
    for base in ("imp", "avg_tricks", "make_rate"):
        rows_all, rows_crit = [], []
        for c in playable:
            sc = cs[str(c)]["scores"]
            v_all = _base_value(D, base, sc, st)
            v_crit = _base_value(D, base, D._filter_critical(sc, mask), st)
            avg = sum(sc) / len(sc) if sc else 0.0
            rows_all.append((str(c), v_all, avg, min(sc) if sc else 0, max(sc) if sc else 0))
            rows_crit.append((str(c), v_crit, avg, min(sc) if sc else 0, max(sc) if sc else 0))
        rows_all.sort(key=lambda r: -r[1])
        rows_crit.sort(key=lambda r: -r[1])
        out[f"{base.upper()}-ALL"] = rows_all
        out[f"{base.upper()}-CRIT"] = rows_crit
    out["_nw"] = nw
    out["_crit"] = crit_n
    out["_worlds"] = worlds
    return out


def _base_value(D, mode, sc, st):
    """按基础口径对给定（已过滤/全量）赢墩序列求决策值，口径间统一走同一实现。"""
    if mode == "avg_tricks":
        return sum(sc) / len(sc) if sc else 0.0
    if mode == "make_rate":
        return sum(1 for t in sc if t >= st.contract.tricks_needed) / len(sc) if sc else 0.0
    # imp
    return D._expected_imp_value(sc, st.contract,
                                 D._declarer_side_vulnerable("南", "NV"))


def main():
    random.seed(20260825)
    found = 0
    total = 0
    for seed in range(8000):
        st = build_to_endgame(100000 + seed)
        if st is None:
            continue
        res = eval_modes(st)
        if res is None:
            continue
        total += 1
        if res["_crit"] <= 0:
            continue  # 无临界分布，分歧是空集回退的假象，跳过
        # 任一基础口径 全量 vs 临界过滤 选牌不同 即命中
        diverged = [b for b in ("IMP", "AVG_TRICKS", "MAKE_RATE")
                    if res[f"{b}-ALL"][0][0] != res[f"{b}-CRIT"][0][0]]
        if diverged:
            found += 1
            nw = res["_nw"]
            nc = res["_crit"]
            print(f"\n===== 命中残局 seed={100000 + seed} 世界数={nw} 临界={nc}({nc / nw:.0%}) "
                  f"分歧口径={diverged}")
            for base in ("IMP", "AVG_TRICKS", "MAKE_RATE"):
                all_top = res[f"{base}-ALL"][0][0]
                crit_top = res[f"{base}-CRIT"][0][0]
                mark = " ←" if all_top != crit_top else ""
                print(f"  [{base}] 全量选中 {all_top:>4} | 过滤后 {crit_top:>4}{mark}")
                print(f"       " + "  ".join(
                    f"{c}(v={v:+.2f},avg={a:.1f},min={mn},max={mx})"
                    for c, v, a, mn, mx in res[f"{base}-ALL"][:4]))
                print(f"       " + "  ".join(
                    f"{c}(v={v:+.2f},avg={a:.1f},min={mn},max={mx})"
                    for c, v, a, mn, mx in res[f"{base}-CRIT"][:4]))
            for p in ORDER:
                print(f"   {p}: " + " ".join(str(c) for c in st.hands[p]))
            print(f"   decl_tricks={st.declarer_tricks} def_tricks={st.defender_tricks} "
                  f"current={st.current_player}")
            print("   ----")
            if found >= 2:
                break
    print(f"\n扫 {total} 个有效残局，{found} 个在某种口径下全量/过滤选牌不同")
    return


if __name__ == "__main__":
    main()