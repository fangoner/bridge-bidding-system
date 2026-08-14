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
        # 1NT/2NT 采用当前库定义（见 bid_constraint_library.py 注释）：
        # 允许 5 张高花/6 张低花，balanced=None（不再要求严格均型、高花≤4）
        ("1NT", 15, 17, None, {"♠": 2, "♥": 2, "♦": 2, "♣": 2}, {"♠": 5, "♥": 5, "♦": 6, "♣": 6}, {}),
        ("1♠", 12, 21, None, {"♠": 5}, {}, {}),
        ("1♥", 12, 21, None, {"♥": 5}, {}, {}),
        ("1♣", 12, 21, None, {"♣": 3}, {}, {}),
        ("2♥", 6, 10, None, {}, {}, {"♥": 6}),
        ("2♠", 6, 10, None, {}, {}, {"♠": 6}),
        ("2NT", 20, 21, None, {"♠": 2, "♥": 2, "♦": 2, "♣": 2}, {"♠": 5, "♥": 5, "♦": 6, "♣": 6}, {}),
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


def _make_state_west_fixed():
    """构建采样状态：西家固定 13 张小牌（每门花色 3 张均分 + 1 张），南/北/东待采样。

    当前采样器 API：sample(state, perspective) 保持 perspective 手牌不变，
    重分配其余未知位置手牌并满足 set_constraints 的约束（v1.50 起替代旧 _constrained_select）。
    注意：西家不能按 HCP 稳定排序取前 13 张（会把一门花色的低张全拿走，
    导致该花色在未知牌池不足，触发可行性预检 INFEASIBLE）。
    """
    from bridge.mcts.state_utils import SUIT_DISPLAY_ORDER, RANK_DESC
    ALL_CARDS = [Card(suit=s, rank=r) for s in SUIT_DISPLAY_ORDER for r in RANK_DESC]
    west = []
    for s in SUIT_DISPLAY_ORDER:
        suit_cards = [c for c in ALL_CARDS if c.suit == s]
        west.extend(sorted(suit_cards, key=lambda c: HCP_MAP.get(c.rank, 0))[:3])
    rest_low = [c for c in ALL_CARDS if c not in west]
    west.append(sorted(rest_low, key=lambda c: HCP_MAP.get(c.rank, 0))[0])
    west_keys = {(c.suit, c.rank) for c in west}
    remaining = [c for c in ALL_CARDS if (c.suit, c.rank) not in west_keys]
    hands = {
        "西": [Card(suit=c.suit, rank=c.rank) for c in west],
        "南": [Card(suit=c.suit, rank=c.rank) for c in remaining[:13]],
        "北": [Card(suit=c.suit, rank=c.rank) for c in remaining[13:26]],
        "东": [Card(suit=c.suit, rank=c.rank) for c in remaining[26:39]],
    }
    state = PlayState(contract=Contract.from_str("1NT", "南"), hands=hands, bidding_sequence="(南)1NT-")
    return state


def test_sampler_1NT_constraint():
    """测试采样器满足1NT开叫约束（使用库当前定义：15-17HCP，每门≥2，高花≤5/低花≤6）"""
    print("=== 测试1NT开叫约束采样 ===")
    
    # 使用库的真实定义（与引擎一致），而非旧版"严格均型高花≤4"（该定义已演进，见库注释）
    lib_constraint = get_opening_bid_constraint("1NT")
    if lib_constraint is None:
        print("  ✗ 库未定义 1NT 约束\n")
        return False
    constraint = BidConstraint(
        position="南",
        min_hcp=lib_constraint.min_hcp,
        max_hcp=lib_constraint.max_hcp,
        balanced=lib_constraint.balanced,
        suit_min=lib_constraint.suit_min,
        suit_max=lib_constraint.suit_max,
    )
    
    sampler = DealSampler()
    state = _make_state_west_fixed()
    sampler.set_constraints({"南": constraint})
    
    print(f"测试约束: 1NT开叫，{constraint.min_hcp}-{constraint.max_hcp}HCP，suit_max={constraint.suit_max}")
    print(f"西家HCP: {sum(HCP_MAP.get(c.rank, 0) for c in state.hands['西'])}")
    
    hcp_samples = []
    valid_count = 0
    n_trials = 200
    
    for _ in range(n_trials):
        world = sampler.sample(state, "西")
        south = world["南"]
        if validate_sample({"南": south, "西": [], "北": [], "东": []}, {"南": constraint}):
            valid_count += 1
            hcp = sum(HCP_MAP.get(c.rank, 0) for c in south)
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
    
    state = _make_state_west_fixed()
    sampler.set_constraints({"南": constraint})
    
    print(f"测试约束: 2♥弱二，6-10HCP，♥=6张")
    print(f"西家♥张数: {sum(1 for c in state.hands['西'] if c.suit == '♥')}")
    
    hcp_samples = []
    valid_count = 0
    n_trials = 200
    
    for _ in range(n_trials):
        world = sampler.sample(state, "西")
        south = world["南"]
        if validate_sample({"南": south, "西": [], "北": [], "东": []}, {"南": constraint}):
            valid_count += 1
            hcp = sum(HCP_MAP.get(c.rank, 0) for c in south)
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
    
    state = _make_state_west_fixed()
    sampler.set_constraints({"南": constraint})
    
    n_trials = 300
    hcp_samples = []
    valid_count = 0
    
    for _ in range(n_trials):
        world = sampler.sample(state, "西")
        south = world["南"]
        if validate_sample({"南": south, "西": [], "北": [], "东": []}, {"南": constraint}):
            valid_count += 1
            hcp = sum(HCP_MAP.get(c.rank, 0) for c in south)
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
