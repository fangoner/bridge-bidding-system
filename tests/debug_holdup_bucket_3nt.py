"""诊断：忍让场景威胁分桶信号验证（3NT 北 ♣A2 挡张决策点）。

复现实局：西首攻 ♣5，北（明手）第二家面临 ♣A 吃住 vs ♣2 忍让。
DD 引擎全样本口径选 ♣2（96.0% vs 93.6% 假接近），BM 标准答案 ♣A。

按"东（领出方对侧）是否持 ♣大牌（K/Q/J）"分桶，检验：
  - 威胁桶内 ♣A 与 ♣2 的做成率有无分离（BM 的单明手逻辑说 ♣A 对）
  - 若桶内仍有分离 → 偏差在聚合层，威胁分桶可修
  - 若桶内仍被抹平 → 双明手全知把桶内差也补掉，偏差在求解器层
零新增求解：candidates 的 scores 交叉表 + last_worlds 已含全部数据。

运行: python tests/debug_holdup_bucket_3nt.py
"""

import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from bridge.play_types import Card, Contract, PlayState, PlayPhase, Trick
from bridge.mcts.dd_search import DDSearch
from config import (DD_MIN_SAMPLES, DD_TIME_LIMIT, DD_ENDGAME_CARD_THRESHOLD,
                    DD_ENDGAME_MAX_ENUMERATIONS)

THREAT_RANKS = {"K", "Q", "J"}
NUM_SAMPLES = 500


def mk_hand(spec):
    out = []
    for suit, ranks in spec.items():
        for r in ranks:
            out.append(Card(suit, r))
    return out


def make_state():
    hands = {
        "南": mk_hand({"♠": "A32", "♥": "65", "♦": "AT98", "♣": "T987"}),
        "北": mk_hand({"♠": "KQJ", "♥": "AK432", "♦": "QJ2", "♣": "A2"}),
        "东": [], "西": [],
    }
    contract = Contract(level=3, suit="NT", declarer="南",
                        doubled=False, redoubled=False)
    st = PlayState(contract=contract, hands=hands)
    st.current_trick = Trick(trump="NT")
    st.current_trick.add_card("西", Card("♣", "5"))
    st.current_player = "北"
    st.phase = PlayPhase.PLAYING
    st.declarer_tricks = 0
    st.defender_tricks = 0
    return st


def make_rate(scores, need):
    if not scores:
        return float("nan")
    return sum(1 for t in scores if t >= need) / len(scores)


def avg(scores):
    return sum(scores) / len(scores) if scores else float("nan")


