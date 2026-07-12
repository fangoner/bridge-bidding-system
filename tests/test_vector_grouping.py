"""测试 αμ+LLM 引擎的 best_vector 分组逻辑。

测试覆盖：
1. _group_candidates_by_vector 基本分组
2. 非连续但vector相同 → 合并为一组
3. 连续张 + vector相同 → 一组（特例自动覆盖）
4. vector缺失 → 退化到连续张分组
5. >0%阈值 + 15%截断逻辑
6. _should_trigger_llm 触发条件（组数≥2）
7. 单组/无候选边界情况
8. 混合vector和连续张
9. vector相同跨区间拆分
10. 跨区间连续（7-8, T-J）不拆分
11. 跨区间不连续（5-T, 2-J）拆分
12. 将牌和非将牌分拆
13. 战术标签标注
"""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from bridge.play_service import PlayService
from unittest.mock import MagicMock


def make_service():
    llm = MagicMock()
    llm.is_configured.return_value = True
    return PlayService(llm_client=llm)


def make_candidate(card, success_rate, best_vector):
    return {
        "card": card,
        "success_rate": success_rate,
        "best_vector": best_vector,
        "avg_tricks": 10.0,
        "min_tricks": 8,
        "worst": 8,
    }


def test_basic_grouping_by_vector():
    """测试1: 不同vector各自成组，相同vector合并。"""
    print("=" * 60)
    print("测试 1: 基本vector分组")
    print("=" * 60)
    svc = make_service()

    candidates = [
        make_candidate("♠2", 0.55, "vec_A"),
        make_candidate("♠3", 0.55, "vec_A"),
        make_candidate("♥5", 0.60, "vec_B"),
        make_candidate("♦K", 0.50, "vec_C"),
    ]
    groups = svc._group_candidates_by_vector(candidates)

    assert len(groups) == 3, f"应有3组(2+3同vec_A, ♥5 vec_B, ♦K vec_C), 实际{len(groups)}"
    vec_a_group = next(g for g in groups if g.get("best_vector") == "vec_A")
    assert len(vec_a_group["cards"]) == 2, f"vec_A组应有2张牌, 实际{len(vec_a_group['cards'])}"
    card_strs = [c["card"] for c in vec_a_group["cards"]]
    assert "♠2" in card_strs and "♠3" in card_strs, f"vec_A组应含♠2♠3, 实际{card_strs}"
    print(f"  ✓ vec_A组: {' '.join(card_strs)} (合并)")

    print(f"  ✓ 共{len(groups)}组，vector相同的牌已合并")
    for g in groups:
        print(f"    组{g['group_id']}: {' '.join(c['card'] for c in g['cards'])} (vec={g.get('best_vector','')[:8]})")


def test_non_continuous_same_vector():
    """测试2: 非连续但vector相同 → 合并为一组（核心改进）。"""
    print("=" * 60)
    print("测试 2: 非连续但vector相同(如2,3,5)合并")
    print("=" * 60)
    svc = make_service()

    candidates = [
        make_candidate("♠2", 0.55, "vec_X"),
        make_candidate("♠3", 0.55, "vec_X"),
        make_candidate("♠5", 0.55, "vec_X"),
        make_candidate("♥A", 0.70, "vec_Y"),
    ]
    groups = svc._group_candidates_by_vector(candidates)

    assert len(groups) == 2, f"应有2组(vec_X合并, vec_Y), 实际{len(groups)}"
    vec_x_group = groups[1] if groups[0]["best_vector"] == "vec_Y" else groups[0]
    assert len(vec_x_group["cards"]) == 3, f"vec_X组应有3张牌, 实际{len(vec_x_group['cards'])}"
    card_strs = [c["card"] for c in vec_x_group["cards"]]
    assert set(card_strs) == {"♠2", "♠3", "♠5"}, f"应含♠2♠3♠5, 实际{card_strs}"
    print(f"  ✓ 非连续♠2♠3♠5(vector相同)合并为一组: {' '.join(card_strs)}")


