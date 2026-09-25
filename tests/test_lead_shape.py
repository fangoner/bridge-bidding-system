# -*- coding: utf-8 -*-
"""v2.15 首攻顶张连张·形态白名单单测（新睿表12-1 排除法）。"""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from bridge.play_types import Card
from bridge.mcts.constraints import (
    _LEAD_SHAPE_NT, _LEAD_SHAPE_TRUMP, parse_lead_shape_patterns, match_suit_shape,
    match_suit_small_shapes, _build_trump_small_shapes,
    BidConstraint, _check_constraint, relax_constraint,
)


def suit_cards(suit, ranks):
    return [Card(suit, r) for r in ranks]


def makes_cards(cards, lead_shape_tuple):
    suit, lead_rank, entries = lead_shape_tuple
    lead = Card(suit, lead_rank)
    return match_suit_shape(cards, (suit, lead_rank, entries))


def test_shape(lead_rank, remaining_cards, expect):
    entries = parse_lead_shape_patterns(_LEAD_SHAPE_NT[lead_rank])
    ls = ("♠", lead_rank, entries)
    ok = makes_cards(remaining_cards, ls)
    status = "PASS" if ok == expect else "FAIL"
    print(f"  [{status}] 攻{lead_rank} 剩余{' '.join(c.rank for c in remaining_cards)} "
          f"→ {ok} (期望 {expect})")
    return ok == expect


