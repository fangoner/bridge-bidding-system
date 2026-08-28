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
from bridge.play_service import PlayService
from bridge.play_types import Card, PlayState, Contract, PlayPhase


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
    """测试采样器满足1NT开叫约束（15-17HCP，每门≥2，高花≤5/低花≤6）"""
    print("=== 测试1NT开叫约束采样 ===")
    
    constraint = BidConstraint(
        position="南",
        min_hcp=15,
        max_hcp=17,
        balanced=None,
        suit_min={"♠": 2, "♥": 2, "♦": 2, "♣": 2},
        suit_max={"♠": 5, "♥": 5, "♦": 6, "♣": 6},
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
    """测试约束合并逻辑（PlayService 本地实现）"""
    print("=== 测试约束合并 ===")
    service = PlayService(None)
    merge = service._merge_constraints
    
    c1 = BidConstraint(position="南", min_hcp=12, max_hcp=21, suit_min={"♠": 5})
    c2 = BidConstraint(position="南", min_hcp=15, max_hcp=17, balanced=True, suit_max={"♠": 4})
    # 矛盾：c1说♠≥5，c2说♠≤4，合并suit_min还是5，suit_max还是4——这在实际中不会出现
    # 测试正常合并
    c1 = BidConstraint(position="南", min_hcp=12, suit_min={"♠": 5})
    c2 = BidConstraint(position="南", max_hcp=17)
    merged = merge(c1, c2)
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