def test_continuous_automatic_coverage():
    """测试3: 连续张 + vector相同 → 自动合并为一组（跨区间连续不拆）。"""
    print("=" * 60)
    print("测试 3: 连续张自动覆盖（含跨区间连续）")
    print("=" * 60)
    svc = make_service()

    candidates = [
        make_candidate("♠Q", 0.65, "vec_C"),
        make_candidate("♠J", 0.65, "vec_C"),
        make_candidate("♠T", 0.65, "vec_C"),
        make_candidate("♦2", 0.55, "vec_D"),
    ]
    groups = svc._group_candidates_by_vector(candidates)

    assert len(groups) == 2, f"应有2组(♠QTJ合并, ♦2), 实际{len(groups)}"
    spade_group = next(g for g in groups if any(c["card"].startswith("♠") for c in g["cards"]))
    assert len(spade_group["cards"]) == 3, f"♠组应有3张, 实际{len(spade_group['cards'])}"
    print(f"  ✓ 连续张♠QTJ合并为一组: {' '.join(c['card'] for c in spade_group['cards'])}")


def test_same_vector_rank_tier_split():
    """测试12: vector相同但同花色内大牌和小牌要分开。"""
    print("=" * 60)
    print("测试 12: vector相同按花色+rank区间拆分")
    print("=" * 60)
    svc = make_service()

    # ♠2♠3♠4♠5(low) + ♠Q(high) → 拆成2组
    candidates = [
        make_candidate("♠2", 0.65, "vec_A"),
        make_candidate("♠3", 0.65, "vec_A"),
        make_candidate("♠4", 0.65, "vec_A"),
        make_candidate("♠5", 0.65, "vec_A"),
        make_candidate("♠Q", 0.65, "vec_A"),
        make_candidate("♦A", 0.64, "vec_B"),
    ]
    groups = svc._group_candidates_by_vector(candidates, trump_suit="♠")

    assert len(groups) == 3, f"应拆成3组(♠low + ♠high + ♦A), 实际{len(groups)}"
    vec_a_groups = [g for g in groups if g.get("best_vector") == "vec_A"]
    assert len(vec_a_groups) == 2, f"vec_A应拆成low+high共2组, 实际{len(vec_a_groups)}"

    low_group = next(g for g in vec_a_groups if any(c["card"] == "♠2" for c in g["cards"]))
    high_group = next(g for g in vec_a_groups if any(c["card"] == "♠Q" for c in g["cards"]))
    assert len(low_group["cards"]) == 4, f"low组应有4张, 实际{len(low_group['cards'])}"
    assert len(high_group["cards"]) == 1, f"high组应有1张, 实际{len(high_group['cards'])}"
    print(f"  ✓ ♠拆分: low组({' '.join(c['card'] for c in low_group['cards'])}) + high组({' '.join(c['card'] for c in high_group['cards'])})")

    # 不同花色分开分组（即使同区间也不合并）
    candidates2 = [
        make_candidate("♠2", 0.66, "vec_X"),
        make_candidate("♠3", 0.66, "vec_X"),
        make_candidate("♣2", 0.66, "vec_X"),
        make_candidate("♣3", 0.66, "vec_X"),
        make_candidate("♠Q", 0.66, "vec_X"),
        make_candidate("♣K", 0.66, "vec_X"),
        make_candidate("♦A", 0.65, "vec_Y"),
    ]
    groups2 = svc._group_candidates_by_vector(candidates2)
    assert len(groups2) == 5, f"应拆成5组(♠low + ♣low + ♠high + ♣high + ♦A), 实际{len(groups2)}"
    vec_x_groups = [g for g in groups2 if g.get("best_vector") == "vec_X"]
    assert len(vec_x_groups) == 4, f"vec_X应拆成4组(2花色×2区间), 实际{len(vec_x_groups)}"
    print(f"  ✓ 不同花色分开: {' | '.join(' '.join(c['card'] for c in g['cards']) for g in vec_x_groups)}")


def test_vector_missing_fallback():
    """测试4: vector缺失 → 退化到连续张分组。"""
    print("=" * 60)
    print("测试 4: vector缺失退化到连续张分组")
    print("=" * 60)
    svc = make_service()

    candidates = [
        make_candidate("♠2", 0.55, ""),
        make_candidate("♠3", 0.55, ""),
        make_candidate("♠5", 0.55, ""),
        make_candidate("♥K", 0.60, ""),
    ]
    groups = svc._group_candidates_by_vector(candidates)

    assert len(groups) == 3, f"vector缺失应退化到连续张分组(3组), 实际{len(groups)}"
    spade_continuous = next(g for g in groups
                           if any(c["card"] == "♠2" for c in g["cards"])
                           and len(g["cards"]) >= 2)
    assert len(spade_continuous["cards"]) == 2, f"♠2♠3应合并, 实际{len(spade_continuous['cards'])}"
    print(f"  ✓ vector缺失时退化: ♠2♠3合并, ♠5独立, ♥K独立")


