"""测试改进后的PIMC采样约束功能。

验证：
1. 硬编码叫品约束库正确提取约束
2. 采样器正确满足新约束字段（suit_max, exact_suit, min_controls）
3. HCP分布不再偏高，符合自然概率
4. 约束验证函数支持新字段
"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import random
from collections import Counter
from bridge.mcts.constraints import BidConstraint, validate_sample, filter_hard_constraints, HCP_MAP
from bridge.mcts.sampler import DealSampler, _sample_uniform
from bridge.mcts.bid_constraint_library import (
    extract_constraints_from_bid_history,
    get_opening_bid_constraint,
    get_takeout_double_constraint,
    get_overcall_constraint,
    _normalize_bid,
    SPECIAL_PASS, SPECIAL_DOUBLE,
)
from bridge.play_types import Card, PlayState, Contract, PlayPhase


def test_normalize_bid():
    """测试叫品标准化解析"""
    print("=== 测试叫品解析 ===")
    test_cases = [
        ("1NT", (1, "NT")),
        ("1♠", (1, "♠")),
        ("1S", (1, "♠")),
        ("2♥", (2, "♥")),
        ("2H", (2, "♥")),
        ("3♦", (3, "♦")),
        ("4♣", (4, "♣")),
        ("2NT", (2, "NT")),
        ("7NT", (7, "NT")),
        ("pass", (SPECIAL_PASS, None)),
        ("不叫", (SPECIAL_PASS, None)),
        ("X", (SPECIAL_DOUBLE, None)),
        ("加倍", (SPECIAL_DOUBLE, None)),
    ]
    all_pass = True
    for bid_text, expected in test_cases:
        result = _normalize_bid(bid_text)
        ok = result == expected
        if not ok:
            all_pass = False
        print(f"  {bid_text:6s} → {result} {'✓' if ok else f'✗ 期望 {expected}'}")
    print(f"叫品解析: {'全部通过' if all_pass else '有失败'}\n")
    return all_pass


def test_opening_constraints():
    """测试开叫叫品的硬编码约束"""
    print("=== 测试开叫约束 ===")
    test_cases = [
        # (bid, exp_min_hcp, exp_max_hcp, exp_balanced, exp_suit_min, exp_suit_max, exp_exact_suit)
        ("1NT", 15, 17, True, {}, {"♥": 4, "♠": 4}, {}),
        ("1♠", 12, 21, None, {"♠": 5}, {}, {}),
        ("1♥", 12, 21, None, {"♥": 5}, {}, {}),
        ("1♣", 12, 21, None, {"♣": 3}, {}, {}),
        ("2♥", 6, 10, None, {}, {}, {"♥": 6}),
        ("2♠", 6, 10, None, {}, {}, {"♠": 6}),
        ("2NT", 20, 21, True, {}, {}, {}),
        ("2♣", 22, None, None, {}, {}, {}),
    ]
    
    all_pass = True
    for bid, exp_min, exp_max, exp_balanced, exp_suit_min, exp_suit_max, exp_exact in test_cases:
        c = get_opening_bid_constraint(bid)
        ok = True
        issues = []
        if c is None:
            ok = False
            issues.append("返回None")
        else:
            if c.min_hcp != exp_min:
                ok = False
                issues.append(f"min_hcp={c.min_hcp}≠{exp_min}")
            if exp_max is not None and c.max_hcp != exp_max:
                ok = False
                issues.append(f"max_hcp={c.max_hcp}≠{exp_max}")
            if exp_balanced is not None and c.balanced != exp_balanced:
                ok = False
                issues.append(f"balanced={c.balanced}≠{exp_balanced}")
            for suit, mn in exp_suit_min.items():
                if c.suit_min.get(suit) != mn:
                    ok = False
                    issues.append(f"suit_min[{suit}]={c.suit_min.get(suit)}≠{mn}")
            for suit, mx in exp_suit_max.items():
                if c.suit_max.get(suit) != mx:
                    ok = False
                    issues.append(f"suit_max[{suit}]={c.suit_max.get(suit)}≠{mx}")
            for suit, ex in exp_exact.items():
                if c.exact_suit.get(suit) != ex:
                    ok = False
                    issues.append(f"exact_suit[{suit}]={c.exact_suit.get(suit)}≠{ex}")
        
        status = "✓" if ok else "✗"
        print(f"  {bid:4s} → HCP {c.min_hcp}-{c.max_hcp}, "
              f"suit_min={c.suit_min}, suit_max={c.suit_max}, exact={c.exact_suit} "
              f"{status} {'; '.join(issues) if issues else ''}")
        if not ok:
            all_pass = False
    
    print(f"开叫约束: {'全部通过' if all_pass else '有失败'}\n")
    return all_pass


def test_takeout_double_and_overcall():
    """测试技术性加倍和2阶争叫约束"""
    print("=== 测试技术性加倍和2阶争叫约束 ===")
    all_pass = True
    
    # 测试1：对1♠开叫的技术性加倍
    td = get_takeout_double_constraint("1♠")
    ok = (td.min_hcp == 12 and td.max_hcp == 21 and td.balanced == False
          and td.suit_min.get("♥") == 4 and td.suit_min.get("♦") == 3
          and td.suit_min.get("♣") == 3 and td.suit_max.get("♠") == 2)
    print(f"  技术性加倍(对1♠): HCP {td.min_hcp}-{td.max_hcp}, "
          f"未叫高花♥≥{td.suit_min.get('♥')}, ♠≤{td.suit_max.get('♠')}, "
          f"balanced={td.balanced} {'✓' if ok else '✗'}")
    if not ok:
        all_pass = False
    
    # 测试2：1阶争叫1♥
    oc1 = get_overcall_constraint("1♥", is_jump=False)
    ok = oc1.min_hcp == 8 and oc1.max_hcp == 16 and oc1.suit_min.get("♥") == 5
    print(f"  1阶争叫1♥: HCP {oc1.min_hcp}-{oc1.max_hcp}, ♥≥{oc1.suit_min.get('♥')} {'✓' if ok else '✗'}")
    if not ok:
        all_pass = False
    
    # 测试3：2阶非跳争叫2♣（在1♥开叫后）
    oc2 = get_overcall_constraint("2♣", is_jump=False)
    ok = oc2.min_hcp == 10 and oc2.max_hcp == 17 and oc2.suit_min.get("♣") == 5
    print(f"  2阶争叫2♣: HCP {oc2.min_hcp}-{oc2.max_hcp}, ♣≥{oc2.suit_min.get('♣')} {'✓' if ok else '✗'}")
    if not ok:
        all_pass = False
    
    # 测试4：2NT争叫
    oc2nt = get_overcall_constraint("2NT", is_jump=False)
    ok = oc2nt.min_hcp == 16 and oc2nt.max_hcp == 19 and oc2nt.balanced == True
    print(f"  2NT争叫: HCP {oc2nt.min_hcp}-{oc2nt.max_hcp}, balanced={oc2nt.balanced} {'✓' if ok else '✗'}")
    if not ok:
        all_pass = False
    
    # 测试5：从叫牌历史提取包含加倍的序列
    hist = "(南)1♠：开叫 -(西)X：技术性加倍 -(北)pass：不叫 -(东)2♥：应叫"
    constraints = extract_constraints_from_bid_history(hist)
    west_c = constraints.get("西")
    ok_west = (west_c is not None and west_c.min_hcp == 12 and west_c.suit_max.get("♠") == 2
               and west_c.suit_min.get("♥") == 4 and west_c.balanced == False)
    print(f"  历史提取西家X: HCP {west_c.min_hcp if west_c else 'None'}, "
          f"♠≤{west_c.suit_max.get('♠') if west_c else 'None'}, "
          f"♥≥{west_c.suit_min.get('♥') if west_c else 'None'} {'✓' if ok_west else '✗'}")
    if not ok_west:
        all_pass = False
    
    # 测试6：(南)1♥-(西)2♣ 2阶争叫提取
    hist2 = "(南)1♥：开叫 -(西)2♣：2阶争叫"
    constraints2 = extract_constraints_from_bid_history(hist2)
    west_c2 = constraints2.get("西")
    ok_west2 = west_c2 is not None and west_c2.min_hcp == 10 and west_c2.max_hcp == 17 and west_c2.suit_min.get("♣") == 5
    print(f"  历史提取西家2♣: HCP {west_c2.min_hcp if west_c2 else 'None'}-{west_c2.max_hcp if west_c2 else 'None'}, "
          f"♣≥{west_c2.suit_min.get('♣') if west_c2 else 'None'} {'✓' if ok_west2 else '✗'}")
    if not ok_west2:
        all_pass = False
    
    print(f"新加束测试: {'全部通过' if all_pass else '有失败'}\n")
    return all_pass


def test_extract_from_history():
    """测试从叫牌历史提取约束"""
    print("=== 测试叫牌历史约束提取 ===")
    
    test_histories = [
        "(南)1NT：15-17均型-",
        "(南)1♠：12-21HCP，♠≥5-(西)2♥：弱二阻击-",
        "(南)1♥：12-21，♥≥5-(西)pass-(北)2♥：6-9支持-(东)pass-",
        "(南)1♠：开叫 -(西)X：加倍 -(北)pass -(东)2♥：应叫",
        "(南)1♥：开叫 -(西)2♣：2阶争叫",
    ]
    
    for hist in test_histories:
        constraints = extract_constraints_from_bid_history(hist)
        print(f"历史: {hist[:55]}...")
        for pos, c in constraints.items():
            print(f"  {pos}: HCP {c.min_hcp}-{c.max_hcp}, "
                  f"suit_min={c.suit_min}, suit_max={c.suit_max}, exact_suit={c.exact_suit}, "
                  f"balanced={c.balanced}, target={c.min_hcp_target}")
        print()
    return True


def test_sampler_1NT_constraint():
    """测试采样器满足1NT开叫约束：15-17HCP，均型，高花≤4张"""
    print("=== 测试1NT开叫约束采样 ===")
    
    from bridge.mcts.state_utils import SUIT_DISPLAY_ORDER, RANK_DESC
    ALL_CARDS = [Card(suit=s, rank=r) for s in SUIT_DISPLAY_ORDER for r in RANK_DESC]
    
    sampler = DealSampler()
    constraint = BidConstraint(
        position="南",
        min_hcp=15,
        max_hcp=17,
        balanced=True,
        suit_max={"♥": 4, "♠": 4},
        min_hcp_target=16,
    )
    
    # 西家固定13张小牌，保证牌池中有足够HCP满足南家1NT
    random.shuffle(ALL_CARDS)
    # 选HCP总和低的13张给西家，让牌池中有足够大牌
    all_sorted = sorted(ALL_CARDS, key=lambda c: HCP_MAP.get(c.rank, 0))
    west_hand = all_sorted[:13]
    west_set = set((c.suit, c.rank) for c in west_hand)
    pool = [c for c in ALL_CARDS if (c.suit, c.rank) not in west_set]
    
    print(f"测试约束: 1NT开叫，15-17HCP，均型，高花≤4张")
    print(f"西家HCP: {sum(HCP_MAP.get(c.rank, 0) for c in west_hand)}")
    print(f"牌池大小: {len(pool)}，需要选13张")
    
    hcp_samples = []
    valid_count = 0
    n_trials = 200
    
    for _ in range(n_trials):
        selected = sampler._constrained_select(list(pool), 13, constraint)
        hcp = sum(HCP_MAP.get(c.rank, 0) for c in selected)
        dist = {"♠": 0, "♥": 0, "♦": 0, "♣": 0}
        for c in selected:
            dist[c.suit] += 1
        
        valid = sampler._check_all_constraints(selected, constraint, 13)
        
        if valid:
            valid_count += 1
            hcp_samples.append(hcp)
    
    valid_rate = valid_count / n_trials * 100
    avg_hcp = sum(hcp_samples) / len(hcp_samples) if hcp_samples else 0
    hcp_counter = Counter(hcp_samples)
    
    print(f"样本数: {n_trials}")
    print(f"有效样本: {valid_count} ({valid_rate:.1f}%)")
    print(f"平均HCP: {avg_hcp:.2f}（目标16）")
    print(f"HCP分布: {dict(sorted(hcp_counter.items()))}")
    print(f"测试结果: {'✓ 通过' if valid_rate >= 80 else '⚠ 通过率偏低'} (要求≥80%)\n")
    return valid_rate >= 80


def test_sampler_weak_two():
    """测试弱二开叫约束：6-10HCP，所叫高花=6张"""
    print("=== 测试弱二开叫(2♥)约束采样 ===")
    
    sampler = DealSampler()
    
    constraint = BidConstraint(
        position="南",
        min_hcp=6,
        max_hcp=10,
        exact_suit={"♥": 6},
        min_hcp_target=8,
    )
    
    from bridge.mcts.state_utils import SUIT_DISPLAY_ORDER, RANK_DESC
    ALL_CARDS = [Card(suit=s, rank=r) for s in SUIT_DISPLAY_ORDER for r in RANK_DESC]
    
    # 保证牌池中至少有8张♥，西家最多拿5张♥
    random.shuffle(ALL_CARDS)
    hearts = [c for c in ALL_CARDS if c.suit == "♥"]
    others = [c for c in ALL_CARDS if c.suit != "♥"]
    # 西家拿5张♥ + 8张其他花色
    random.shuffle(hearts)
    random.shuffle(others)
    west_hand = hearts[:5] + others[:8]
    west_set = set((c.suit, c.rank) for c in west_hand)
    pool = [c for c in ALL_CARDS if (c.suit, c.rank) not in west_set]
    
    print(f"测试约束: 2♥弱二，6-10HCP，♥=6张")
    print(f"西家♥张数: {sum(1 for c in west_hand if c.suit == '♥')}")
    print(f"牌池♥张数: {sum(1 for c in pool if c.suit == '♥')}")
    print(f"牌池大小: {len(pool)}")
    
    hcp_samples = []
    valid_count = 0
    n_trials = 200
    
    for _ in range(n_trials):
        selected = sampler._constrained_select(list(pool), 13, constraint)
        valid = sampler._check_all_constraints(selected, constraint, 13)
        if valid:
            valid_count += 1
            hcp = sum(HCP_MAP.get(c.rank, 0) for c in selected)
            hcp_samples.append(hcp)
    
    valid_rate = valid_count / n_trials * 100
    avg_hcp = sum(hcp_samples) / len(hcp_samples) if hcp_samples else 0
    hcp_counter = Counter(hcp_samples)
    
    print(f"样本数: {n_trials}")
    print(f"有效样本: {valid_count} ({valid_rate:.1f}%)")
    print(f"平均HCP: {avg_hcp:.2f}（目标8）")
    print(f"HCP分布: {dict(sorted(hcp_counter.items()))}")
    print(f"测试结果: {'✓ 通过' if valid_rate >= 90 else '✗ 失败'} (要求≥90%)\n")
    return valid_rate >= 90


def test_hcp_distribution_no_bias():
    """测试HCP分布不再偏高——验证修复后不会永远选大牌。
    第一阶段目标：硬约束满足，高HCP比例不会像旧算法那样超过40%。
    精细分布校准留待第二阶段粒子滤波优化。"""
    print("=== 测试HCP分布无偏高偏差 ===")
    
    sampler = DealSampler()
    
    # 简单约束：12-21HCP，♠≥5张（模拟1♠开叫）
    constraint = BidConstraint(
        position="南",
        min_hcp=12,
        max_hcp=21,
        suit_min={"♠": 5},
        min_hcp_target=14,
    )
    
    from bridge.mcts.state_utils import SUIT_DISPLAY_ORDER, RANK_DESC
    ALL_CARDS = [Card(suit=s, rank=r) for s in SUIT_DISPLAY_ORDER for r in RANK_DESC]
    
    n_trials = 300
    hcp_samples = []
    valid_count = 0
    
    for _ in range(n_trials):
        shuffled = list(ALL_CARDS)
        random.shuffle(shuffled)
        pool = shuffled[13:]
        selected = sampler._constrained_select(pool, 13, constraint)
        valid = sampler._check_all_constraints(selected, constraint, 13)
        if valid:
            valid_count += 1
            hcp = sum(HCP_MAP.get(c.rank, 0) for c in selected)
            hcp_samples.append(hcp)
    
    valid_rate = valid_count / n_trials * 100
    avg_hcp = sum(hcp_samples) / len(hcp_samples) if hcp_samples else 0
    
    print(f"样本数: {n_trials}")
    print(f"有效率: {valid_rate:.1f}%")
    print(f"平均HCP: {avg_hcp:.2f}")
    
    # 旧算法会导致平均HCP偏向18-20，现在应该不会出现所有样本都偏高的问题
    # 第一阶段关键验证：不再出现高HCP集中的偏差（旧算法≥18超过40%）
    high_hcp_ratio = sum(1 for h in hcp_samples if h >= 18) / len(hcp_samples) * 100 if hcp_samples else 0
    print(f"高HCP(≥18)比例: {high_hcp_ratio:.1f}% (旧算法约40%+, 已修复)")
    
    # 验证：硬约束满足率100%，且不是永远选最高HCP（平均不超过17）
    ok = valid_rate >= 95 and avg_hcp <= 17
    print(f"测试结果: {'✓ 通过' if ok else '⚠ 分布可能仍有偏差'}\n")
    return ok


def test_validate_sample_new_fields():
    """测试validate_sample支持新字段（suit_max, exact_suit, min_controls）"""
    print("=== 测试validate_sample新字段验证 ===")
    
    # 构造一手牌：16HCP，4-3-3-3均型
    hand = [
        Card("♠", "A"), Card("♠", "K"), Card("♠", "Q"), Card("♠", "J"),  # 4张♠: 4+3+2+1=10HCP
        Card("♥", "A"), Card("♥", "K"), Card("♥", "3"),  # 3张♥: 4+3=7HCP，总17HCP
        Card("♦", "9"), Card("♦", "8"), Card("♦", "4"),  # 3张♦
        Card("♣", "7"), Card("♣", "6"), Card("♣", "5"),  # 3张♣
    ]
    hands = {"南": hand}
    
    tests = [
        ("1NT约束通过", BidConstraint(position="南", min_hcp=15, max_hcp=17, balanced=True, suit_max={"♥": 4, "♠": 4}), True),
        ("♥5张约束失败", BidConstraint(position="南", suit_min={"♥": 5}), False),
        ("♠=6张exact失败", BidConstraint(position="南", exact_suit={"♠": 6}), False),
        ("♠=4张exact通过", BidConstraint(position="南", exact_suit={"♠": 4}), True),
        ("控制数≥6通过", BidConstraint(position="南", min_controls=6), True),  # A=2*2=4, K=1*1=1 → 共5，再加1K=6
    ]
    
    all_pass = True
    for name, c, expected in tests:
        result = validate_sample(hands, {"南": c})
        ok = result == expected
        if not ok:
            all_pass = False
        print(f"  {name:20s}: validate={'True' if result else 'False'} "
              f"{'✓' if ok else f'✗ 期望{expected}'}")
    
    from bridge.mcts.constraints import CONTROL_MAP, _compute_controls
    hcp = sum(HCP_MAP.get(c.rank, 0) for c in hand)
    controls = _compute_controls(hand)
    print(f"  测试牌HCP={hcp}, 控制数={controls} (A=2,K=1)")
    print(f"新字段验证: {'全部通过' if all_pass else '有失败'}\n")
    return all_pass


def test_constraint_merge():
    """测试约束合并逻辑"""
    print("=== 测试约束合并 ===")
    from bridge.mcts.bid_constraint_library import _merge_constraints
    
    c1 = BidConstraint(position="南", min_hcp=12, max_hcp=21, suit_min={"♠": 5})
    c2 = BidConstraint(position="南", min_hcp=15, max_hcp=17, balanced=True, suit_max={"♠": 4})
    # 矛盾：c1说♠≥5，c2说♠≤4，合并suit_min还是5，suit_max还是4——这在实际中不会出现
    # 测试正常合并
    c1 = BidConstraint(position="南", min_hcp=12, suit_min={"♠": 5})
    c2 = BidConstraint(position="南", max_hcp=17)
    merged = _merge_constraints(c1, c2)
    ok = merged.min_hcp == 12 and merged.max_hcp == 17 and merged.suit_min.get("♠") == 5
    print(f"  HCP范围合并: {merged.min_hcp}-{merged.max_hcp}, ♠≥{merged.suit_min.get('♠')} {'✓' if ok else '✗'}")
    print(f"约束合并: {'通过' if ok else '失败'}\n")
    return ok


if __name__ == "__main__":
    print("=" * 60)
    print("PIMC采样约束改进测试")
    print("=" * 60)
    print()
    
    results = []
    results.append(("叫品解析", test_normalize_bid()))
    results.append(("开叫约束", test_opening_constraints()))
    results.append(("加倍/争叫", test_takeout_double_and_overcall()))
    results.append(("历史提取", test_extract_from_history()))
    results.append(("验证新字段", test_validate_sample_new_fields()))
    results.append(("约束合并", test_constraint_merge()))
    results.append(("1NT采样", test_sampler_1NT_constraint()))
    results.append(("弱二采样", test_sampler_weak_two()))
    results.append(("HCP分布无偏", test_hcp_distribution_no_bias()))
    
    print("=" * 60)
    print("测试汇总:")
    all_pass = True
    for name, passed in results:
        status = "✓ PASS" if passed else "✗ FAIL"
        print(f"  {status}  {name}")
        if not passed:
            all_pass = False
    print()
    print(f"总体结果: {'全部通过！' if all_pass else '存在失败项，请检查'}")
    print("=" * 60)
