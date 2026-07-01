"""测试兰迪约定和其他特殊约定叫的约束提取"""
import sys
sys.path.insert(0, '.')

from bridge.mcts.bid_constraint_library import extract_constraints_from_bid_history, SYSTEM_JF, SYSTEM_NATURAL

def test_landy():
    """测试兰迪约定（对抗1NT开叫争叫）"""
    print("=" * 60)
    print("测试1: 南1NT - 西2♣ 兰迪约定（双高套）")
    print("=" * 60)
    bid = "(南)1NT-(西)2♣"
    constraints = extract_constraints_from_bid_history(bid, system=SYSTEM_JF)
    for pos, c in constraints.items():
        print(f"  {pos}家: HCP {c.min_hcp}-{c.max_hcp}, suits={dict(c.suit_min)}, 来源={c.inference_source}")
    
    print("\n" + "=" * 60)
    print("测试2: 南1NT - 西2♥ 自然争叫（♥≥5张）")
    print("=" * 60)
    bid = "(南)1NT-(西)2♥"
    constraints = extract_constraints_from_bid_history(bid, system=SYSTEM_JF)
    for pos, c in constraints.items():
        print(f"  {pos}家: HCP {c.min_hcp}-{c.max_hcp}, suits={dict(c.suit_min)}, 来源={c.inference_source}")
    
    print("\n" + "=" * 60)
    print("测试3: 南1NT - 西2NT 不寻常无将（双低套）")
    print("=" * 60)
    bid = "(南)1NT-(西)2NT"
    constraints = extract_constraints_from_bid_history(bid, system=SYSTEM_JF)
    for pos, c in constraints.items():
        print(f"  {pos}家: HCP {c.min_hcp}-{c.max_hcp}, suits={dict(c.suit_min)}, 来源={c.inference_source}")
    
    print("\n" + "=" * 60)
    print("测试4: 南2NT - 北3♣ 傀儡斯台曼")
    print("=" * 60)
    bid = "(南)2NT-(西)pass-(北)3♣"
    constraints = extract_constraints_from_bid_history(bid, system=SYSTEM_JF)
    for pos, c in constraints.items():
        print(f"  {pos}家: HCP {c.min_hcp}-{c.max_hcp}, suits={dict(c.suit_min)}, 来源={c.inference_source}")
    
    print("\n" + "=" * 60)
    print("测试5: 南1♥ - 北4NT 黑木问叫")
    print("=" * 60)
    bid = "(南)1♥-(西)pass-(北)3♥-(东)pass-(南)4♥-(西)pass-(北)4NT"
    constraints = extract_constraints_from_bid_history(bid, system=SYSTEM_JF)
    for pos, c in constraints.items():
        print(f"  {pos}家: HCP {c.min_hcp}-{c.max_hcp}, suits={dict(c.suit_min)}, 来源={c.inference_source}")
    
    print("\n" + "=" * 60)
    print("测试6: 体系选择 - 空叫牌历史返回空约束（自然随机）")
    print("=" * 60)
    constraints_empty = extract_constraints_from_bid_history("", system=SYSTEM_NATURAL)
    print(f"  空字符串约束数: {len(constraints_empty)} (期望0)")
    
    constraints_none = extract_constraints_from_bid_history(None, system=SYSTEM_NATURAL)
    print(f"  None约束数: {len(constraints_none)} (期望0)")
    
    print("\n" + "=" * 60)
    print("测试7: 有叫牌历史用JF，无叫牌历史用自然")
    print("=" * 60)
    bid_natural = "(南)1NT-(西)pass-(北)2♣"
    constraints_jf = extract_constraints_from_bid_history(bid_natural, system=SYSTEM_JF)
    constraints_nat = extract_constraints_from_bid_history(bid_natural, system=SYSTEM_NATURAL)
    print(f"  JF体系2♣: {[(p, c.inference_source) for p, c in constraints_jf.items()]}")
    print(f"  自然体系2♣: {[(p, c.inference_source) for p, c in constraints_nat.items()]}")
    
    print("\n✅ 所有约定叫约束提取测试完成!")

if __name__ == "__main__":
    test_landy()
