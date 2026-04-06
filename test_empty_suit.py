#!/usr/bin/env python3
"""测试endplay的空花色表示"""

from endplay import Deal

def test_empty_suit_formats():
    """测试不同的空花色表示方法"""
    print("测试endplay的空花色表示")
    print("=" * 60)

    # 测试用例：东家手牌缺少草花，其他正常
    test_cases = [
        # (描述, PBN字符串)
        ("完全省略最后一个花色（无末尾点号）",
         "N:A3.AT4.QJT94.A94 J8642.5.KQJT763 95.K982.A653.852 KQT7.QJ763.K872"),

        ("省略最后一个花色（有点号但无内容）",
         "N:A3.AT4.QJT94.A94 J8642.5.KQJT763. 95.K982.A653.852 KQT7.QJ763.K872"),

        ("使用空字符串作为花色",
         "N:A3.AT4.QJT94.A94 J8642.5.KQJT763. 95.K982.A653.852 KQT7.QJ763.K872."),

        ("缺少中间花色（红桃空）",
         "N:A3.AT4.QJT94.A94 J8642..KQJT763. 95.K982.A653.852 KQT7.QJ763.K872"),

        ("缺少中间花色（红桃空，使用点号分隔）",
         "N:A3.AT4.QJT94.A94 J8642..KQJT763 95.K982.A653.852 KQT7.QJ763.K872"),

        ("使用'-'作为空花色",
         "N:A3.AT4.QJT94.A94 J8642.5.KQJT763.- 95.K982.A653.852 KQT7.QJ763.K872.-"),
    ]

    for desc, pbn in test_cases:
        print(f"\n测试: {desc}")
        print(f"PBN: {pbn}")
        try:
            deal = Deal(pbn)
            print("  [成功] 创建Deal对象")
            # 显示手牌确认
            print(f"  北: {deal.north}")
            print(f"  东: {deal.east}")
            print(f"  南: {deal.south}")
            print(f"  西: {deal.west}")
        except Exception as e:
            print(f"  [失败] {e}")

def test_hand_to_string():
    """测试Deal对象如何表示手牌"""
    print("\n\n测试Deal对象的手牌字符串表示")
    print("=" * 60)

    # 创建一个有空白花色的牌局
    pbn = "N:A3.AT4.QJT94.A94 J8642.5.KQJT763 95.K982.A653.852 KQT7.QJ763.K872"
    deal = Deal(pbn)

    print(f"原始PBN: {pbn}")
    print(f"北手牌字符串: {deal.north}")
    print(f"东手牌字符串: {deal.east}")
    print(f"南手牌字符串: {deal.south}")
    print(f"西手牌字符串: {deal.west}")

    # 检查手牌对象的内部表示
    print("\n检查手牌对象类型:")
    print(f"北手牌类型: {type(deal.north)}")
    print(f"东手牌类型: {type(deal.east)}")

    # 尝试转换为字符串
    print(f"\n东家手牌.to_string(): {deal.east.to_string()}")
    print(f"东家手牌.__str__(): {str(deal.east)}")
    print(f"东家手牌.__repr__(): {repr(deal.east)}")

if __name__ == "__main__":
    test_empty_suit_formats()
    test_hand_to_string()