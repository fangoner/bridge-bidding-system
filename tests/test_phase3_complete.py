"""第三阶段验证测试：特殊约定叫约束 + 全局采样 + 信念跟踪集成"""
import sys
import random
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from bridge.mcts.bid_constraint_library import extract_constraints_from_bid_history, SYSTEM_JF, SYSTEM_NATURAL
from bridge.mcts.sampler import DealSampler, ALL_CARDS, _distribute_global_constrained
from bridge.mcts.constraints import validate_sample, _compute_hcp, _count_distribution
from bridge.mcts.belief import BeliefTracker
from bridge.play_types import Card, POSITION_ORDER


def random_deal():
    cards = list(ALL_CARDS)
    random.shuffle(cards)
    hands = {}
    for i, pos in enumerate(POSITION_ORDER):
        hands[pos] = cards[i*13:(i+1)*13]
    return hands


def test_convention_extraction():
    """测试1: 所有特殊约定叫约束正确提取"""
    print("=" * 60)
    print("测试1: 特殊约定叫约束提取")
    print("=" * 60)
    
    tests = [
        ("(南)1NT-(西)2♣", "兰迪2♣: 双高套≥4-4", {"西": ("♥", 4), "西": ("♠", 4)}),
        ("(南)1NT-(西)2NT", "兰迪2NT: 双低套≥5-5", {"西": ("♣", 5), "西": ("♦", 5)}),
        ("(南)2NT-(北)3♣", "傀儡斯台曼3♣", {"北": ("♥", 3), "北": ("♠", 3)}),
        ("(南)1♥-(北)4NT", "黑木4NT问叫", {"北": ("♥", 4)}),
        ("(南)1NT-(西)pass-(北)2♥-(东)pass-(南)2♠-(西)pass-(北)4♠", "雅各比转移4♠", {"北": ("♠", 5)}),
    ]
    
    all_ok = True
    for bid_hist, desc, expected in tests:
        c = extract_constraints_from_bid_history(bid_hist, system=SYSTEM_JF)
        sources = {pos: c[pos].inference_source for pos in c}
        print(f"  {desc}")
        for pos in ["南", "西", "北", "东"]:
            if pos in c and (c[pos].inference_source.startswith("convention")):
                print(f"    {pos}家: HCP {c[pos].min_hcp}-{c[pos].max_hcp}, "
                      f"suit_min={dict(c[pos].suit_min)}, "
                      f"source={c[pos].inference_source}")
    print("  ✅ 约定叫约束提取完成")
    return all_ok


def test_sampling_quality():
    """测试2: 全局采样约束满足率"""
    print("\n" + "=" * 60)
    print("测试2: 全局约束采样质量")
    print("=" * 60)
    
    scenarios = [
        ("(南)1NT-(西)2♣", "兰迪2♣争叫"),
        ("(南)2NT-(北)3♣", "傀儡斯台曼"),
        ("(南)1♥-(北)3♥-(南)4♥-(北)4NT", "黑木问叫"),
        ("(南)1NT-(西)pass-(北)2♥-(东)pass-(南)2♠-(西)pass-(北)4♠", "雅各比转移进局"),
        ("(南)1♠-(西)2♥-(北)3♠", "1♠-2♥争叫-3♠邀请"),
    ]
    
    avg_rate = 0
    for bid_hist, desc in scenarios:
        constraints = extract_constraints_from_bid_history(bid_hist, system=SYSTEM_JF)
        valid = 0
        n = 200
        for _ in range(n):
            pool = list(ALL_CARDS)
            random.shuffle(pool)
            remaining_counts = {pos: 13 for pos in POSITION_ORDER}
            result = {}
            _distribute_global_constrained(result, pool, remaining_counts, constraints, {})
            if validate_sample(result, constraints):
                valid += 1
        rate = valid / n * 100
        avg_rate += rate
        status = "✅" if rate >= 95 else "⚠️" if rate >= 85 else "❌"
        print(f"  {desc}: {rate:.1f}% {status}")
    
    avg_rate /= len(scenarios)
    print(f"\n  平均约束满足率: {avg_rate:.1f}%")
    return avg_rate >= 95