def test_zero_rate_filtered_and_gap_truncation():
    """测试5: success_rate=0被过滤 + 15%差距截断。"""
    print("=" * 60)
    print("测试 5: >0%过滤 + 15%截断")
    print("=" * 60)
    svc = make_service()

    # 0%的牌被过滤
    candidates = [
        make_candidate("♠2", 0.55, "vec_A"),
        make_candidate("♠3", 0.55, "vec_A"),
        make_candidate("♥K", 0.0, "vec_B"),
    ]
    groups = svc._group_candidates_by_vector(candidates)
    assert len(groups) == 1, f"0%的♥K应被过滤, 只剩1组, 实际{len(groups)}"
    assert len(groups[0]["cards"]) == 2, f"组1应有♠2♠3, 实际{len(groups[0]['cards'])}"
    print(f"  ✓ ♥K(0%)被过滤, 只保留♠2♠3组")

    # 15%差距截断: [60%, 58%, 55%, 20%] → 55%→20%差距35%≥15% → 截断, 保留前3组
    candidates = [
        make_candidate("♠A", 0.60, "vec_1"),
        make_candidate("♠K", 0.58, "vec_2"),
        make_candidate("♥Q", 0.55, "vec_3"),
        make_candidate("♦2", 0.20, "vec_4"),
    ]
    groups = svc._group_candidates_by_vector(candidates)
    assert len(groups) == 3, f"15%截断应保留3组, 实际{len(groups)}"
    rates = [g["success_rate"] for g in groups]
    assert 0.20 not in rates, f"20%组应被截断, 实际{rates}"
    print(f"  ✓ 15%截断: [60%,58%,55%,20%] → 保留前3组, 截断20%")

    # 低成功率但差距<15% → 全保留（唯一成局线路场景）
    candidates = [
        make_candidate("♠A", 0.10, "vec_1"),
        make_candidate("♠K", 0.08, "vec_2"),
        make_candidate("♥Q", 0.05, "vec_3"),
    ]
    groups = svc._group_candidates_by_vector(candidates)
    assert len(groups) == 3, f"低成功率但差距<15%应全保留, 实际{len(groups)}"
    print(f"  ✓ 低成功率全保留: [10%,8%,5%] → 3组全保留（可能含唯一成局线路）")

    # 两组差距≥15% → 截断较低组
    candidates = [
        make_candidate("♠A", 0.60, "vec_1"),
        make_candidate("♥K", 0.40, "vec_2"),
    ]
    groups = svc._group_candidates_by_vector(candidates)
    assert len(groups) == 1, f"差距20%≥15%应截断, 只剩1组, 实际{len(groups)}"
    print(f"  ✓ 差距≥15%截断: [60%,40%] → 只保留60%组")


def test_should_trigger_llm():
    """测试6: 触发条件（组数≥2即触发）。"""
    print("=" * 60)
    print("测试 6: 触发条件")
    print("=" * 60)
    svc = make_service()

    # 组数<2 → 不触发
    groups = [{"success_rate": 0.6, "cards": [{"card": "♠2"}]}]
    assert not svc._should_trigger_llm(groups), "组数<2不应触发"
    print("  ✓ 组数<2 → 不触发")

    # 组数≥2 → 触发（不论成功率高低）
    groups = [
        {"success_rate": 0.10, "cards": [{"card": "♠2"}]},
        {"success_rate": 0.08, "cards": [{"card": "♥K"}]},
    ]
    assert svc._should_trigger_llm(groups), "组数≥2应触发（即使成功率低）"
    print("  ✓ 组数≥2, 低成功率 → 触发（可能含唯一成局线路）")

    # 组数≥2, 高成功率 → 触发
    groups = [
        {"success_rate": 0.60, "cards": [{"card": "♠2"}]},
        {"success_rate": 0.55, "cards": [{"card": "♥K"}]},
    ]
    assert svc._should_trigger_llm(groups), "组数≥2应触发"
    print("  ✓ 组数≥2, 高成功率 → 触发")

    # 空列表 → 不触发
    assert not svc._should_trigger_llm([]), "空列表不应触发"
    print("  ✓ 空列表 → 不触发")


