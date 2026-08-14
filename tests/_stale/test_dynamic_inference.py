"""测试动态约束推断：否定推断 + 点力守恒。

演示典型叫牌序列中提取的完整约束数据，包括：
1. 第一家Pass的否定推断
2. 同伴开叫后Pass的否定推断
3. 对方开叫后争叫位置Pass的否定推断
4. 点力守恒收紧对方HCP上限
5. 完整叫牌进程的综合约束
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from bridge.mcts.bid_constraint_library import extract_constraints_from_bid_history


def print_constraints(title, constraints):
    """美观打印约束结果。"""
    print(f"\n{'='*70}")
    print(f"  {title}")
    print('='*70)
    for pos in ["南", "西", "北", "东"]:
        if pos not in constraints:
            continue
        c = constraints[pos]
        parts = []
        # HCP范围
        hcp_str = ""
        if c.min_hcp is not None and c.max_hcp is not None:
            hcp_str = f"{c.min_hcp}-{c.max_hcp}HCP"
        elif c.min_hcp is not None:
            hcp_str = f"{c.min_hcp}+HCP"
        elif c.max_hcp is not None:
            hcp_str = f"≤{c.max_hcp}HCP"
        if hcp_str:
            parts.append(hcp_str)
        # 牌型
        if c.balanced is True:
            parts.append("均型")
        elif c.balanced is False:
            parts.append("非均型")
        # 花色约束
        for suit in ["♠", "♥", "♦", "♣"]:
            if suit in c.exact_suit:
                parts.append(f"{suit}={c.exact_suit[suit]}")
            elif suit in c.suit_min and suit in c.suit_max:
                parts.append(f"{c.suit_min[suit]}≤{suit}≤{c.suit_max[suit]}")
            elif suit in c.suit_min:
                parts.append(f"{suit}≥{c.suit_min[suit]}")
            elif suit in c.suit_max:
                parts.append(f"{suit}≤{c.suit_max[suit]}")
        # 控制数
        if c.min_controls is not None:
            parts.append(f"控制≥{c.min_controls}")
        # 特定牌张
        if c.specific_cards:
            cards_str = ",".join(f"{s}{r}" for s, r in sorted(c.specific_cards))
            parts.append(f"持有{cards_str}")
        # 来源标记
        source_mark = ""
        if c.inference_source == "negative_inference":
            source_mark = " [否定推断]"
        elif c.inference_source == "hcp_conservation":
            source_mark = " [点力守恒]"
        elif c.inference_source == "hard_coded":
            source_mark = " [硬编码]"
        
        print(f"  {pos}家：{'，'.join(parts)}{source_mark}")
    print('='*70)


def test_1_first_seat_pass():
    """场景1：第一家开叫位置Pass。
    
    预期：南家≤11HCP（否定推断）
    """
    bid_history = "(南)pass-(西)1♠-(北)pass-(东)2♠-"
    constraints = extract_constraints_from_bid_history(bid_history)
    print_constraints("场景1：第一家Pass + 西1♠开叫 + 北Pass + 东2♠加叫", constraints)
    
    # 验证否定推断
    assert "南" in constraints, "南家应该有约束"
    assert constraints["南"].max_hcp == 11, f"南家应该≤11HCP，实际是{constraints['南'].max_hcp}"
    assert constraints["南"].inference_source == "negative_inference"
    print("✓ 验证通过：南家（第一家Pass）max_hcp=11，来源：否定推断")
    
    assert "北" in constraints, "北家应该有约束"
    # 北家是西家（开叫人）的下家（对方位置），属于争叫位置pass → ≤7HCP
    assert constraints["北"].max_hcp == 7, f"北家（对方1♠开叫后争叫位置Pass）应该≤7HCP，实际是{constraints['北'].max_hcp}"
    assert constraints["北"].inference_source == "negative_inference"
    print("✓ 验证通过：北家（对方开叫后争叫位置Pass）max_hcp=7，来源：否定推断")
    
    assert "东" in constraints
    # 东家是西家的同伴，2♠简单加叫：6-9HCP，♠≥3张（硬编码约束）
    assert constraints["东"].min_hcp == 6 and constraints["东"].max_hcp == 9
    assert constraints["东"].suit_min.get("♠") == 3
    print("✓ 验证通过：东家（同伴西开叫1♠后2♠加叫）6-9HCP，♠≥3张（硬编码）")


def test_2_response_to_1nt_pass():
    """场景2：1NT开叫后同伴Pass。
    
    预期：应叫人≤7HCP（Stayman/转移叫从8点开始）
    """
    bid_history = "(南)1NT-(西)pass-(北)pass-(东)pass-"
    constraints = extract_constraints_from_bid_history(bid_history)
    print_constraints("场景2：南开叫1NT，三家Pass", constraints)
    
    assert "南" in constraints
    assert constraints["南"].min_hcp == 15 and constraints["南"].max_hcp == 17
    assert constraints["南"].balanced is True
    print("✓ 验证通过：南家1NT开叫15-17HCP均型（硬编码）")
    
    assert "西" in constraints
    assert constraints["西"].max_hcp == 7, f"西家（1NT后争叫位置Pass）应该≤7HCP，实际{constraints['西'].max_hcp}"
    print(f"✓ 验证通过：西家（第二家争叫位置Pass）max_hcp={constraints['西'].max_hcp}")
    
    assert "北" in constraints
    assert constraints["北"].max_hcp == 7, f"北家（1NT后应叫Pass）应该≤7HCP，实际{constraints['北'].max_hcp}"
    assert constraints["北"].inference_source == "negative_inference"
    print("✓ 验证通过：北家（同伴1NT后Pass）max_hcp=7，来源：否定推断")


def test_3_strong_opening_hcp_conservation():
    """场景3：强2♣开叫后的点力守恒。
    
    2♣开叫≥22HCP，同伴pass<6HCP，
    则NS方总HCP≥22+0=22，EW方总HCP≤18，
    点力守恒后EW个人上限会被收紧。
    """
    bid_history = "(南)2♣-(西)pass-(北)pass-(东)pass-"
    constraints = extract_constraints_from_bid_history(bid_history)
    print_constraints("场景3：南2♣强开叫，三家Pass", constraints)
    
    assert "南" in constraints
    assert constraints["南"].min_hcp == 22
    assert constraints["南"].min_controls == 5
    print("✓ 验证通过：南家2♣强开叫≥22HCP，控制≥5（硬编码）")
    
    # 北家应叫pass <6HCP（同伴花色开叫）
    assert "北" in constraints
    assert constraints["北"].max_hcp == 5
    print("✓ 验证通过：北家（2♣后Pass）max_hcp=5（否定推断）")
    
    # 西家是第二家位置pass：对方2♣强开叫，pass的hcp_cap应该较低
    assert "西" in constraints
    print(f"  西家约束：max_hcp={constraints['西'].max_hcp}, 来源={constraints['西'].inference_source}")
    
    # 点力守恒验证：NS总min=22+0=22 → EW总max=18
    # 西和东的max_hcp应该被收紧
    west_max = constraints["西"].max_hcp if "西" in constraints else 40
    east_max = constraints["东"].max_hcp if "东" in constraints else 40
    print(f"  EW方总max上限：{west_max} + {east_max} = {west_max + east_max}（守恒应为≤18）")


def test_4_overcall_pass():
    """场景4：对方开叫后第二家（争叫位置）Pass。
    
    预期：第二家<8HCP（不够争叫）
    """
    bid_history = "(南)1♥-(西)pass-(北)1♠-(东)pass-"
    constraints = extract_constraints_from_bid_history(bid_history)
    print_constraints("场景4：南1♥开叫，西Pass，北1♠应叫，东Pass", constraints)
    
    assert "西" in constraints
    assert constraints["西"].max_hcp == 7, f"西家（争叫位置Pass）应该≤7HCP，实际{constraints['西'].max_hcp}"
    print("✓ 验证通过：西家（第二家争叫位置Pass）max_hcp=7（否定推断）")
    
    assert "北" in constraints
    assert constraints["北"].min_hcp == 6, f"北家1♠应叫应该≥6HCP，实际{constraints['北'].min_hcp}"
    assert constraints["北"].suit_min.get("♠") == 4, "北家1♠应叫应该♠≥4张"
    print("✓ 验证通过：北家1♠一盖一应叫≥6HCP，♠≥4张（硬编码）")
    
    # 东家是北家的下家（对方位置，争叫位置pass）
    assert "东" in constraints
    assert constraints["东"].max_hcp == 7
    print("✓ 验证通过：东家（对方1♠后争叫位置Pass）max_hcp=7（否定推断）")


def test_5_takeout_double_conservation():
    """场景5：技术性加倍后的点力守恒。
    
    南1♥开叫（12-21），西技术性加倍（12-21），
    双方都显示开叫实力后，点力守恒会收紧双方上限。
    
    注意：东家对技术性加倍的2♦应叫当前被简化处理为二盖一（12+HCP），
    实际约定中这通常是0-8HCP的消极应叫/自然出套，会在后续约定叫识别中修正。
    """
    bid_history = "(南)1♥-(西)X-(北)pass-(东)2♦-"
    constraints = extract_constraints_from_bid_history(bid_history)
    print_constraints("场景5：南1♥开叫，西技术加倍，北Pass，东2♦应叫", constraints)
    
    assert "南" in constraints
    assert constraints["南"].min_hcp == 12
    assert constraints["南"].suit_min.get("♥") == 5
    # 点力守恒收紧max_hcp：因为西和东都显示开叫实力，南家max被收紧
    print(f"  南家HCP范围被点力守恒收紧：12-{constraints['南'].max_hcp}HCP (原始范围12-21)")
    
    assert "西" in constraints
    assert constraints["西"].min_hcp == 12
    assert constraints["西"].balanced is False
    assert constraints["西"].suit_max.get("♥") == 2  # 开叫花色≤2张
    assert constraints["西"].suit_min.get("♠") == 4  # 未叫高花≥4张
    assert constraints["西"].suit_min.get("♦") == 3  # 未叫低花≥3张
    assert constraints["西"].suit_min.get("♣") == 3  # 未叫低花≥3张
    print("✓ 验证通过：西家技术性加倍12+HCP非均型，♥≤2张，未叫花色有支持（硬编码）")
    
    assert "北" in constraints
    # 北家在同伴南1♥开叫后pass：<6HCP（否定推断），点力守恒可能进一步收紧
    assert constraints["北"].max_hcp <= 5
    print(f"✓ 验证通过：北家（同伴1♥后Pass）max_hcp={constraints['北'].max_hcp}（否定推断+点力守恒）")
    
    assert "东" in constraints
    # 注：东家2♦当前约束是简化处理，后续约定叫识别会区分加倍后的弱应叫
    print(f"  东家2♦应叫约束：{constraints['东'].min_hcp}-{constraints['东'].max_hcp}HCP (待约定叫识别优化)")


def test_6_nt_opening_jacoby_transfer():
    """场景6：1NT开叫 + 转移叫+进局。
    
    南1NT(15-17) - 北2♥转移 - 南2♠接受 - 北4♠进局
    """
    bid_history = "(南)1NT-(西)pass-(北)2♥-(东)pass-(南)2♠-(西)pass-(北)4♠-"
    constraints = extract_constraints_from_bid_history(bid_history)
    print_constraints("场景6：南1NT - 北2♥转移 - 南2♠ - 北4♠进局", constraints)
    
    assert "南" in constraints
    print(f"  南家（1NT开叫+2♠接受转移）：{constraints['南'].min_hcp}-{constraints['南'].max_hcp}HCP")
    # 南家再叫2♠是平叫原同伴花色？不，2♥是约定叫，2♠是接受转移，会被识别为加叫同伴花色
    # 当前硬编码再叫逻辑：平加叫同伴花色12-15HCP，3张支持；但开叫人是15-17，合并后会收紧
    if "♠" in constraints["南"].suit_min:
        print(f"    ♠≥{constraints['南'].suit_min['♠']}张")
    
    assert "北" in constraints
    print(f"  北家（转移叫+4♠进局）：")
    if constraints["北"].min_hcp is not None:
        print(f"    min_hcp={constraints['北'].min_hcp}")
    # 4♠是再叫原花跳叫？16-18HCP？但转移叫后4♠是止叫，点力范围约8-14HCP
    # 这也是约定叫识别需要完善的地方，当前硬编码会给出一定约束
    
    assert "西" in constraints
    assert constraints["西"].max_hcp == 7
    print(f"✓ 西家（1NT后连续Pass）max_hcp={constraints['西'].max_hcp}（否定推断）")
    
    assert "东" in constraints
    assert constraints["东"].max_hcp == 7
    print(f"✓ 东家（争叫位置连续Pass）max_hcp={constraints['东'].max_hcp}（否定推断）")


def test_7_competitive_bidding():
    """场景7：竞争性叫牌，双方都叫牌。
    
    南1♠ - 西2♥争叫 - 北3♠邀请 - 东pass
    """
    bid_history = "(南)1♠-(西)2♥-(北)3♠-(东)pass-"
    constraints = extract_constraints_from_bid_history(bid_history)
    print_constraints("场景7：南1♠开叫，西2♥争叫，北3♠邀请，东Pass", constraints)
    
    assert "南" in constraints
    assert constraints["南"].min_hcp == 12
    assert constraints["南"].suit_min.get("♠") == 5
    print(f"✓ 南家1♠开叫：{constraints['南'].min_hcp}-{constraints['南'].max_hcp}HCP，♠≥5张")
    
    assert "西" in constraints
    assert constraints["西"].min_hcp == 10 and constraints["西"].max_hcp == 17
    assert constraints["西"].suit_min.get("♥") == 5
    print("✓ 西家2♥争叫：10-17HCP，♥≥5张（2阶争叫）")
    
    assert "北" in constraints
    assert constraints["北"].min_hcp == 10 and constraints["北"].max_hcp == 12
    assert constraints["北"].suit_min.get("♠") == 4
    print("✓ 北家3♠跳加叫：10-12HCP，♠≥4张（邀请）")
    
    assert "东" in constraints
    # 东家是同伴西家2♥争叫后的应叫位置pass，否定推断给出max_hcp
    print(f"✓ 东家（同伴2♥后Pass）max_hcp={constraints['东'].max_hcp}，来源={constraints['东'].inference_source}")


if __name__ == "__main__":
    print("\n" + "★"*70)
    print("  动态约束推断测试：否定推断 + 点力守恒")
    print("  展示叫牌序列提取的完整约束数据")
    print("★"*70)
    
    test_1_first_seat_pass()
    test_2_response_to_1nt_pass()
    test_3_strong_opening_hcp_conservation()
    test_4_overcall_pass()
    test_5_takeout_double_conservation()
    test_6_nt_opening_jacoby_transfer()
    test_7_competitive_bidding()
    
    print("\n" + "✓"*70)
    print("  所有测试场景执行完毕！")
    print("✓"*70)