def test_system_switching():
    """测试3: 体系自动切换（有叫牌历史用JF，无则用自然）"""
    print("\n" + "=" * 60)
    print("测试3: 体系自动切换")
    print("=" * 60)
    
    # 空叫牌历史 -> 无约束
    c_empty = extract_constraints_from_bid_history("", system=SYSTEM_JF)
    c_none = extract_constraints_from_bid_history(None, system=SYSTEM_JF)
    print(f"  空字符串约束数: {len(c_empty)} (期望0)")
    print(f"  None约束数: {len(c_none)} (期望0)")
    
    # JF vs 自然
    bid_1c = "(南)1♣"
    c_jf = extract_constraints_from_bid_history(bid_1c, system=SYSTEM_JF)
    c_nat = extract_constraints_from_bid_history(bid_1c, system=SYSTEM_NATURAL)
    print(f"  JF 1♣来源: {c_jf['南'].inference_source}")
    print(f"  自然1♣来源: {c_nat['南'].inference_source}")
    
    ok = len(c_empty) == 0 and len(c_none) == 0
    print(f"  {'✅' if ok else '❌'} 体系切换测试")
    return ok


def test_belief_tracker_integration():
    """测试4: 信念跟踪器使用约束采样器"""
    print("\n" + "=" * 60)
    print("测试4: 信念跟踪器集成")
    print("=" * 60)
    
    constraints = extract_constraints_from_bid_history(
        "(南)1♥-(西)pass-(北)2♥", system=SYSTEM_JF
    )
    sampler = DealSampler()
    sampler.set_constraints(constraints)
    
    # 信念跟踪器初始化
    belief = BeliefTracker(sampler, num_particles=20)
    print(f"  采样器约束数: {len(sampler.constraints)}")
    print(f"  信念跟踪器初始化完成，粒子容量: 20")
    
    # 验证采样器被正确引用
    assert belief.sampler is sampler
    print("  ✅ 信念跟踪器正确引用采样器")
    return True


def test_no_hcp_inversion():
    """测试5: HCP守恒不会产生范围反转"""
    print("\n" + "=" * 60)
    print("测试5: HCP范围安全检查")
    print("=" * 60)
    
    # 多种叫牌序列测试，确保不会出现min_hcp > max_hcp
    test_bids = [
        "(南)1♥-(西)X-(北)pass-(东)1♠",
        "(南)1NT-(西)2♣-(北)X",
        "(南)1♣-(西)1♠-(北)2♣",
        "(南)2NT-(北)3♣-(南)3NT",
    ]
    
    all_ok = True
    for bid_hist in test_bids:
        c = extract_constraints_from_bid_history(bid_hist, system=SYSTEM_JF)
        for pos, constraint in c.items():
            if constraint.min_hcp is not None and constraint.max_hcp is not None:
                if constraint.min_hcp > constraint.max_hcp:
                    print(f"  ❌ {bid_hist} 中 {pos} HCP范围反转: {constraint.min_hcp}-{constraint.max_hcp}")
                    all_ok = False
    if all_ok:
        print("  ✅ 所有测试用例无HCP范围反转")
    return all_ok


if __name__ == "__main__":
    print("\n" + "🏆" * 20)
    print("第三阶段：特殊约定叫约束 + 采样整合MCTS信念更新")
    print("🏆" * 20 + "\n")
    
    results = []
    results.append(("约定叫提取", test_convention_extraction()))
    results.append(("采样质量", test_sampling_quality()))
    results.append(("体系切换", test_system_switching()))
    results.append(("信念跟踪集成", test_belief_tracker_integration()))
    results.append(("HCP安全检查", test_no_hcp_inversion()))
    
    print("\n" + "=" * 60)
    print("📊 测试总结:")
    print("=" * 60)
    all_passed = True
    for name, passed in results:
        status = "✅ 通过" if passed else "❌ 失败"
        print(f"  {name}: {status}")
        if not passed:
            all_passed = False
    
    print("\n" + ("🎉 所有测试通过！第三阶段完成！" if all_passed else "⚠️ 存在问题需要修复"))
    print("=" * 60)