def test_empty_and_single():
    """测试7: 空候选和单候选边界情况。"""
    print("=" * 60)
    print("测试 7: 边界情况")
    print("=" * 60)
    svc = make_service()

    # 空列表
    groups = svc._group_candidates_by_vector([])
    assert groups == [], "空候选应返回空列表"
    print("  ✓ 空候选 → 空列表")

    # 单候选
    candidates = [make_candidate("♠2", 0.55, "vec_A")]
    groups = svc._group_candidates_by_vector(candidates)
    assert groups == [], "单候选应返回空列表(len<2)"
    print("  ✓ 单候选 → 空列表")


def test_mixed_vector_and_continuous():
    """测试8: 混合情况 - 有vector的牌 + vector缺失的牌。"""
    print("=" * 60)
    print("测试 8: 混合vector和连续张")
    print("=" * 60)
    svc = make_service()

    candidates = [
        make_candidate("♠2", 0.55, "vec_A"),
        make_candidate("♠3", 0.55, "vec_A"),
        make_candidate("♥4", 0.50, ""),
        make_candidate("♥5", 0.50, ""),
    ]
    groups = svc._group_candidates_by_vector(candidates)

    assert len(groups) == 2, f"应有2组(vec_A + 连续张退化), 实际{len(groups)}"
    print(f"  ✓ 混合分组: {len(groups)}组")
    for g in groups:
        cards = ' '.join(c['card'] for c in g['cards'])
        vec = g.get('best_vector', '')
        print(f"    组{g['group_id']}: {cards} (vec={vec or '缺失-连续张'})")


def test_rank_tier_split_mixed_suits():
    """测试9: vector相同但混合花色和区间 → 按花色+区间拆分，不同花色不合并。"""
    print("=" * 60)
    print("测试 9: vector相同按花色+区间拆分（混合花色）")
    print("=" * 60)
    svc = make_service()

    candidates = [
        make_candidate("♠2", 0.66, "vec_A"),
        make_candidate("♠3", 0.66, "vec_A"),
        make_candidate("♠5", 0.66, "vec_A"),
        make_candidate("♠Q", 0.66, "vec_A"),
        make_candidate("♣2", 0.66, "vec_A"),
        make_candidate("♣3", 0.66, "vec_A"),
        make_candidate("♦A", 0.65, "vec_B"),
    ]
    groups = svc._group_candidates_by_vector(candidates)

    assert len(groups) == 4, f"应拆成4组(♠low + ♠high + ♣low + ♦A), 实际{len(groups)}"
    vec_a_groups = [g for g in groups if g.get("best_vector") == "vec_A"]
    assert len(vec_a_groups) == 3, f"vec_A应拆成3组(♠low + ♠high + ♣low), 实际{len(vec_a_groups)}"

    spade_low = next(g for g in vec_a_groups if any(c["card"] == "♠2" for c in g["cards"]))
    spade_high = next(g for g in vec_a_groups if any(c["card"] == "♠Q" for c in g["cards"]))
    club_low = next(g for g in vec_a_groups if any(c["card"] == "♣2" for c in g["cards"]))
    assert len(spade_low["cards"]) == 3, f"♠low组应有3张(♠2♠3♠5), 实际{len(spade_low['cards'])}"
    assert len(spade_high["cards"]) == 1, f"♠high组应有1张(♠Q), 实际{len(spade_high['cards'])}"
    assert len(club_low["cards"]) == 2, f"♣low组应有2张(♣2♣3), 实际{len(club_low['cards'])}"
    print(f"  ✓ 花色分开: {' | '.join(' '.join(c['card'] for c in g['cards']) for g in vec_a_groups)}")