def main():
    print("=" * 70)
    print("表12-1 形态白名单单测（♠ 花色示例）")
    total = passed = 0

    def run_case(lead_rank, rem_ranks, expect):
        nonlocal total, passed
        total += 1
        entries = parse_lead_shape_patterns(_LEAD_SHAPE_NT[lead_rank])
        cards = suit_cards("♠", rem_ranks)
        ok = match_suit_shape(cards, ("♠", lead_rank, entries))
        status = "PASS" if ok == expect else "FAIL"
        if ok == expect:
            passed += 1
        print(f"  [{status}] 攻{lead_rank} 剩余{rem_ranks or '-'} → {ok} (期望 {expect})")

    # ── 攻 K 行：KQJ+, KQ+, Kx, K ──
    print("攻 K：白名单 = KQJ+/KQ+/Kx/K")
    run_case("K", ["Q", "J", "2", "3"], True)    # KQJ+
    run_case("K", ["Q", "2", "3"], True)         # KQ+
    run_case("K", ["2"], True)                   # Kx
    run_case("K", [], True)                      # K 单张
    run_case("K", ["Q", "J", "T", "2"], False)   # KQJT 超出（KQJ+ 无 T）
    run_case("K", ["A", "2"], False)             # AK 攻K 排除
    run_case("K", ["Q", "T"], False)             # KQT 超出（有 T 无 J → 非 KQJ+ 非 KQ+）
    run_case("K", ["2", "3"], False)             # Kxx 非 Kx（x 恰好1张）

    # ── 攻 A 行：AKQJ+, AKQ+, AKx, AK, Ax+, A ──
    print("攻 A：白名单 = AKQJ+/AKQ+/AKx/AK/Ax+/A")
    run_case("A", ["K", "Q", "J", "2"], True)    # AKQJ+
    run_case("A", ["K", "Q", "2"], True)         # AKQ+
    run_case("A", ["K", "2"], True)              # AKx
    run_case("A", ["K"], True)                   # AK
    run_case("A", ["2", "3"], True)              # Ax+
    run_case("A", ["Q", "2"], False)             # AQ 非白名单（无 K）
    run_case("A", ["K", "Q", "2", "T"], False)   # AKQT 超出

    # ── 攻 Q 行：QJ+, AQJ+, Qx, Q ──
    print("攻 Q：白名单 = QJ+/AQJ+/Qx/Q")
    run_case("Q", ["J", "2", "3"], True)         # QJ+
    run_case("Q", ["A", "J", "2"], True)         # AQJ+
    run_case("Q", ["2"], True)                   # Qx
    run_case("Q", [], True)                      # Q 单张
    run_case("Q", ["A", "2"], False)             # AQ 非白名单（无 J → 非 AQJ+）
    run_case("Q", ["J", "T"], False)             # QJT 超出

    # ── 攻 J 行：J10+, AJ10+, KJ10+, Jx, J ──
    print("攻 J：白名单 = J10+/AJ10+/KJ10+/Jx/J")
    run_case("J", ["T", "2", "3"], True)         # J10+
    run_case("J", ["A", "T", "2"], True)         # AJ10+
    run_case("J", ["K", "T", "2"], True)         # KJ10+
    run_case("J", ["2"], True)                   # Jx
    run_case("J", [], True)                      # J 单张
    run_case("J", ["Q", "T"], False)             # JQT 超出（无 A/K）

    # ── 攻 T(10) 行：109+, A109+, K109+, Q109+, 10x, 10 ──
    print("攻 T(10)：白名单 = 109+/A109+/K109+/Q109+/10x/10")
    run_case("T", ["9", "2", "3"], True)         # 109+
    run_case("T", ["A", "9", "2"], True)         # A109+
    run_case("T", ["K", "9", "2"], True)         # K109+
    run_case("T", ["Q", "9", "2"], True)         # Q109+
    run_case("T", ["2"], True)                   # 10x
    run_case("T", [], True)                      # 10 单张
    run_case("T", ["J", "9"], False)             # J109 超出（首攻10 无 J）
    run_case("T", ["A", "J", "9"], False)        # AJ109 超出

    # ── _check_constraint 集成 + relax 不丢 ──
    print("集成验证（BidConstraint._check_constraint）")
    entries = parse_lead_shape_patterns(_LEAD_SHAPE_NT["K"])
    con = BidConstraint(position="西", lead_shape=("♠", "K", entries),
                        inference_source="opening_lead_honor_chain")
    ok = _check_constraint(suit_cards("♠", ["Q", "2"]), con)
    print(f"  [{'PASS' if ok else 'FAIL'}] 攻K 剩余♠Q2 → {ok} (期望 True)")
    total += 1; passed += ok
    # 攻K 但花色含 A：应 False
    ok = _check_constraint(suit_cards("♠", ["A", "2"]), con)
    print(f"  [{'PASS' if not ok else 'FAIL'}] 攻K 剩余♠A2 → {not ok} (期望 True=拒绝)")
    total += 1; passed += (not ok)
    # relax 与 length_above 同款：不保留 lead_shape（宽松链降级处理）
    relaxed = relax_constraint(con)
    ok_relax = relaxed.lead_shape is None
    print(f"  [{'PASS' if ok_relax else 'FAIL'}] relax 丢弃 lead_shape（同 length_above）→ {ok_relax}")
    total += 1; passed += ok_relax

    # ── 小牌白名单（长四/三张/双张）──
    print("攻小牌白名单：[(4+, ≥3大), (3张, ≥1大), (2张, 0大)]")

    def run_small(suit, rem_ranks, expect):
        nonlocal total, passed
        total += 1
        # 模拟攻 ♠7：首攻牌 7 已出，rem 为剩余该花色
        shapes = ["♠", "7", [(4, 13, 3, 3, 0, 99), (3, 3, 2, 2, 1, 99),
                             (3, 3, 1, 1, 0, 0), (2, 2, 0, 0, 0, 99)]]
        cards = suit_cards(suit, rem_ranks)
        ok = match_suit_small_shapes(cards, shapes)
        status = "PASS" if ok == expect else "FAIL"
        if ok == expect:
            passed += 1
        print(f"  [{status}] 攻♠7 剩余{rem_ranks or '-'} → {ok} (期望 {expect})")

    run_small("♠", ["K", "9", "2"], False)   # 完整K,9,7,2：>7=K,9 仅2张 → 非长四(需3)
    run_small("♠", ["K", "Q", "J"], True)    # 完整K,Q,J,7：>7=3张 → 长四
    run_small("♠", ["9", "8"], False)        # 完整9,8,7：三张小牌应攻中间8，攻7不合法
    run_small("♠", ["T", "8"], True)         # 完整T,8,7：>7=T,8 2张含大牌T → 三张带大牌攻最小
    run_small("♠", ["9"], False)             # 完整9,7：双张 9-7 应攻9，攻7不合法
    run_small("♠", ["K"], False)             # 完整K,7：>7=K 1张大牌 → 非双张(需0大)/非三张中部(需1小)
    run_small("♠", ["2"], True)              # 完整7,2：>7=0 → 双张攻大
    run_small("♠", ["3", "4"], False)        # 完整7,3,4：>7=0 但3张 → 非双张；长四需3大 → False
    run_small("♠", ["K", "Q", "J", "A"], False)  # 完整A,K,Q,J,7：>7=4张 → 长四需恰3 → 排除
    run_small("♠", ["Q", "8"], True)         # 完整Q,8,7：>7=Q,8 2张含大牌Q → 三张带大牌攻最小
    run_small("♠", ["5", "6"], False)        # 完整7,5,6：>7=0 → 非任何形态

    # 集成验证：BidConstraint._check_constraint 小牌分支
    con_small = BidConstraint(position="西", lead_small_shapes=("♠", "7", [(4, 13, 3, 3, 0, 99), (3, 3, 2, 2, 1, 99), (3, 3, 1, 1, 0, 0), (2, 2, 0, 0, 0, 99)]),
                              inference_source="opening_lead_long4")
    ok = _check_constraint(suit_cards("♠", ["K", "2"]), con_small)
    print(f"  [{'PASS' if not ok else 'FAIL'}] 攻7 剩余♠K2 → {not ok} (期望 True=拒绝：三张中间上面是大牌)")
    total += 1; passed += (not ok)
    ok = _check_constraint(suit_cards("♠", ["9", "8"]), con_small)
    print(f"  [{'PASS' if not ok else 'FAIL'}] 攻7 剩余♠98 → {not ok} (期望 True=拒绝：三张小牌应攻中间8)")
    total += 1; passed += (not ok)

    # ── 有将顶张：K 行含 AK（AK 双张攻 K），无 KQJ+；A 行无 AK ──
    print("有将顶张（表12-3）：K 行 = KQ+/AK/Kx/K")
    entries = parse_lead_shape_patterns(_LEAD_SHAPE_TRUMP["K"])
    con_kt = BidConstraint(position="西", lead_shape=("♠", "K", entries),
                           inference_source="opening_lead_honor_chain")
    ok = _check_constraint(suit_cards("♠", ["Q", "2"]), con_kt)
    print(f"  [{'PASS' if ok else 'FAIL'}] 有将攻K 剩余♠Q2 → {ok} (期望 True：KQ+)")
    total += 1; passed += ok
    ok = _check_constraint(suit_cards("♠", ["A"]), con_kt)
    print(f"  [{'PASS' if ok else 'FAIL'}] 有将攻K 剩余♠A → {ok} (期望 True：AK 双张攻K)")
    total += 1; passed += ok
    ok = _check_constraint(suit_cards("♠", ["Q", "J"]), con_kt)
    print(f"  [{'PASS' if not ok else 'FAIL'}] 有将攻K 剩余♠QJ → {not ok} (期望 True=拒绝：无KQJ+，QJ多J)")
    total += 1; passed += (not ok)
    # NT 对照：K 行含 KQJ+，KQJ 是合法（有将应拒绝）
    entries_nt = parse_lead_shape_patterns(_LEAD_SHAPE_NT["K"])
    ok = _check_constraint(suit_cards("♠", ["Q", "J"]), BidConstraint(position="西", lead_shape=("♠", "K", entries_nt)))
    print(f"  [{'PASS' if ok else 'FAIL'}] NT 对照 攻K 剩余♠QJ → {ok} (期望 True：NT KQJ+ 合法)")
    total += 1; passed += ok

    # ── 有将小牌：3/5 首攻 ──
    print("有将小牌（表12-3 X 行）：3/5 首攻偶数攻第3大/奇数攻最小")
    ent_trump = _build_trump_small_shapes("7")

    def run_trump(suit, rem_ranks, expect):
        nonlocal total, passed
        total += 1
        cards = suit_cards(suit, rem_ranks)
        ok = match_suit_small_shapes(cards, ("♠", "7", ent_trump))
        status = "PASS" if ok == expect else "FAIL"
        if ok == expect:
            passed += 1
        print(f"  [{status}] 有将攻♠7 剩余{rem_ranks or '-'} → {ok} (期望 {expect})")

    run_trump("♠", ["K", "9", "8", "2"], False)   # 5张：>7=K,9,8 3张 → 5张奇数攻最小需4张→False
    run_trump("♠", ["K", "8", "2"], True)        # 4张：>7=K,8 2张 → 偶数攻第3大
    run_trump("♠", ["K", "8"], True)             # 3张带大牌攻最小（K,8>7 2张含大牌）
    run_trump("♠", ["9", "8"], False)            # 3张：9,8>7 2张无大牌 → 非HxX；above≠1非xXx
    run_trump("♠", ["9"], False)                 # 2张：9>7 1张 → 非双张攻大(0大)
    run_trump("♠", ["2"], True)                  # 2张：双张攻大(0张>7)
    run_trump("♠", ["A", "8", "2"], True)        # 4张偶数：>7=A,8 2张
    run_trump("♠", ["A", "8", "3", "2"], False)  # 5张奇数：>7=A,8 2张 → 非攻最小(需4张)
    run_trump("♠", ["A", "5", "4", "3", "2"], False)  # 6张偶数：>7=A 1张 → 偶数需2张→False
    run_trump("♠", ["A", "8", "5", "4", "3", "2"], False)  # 7张奇数：>7=A,8 2张 → 攻最小需6张→False
    run_trump("♠", ["A", "8", "5", "4", "3"], True)     # 6张偶数：>7=A,8 2张 → 攻第3大
    run_trump("♠", ["9", "8", "3"], True)        # 4张偶数：>7=9,8 2张（无大牌也过）
    run_trump("♠", ["K", "Q", "J", "A", "8"], False)  # 6张：>7=K,Q,J,A,8 5张 → 偶数需2→False

    # ── 中局递减（2026-09-25 用户原则：带长度/点力的约束随出牌递减）──
    print("中局递减：lead_shape（攻K）+ length_above")
    from bridge.mcts.sampler import _reduce_constraint_for_played

    def reduce_lead(played_ranks):
        entries = parse_lead_shape_patterns(_LEAD_SHAPE_NT["K"])
        con = BidConstraint(position="西", lead_shape=("♠", "K", entries),
                            inference_source="opening_lead_honor_chain")
        played = {"hcp": 0, "controls": 0, "suit": {"♠": len(played_ranks)}}
        pcs = [Card("♠", r) for r in played_ranks]
        return _reduce_constraint_for_played(con, played, 13 - len(played_ranks),
                                             played_cards=pcs)

    # 出首攻 K → 剩余口径：KQ+ 变 Q小≥2（剔首攻牌），剩余♠Q2 命中、♠A2 拒绝
    r1 = reduce_lead(["K"])
    ok1 = (r1 is not None and r1.lead_shape is not None
           and match_suit_shape(suit_cards("♠", ["Q", "2"]), r1.lead_shape))
    print(f"  [{'PASS' if ok1 else 'FAIL'}] 出K(首攻) 剩余口径：剩余♠Q2 命中 → {ok1}")
    total += 1; passed += ok1
    ok1b = (r1 is not None and r1.lead_shape is not None
            and not match_suit_shape(suit_cards("♠", ["A", "2"]), r1.lead_shape))
    print(f"  [{'PASS' if ok1b else 'FAIL'}] 出K(首攻) 剩余♠A2 拒绝（AK排除）→ {ok1b}")
    total += 1; passed += ok1b
    ok1c = (r1 is not None and r1.lead_shape is not None
            and match_suit_shape(suit_cards("♠", ["2"]), r1.lead_shape))
    print(f"  [{'PASS' if ok1c else 'FAIL'}] 出K(首攻) 剩余♠2 命中（Kx 分支）→ {ok1c}")
    total += 1; passed += ok1c
    # 出第二张 Q → 递减：KQJ+ 变 {K,J}+小≥1，剩余♠J2 命中；剩余♠A2 拒绝
    r2 = reduce_lead(["K", "Q"])
    ok2 = (r2 is not None and r2.lead_shape is not None
           and match_suit_shape(suit_cards("♠", ["J", "2"]), r2.lead_shape))
    print(f"  [{'PASS' if ok2 else 'FAIL'}] 出KQ 递减后剩余♠J2 命中 → {ok2}")
    total += 1; passed += ok2
    ok3 = (r2 is not None and r2.lead_shape is not None
           and not match_suit_shape(suit_cards("♠", ["A", "2"]), r2.lead_shape))
    print(f"  [{'PASS' if ok3 else 'FAIL'}] 出KQ 递减后剩余♠A2 拒绝（AK排除）→ {ok3}")
    total += 1; passed += ok3
    # 出第二张小牌 → 小牌下限扣减：KQJ+ 小牌下限 1-1=0，剩余♠QJ2 命中
    r3 = reduce_lead(["K", "5"])
    ok4 = (r3 is not None and r3.lead_shape is not None
           and match_suit_shape(suit_cards("♠", ["Q", "J", "2"]), r3.lead_shape))
    print(f"  [{'PASS' if ok4 else 'FAIL'}] 出K5 递减后剩余♠QJ2 命中（小牌下限0）→ {ok4}")
    total += 1; passed += ok4
    # length_above 递减：♠>8 需3张，出 ♠8/♠9/♠K（>8 两张）→ 剩余需 1
    con_la = BidConstraint(position="西", length_above={"♠": ("8", 3)},
                           inference_source="test")
    played_la = {"hcp": 0, "controls": 0, "suit": {"♠": 3}}
    r_la = _reduce_constraint_for_played(con_la, played_la, 10,
                                         played_cards=[Card("♠", "8"), Card("♠", "9"),
                                                       Card("♠", "K")])
    ok5 = r_la is not None and r_la.length_above.get("♠") == ("8", 1)
    print(f"  [{'PASS' if ok5 else 'FAIL'}] length_above 出♠8/9/K 后 >8 需 3-2=1 → {ok5}")
    total += 1; passed += ok5
    # >8 全部出尽（4 张）→ 释放
    r_la2 = _reduce_constraint_for_played(con_la, {"hcp": 0, "controls": 0, "suit": {"♠": 4}}, 9,
                                          played_cards=[Card("♠", "8"), Card("♠", "9"),
                                                        Card("♠", "K"), Card("♠", "Q")])
    ok6 = r_la2 is None or "♠" not in (r_la2.length_above or {})
    print(f"  [{'PASS' if ok6 else 'FAIL'}] length_above 出尽 >8 → 释放 → {ok6}")
    total += 1; passed += ok6

    print("=" * 70)
    print(f"结果: {passed}/{total}")
    return 0 if passed == total else 1


if __name__ == "__main__":
    sys.exit(main())