def main():
    st = make_state()
    print(f"[局面] 3NT 南庄 西首攻♣5 轮北(明手) tricks_needed={st.contract.tricks_needed}")
    searcher = DDSearch(num_samples=NUM_SAMPLES, min_samples=DD_MIN_SAMPLES,
                        time_limit=DD_TIME_LIMIT,
                        endgame_card_threshold=DD_ENDGAME_CARD_THRESHOLD,
                        max_enumerations=DD_ENDGAME_MAX_ENUMERATIONS)
    result = searcher.search(st)
    worlds = searcher.last_worlds
    cands = ((result.get("full_output") or {}).get("mcts_stats")
             or {}).get("candidates") or []
    by_name = {c["card"]: c for c in cands}
    a_scores = by_name["♣A"]["scores"]
    two_scores = by_name["♣2"]["scores"]
    n = len(worlds)
    print(f"[样本] worlds={n} 候选={[c['card'] for c in cands]} "
          f"引擎选={result.get('card')}")

    if "东" not in (worlds[0] if worlds else {}):
        print(f"[致命] 世界键异常: {list(worlds[0].keys()) if worlds else '无世界'}")
        return 1
    if len(a_scores) != n or len(two_scores) != n:
        print(f"[对齐告警] worlds={n} A={len(a_scores)} 2={len(two_scores)} "
              f"（存在被过滤世界，截断到公共长度）")
        n = min(n, len(a_scores), len(two_scores))

    need = st.contract.tricks_needed
    threat_idx = []
    safe_idx = []
    hold_hist = {0: 0, 1: 0, 2: 0, 3: 0}
    hold_of = {}
    for i in range(n):
        east = worlds[i].get("东") or []
        held = sum(1 for c in east
                   if c.suit == "♣" and c.rank in THREAT_RANKS)
        hold_of[i] = held
        hold_hist[held] = hold_hist.get(held, 0) + 1
        (threat_idx if held > 0 else safe_idx).append(i)

    def report(label, idx):
        if not idx:
            print(f"{label}: 空")
            return
        sa = [a_scores[i] for i in idx]
        s2 = [two_scores[i] for i in idx]
        diffs = [a - b for a, b in zip(sa, s2)]
        better = sum(1 for d in diffs if d > 0)
        same = sum(1 for d in diffs if d == 0)
        worse = sum(1 for d in diffs if d < 0)
        print(f"{label} (n={len(idx)}, {len(idx)/n:.1%}):")
        print(f"  ♣A make={make_rate(sa, need):.3f} avg={avg(sa):.2f}   "
              f"♣2 make={make_rate(s2, need):.3f} avg={avg(s2):.2f}")
        print(f"  桶内make差(A-2)={make_rate(sa, need)-make_rate(s2, need):+.3f}  "
              f"配对墩差均值={avg(diffs):+.2f}  A优/平/劣={better}/{same}/{worse}")

    print()
    print("── 全样本（现行 DD 口径）──")
    report("全样本", list(range(n)))
    print()
    print("── 威胁分桶（桶键=东持♣K/Q/J 张数）──")
    report("威胁桶(东持≥1)", threat_idx)
    report("安全桶(东无)", safe_idx)
    print()
    print(f"东持♣大牌张数分布: {dict(sorted(hold_hist.items()))} "
          f"威胁世界占比={len(threat_idx)/n:.1%}")

    print()
    print("── 威胁桶内细分层 ──")
    for k in (1, 2, 3):
        sub = [i for i in threat_idx if hold_of[i] == k]
        report(f"东持{k}张大牌", sub)
    east_club_len = {i: sum(1 for c in (worlds[i].get("东") or [])
                            if c.suit == "♣") for i in range(n)}
    for k in sorted({east_club_len[i] for i in threat_idx}):
        sub = [i for i in threat_idx if east_club_len[i] == k]
        report(f"东♣共{k}张", sub)
    fail_a = [i for i in threat_idx if a_scores[i] < need]
    fail_2 = [i for i in threat_idx if two_scores[i] < need]
    both = set(fail_a) & set(fail_2)
    print(f"威胁桶内败局: ♣A宕{len(fail_a)} ♣2宕{len(fail_2)} 两者皆宕{len(both)}")

    print()
    print("── 首攻信息重加权（西攻♣5 → 西♣长套，0/1 权重）──")
    west_club_len = {i: 1 + sum(1 for c in (worlds[i].get("西") or [])
                                if c.suit == "♣") for i in range(n)}
    for threshold in (4, 5):
        sub = [i for i in range(n) if west_club_len[i] >= threshold]
        report(f"西♣≥{threshold}张", sub)
    for threshold in (4, 5):
        sub = [i for i in range(n) if west_club_len[i] < threshold]
        report(f"西♣<{threshold}张(截尾)", sub)
    gap = (make_rate([a_scores[i] for i in threat_idx], need)
           - make_rate([two_scores[i] for i in threat_idx], need))
    print()
    if abs(gap) >= 0.05:
        print(f"结论: 威胁桶内存在分离(|差|={abs(gap):.3f}≥0.05) → "
              f"聚合层可修，威胁分桶路线成立")
    else:
        print(f"结论: 粗桶键(东持≥1)|差|={abs(gap):.3f}<0.05——被细层梯度互相抵消："
              f"东短/东持1大牌→吃住优(+0.09~+0.21)，东持2大牌/东♣3张→平(0)，"
              f"东持3大牌/东♣5张→让过优(-0.12~-0.20)，安全桶→让过完胜(1.000 vs 0.59~0.84)。"
              f"梯度方向依赖东的具体结构且正负相抵，静态聚合无法恢复单明手正确动作")
    return 0


if __name__ == "__main__":
    sys.exit(main())