def test_rank_tier_continuous_cross_boundary():
    """测试10: 跨区间连续（7-8, T-J）不拆分。"""
    print("=" * 60)
    print("测试 10: 跨区间连续不拆分")
    print("=" * 60)
    svc = make_service()

    candidates = [
        make_candidate("♠7", 0.60, "vec_A"),
        make_candidate("♠8", 0.60, "vec_A"),
        make_candidate("♥K", 0.55, "vec_B"),
    ]
    groups = svc._group_candidates_by_vector(candidates)
    vec_a_groups = [g for g in groups if g.get("best_vector") == "vec_A"]
    assert len(vec_a_groups) == 1, f"7-8连续跨区间不应拆, 实际{len(vec_a_groups)}组"
    print(f"  ✓ 7-8跨区间连续: 不拆分 ({' '.join(c['card'] for c in vec_a_groups[0]['cards'])})")

    candidates2 = [
        make_candidate("♠T", 0.60, "vec_C"),
        make_candidate("♠J", 0.60, "vec_C"),
        make_candidate("♥K", 0.55, "vec_B"),
    ]
    groups2 = svc._group_candidates_by_vector(candidates2)
    vec_c_groups = [g for g in groups2 if g.get("best_vector") == "vec_C"]
    assert len(vec_c_groups) == 1, f"T-J连续跨区间不应拆, 实际{len(vec_c_groups)}组"
    print(f"  ✓ T-J跨区间连续: 不拆分 ({' '.join(c['card'] for c in vec_c_groups[0]['cards'])})")


def test_rank_tier_split_non_continuous():
    """测试11: 同花色跨区间不连续（如5-T）→ 拆分。"""
    print("=" * 60)
    print("测试 11: 同花色跨区间不连续拆分")
    print("=" * 60)
    svc = make_service()

    candidates = [
        make_candidate("♠5", 0.60, "vec_A"),
        make_candidate("♠T", 0.60, "vec_A"),
        make_candidate("♥K", 0.55, "vec_B"),
    ]
    groups = svc._group_candidates_by_vector(candidates)
    vec_a_groups = [g for g in groups if g.get("best_vector") == "vec_A"]
    assert len(vec_a_groups) == 2, f"5-T跨区间不连续应拆成2组, 实际{len(vec_a_groups)}组"
    print(f"  ✓ 5-T跨区间不连续: 拆成2组")
    for g in vec_a_groups:
        print(f"    {' '.join(c['card'] for c in g['cards'])}")


def test_tactic_labels():
    """测试13: 战术标签正确标注。"""
    print("=" * 60)
    print("测试 13: 战术标签标注")
    print("=" * 60)
    svc = make_service()

    candidates = [
        make_candidate("♠2", 0.66, "vec_A"),
        make_candidate("♠3", 0.66, "vec_A"),
        make_candidate("♠Q", 0.66, "vec_B"),
        make_candidate("♥T", 0.60, "vec_C"),
        make_candidate("♥9", 0.60, "vec_C"),
        make_candidate("♣K", 0.55, "vec_D"),
    ]
    groups = svc._group_candidates_by_vector(candidates, trump_suit="♠")

    print(f"  共{len(groups)}组:")
    for g in groups:
        cards = ' '.join(c['card'] for c in g['cards'])
        tactic = g.get('tactic', '')
        print(f"    组{g['group_id']}: {cards} → [{tactic}]")

    tactic_map = {}
    for g in groups:
        tactic_map[g['group_id']] = g.get('tactic', '')

    tactics = list(tactic_map.values())
    assert any("清将" in t for t in tactics), f"应有清将标签, 实际{tactics}"
    assert any("清将/飞牌" == t for t in tactics), f"将牌high应有清将/飞牌标签, 实际{tactics}"
    assert any("长套" in t or "建立" in t for t in tactics), f"应有长套建立标签, 实际{tactics}"
    assert any("兑现" in t or "飞牌" in t for t in tactics), f"应有兑现/飞牌标签, 实际{tactics}"
    print(f"  ✓ 战术标签正确标注（含将牌飞牌）")


if __name__ == "__main__":
    test_basic_grouping_by_vector()
    test_non_continuous_same_vector()
    test_continuous_automatic_coverage()
    test_same_vector_rank_tier_split()
    test_vector_missing_fallback()
    test_zero_rate_filtered_and_gap_truncation()
    test_should_trigger_llm()
    test_empty_and_single()
    test_mixed_vector_and_continuous()
    test_rank_tier_split_mixed_suits()
    test_rank_tier_continuous_cross_boundary()
    test_rank_tier_split_non_continuous()
    test_tactic_labels()
    print("=" * 60)
    print("所有测试通过 ✓")
    print("=" * 60)
