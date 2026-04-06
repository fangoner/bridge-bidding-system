#!/usr/bin/env python3
"""测试 endplay 库的双明手分析功能"""

import sys

def test_endplay_installation():
    """测试 endplay 安装和基本功能"""
    try:
        import endplay
        print(f"endplay 版本: {endplay.__version__}")
        return True
    except ImportError:
        print("endplay 未安装")
        print("尝试安装: pip install endplay")
        return False

def test_dds_basic():
    """测试双明手分析基础功能"""
    try:
        from endplay import Deal
        from endplay.evaluate import dds_table
        from endplay.types import Card, Rank, Suit, Denom, Vul

        # 创建一个示例牌局
        # 使用简单的ACBL格式: "N:QJ6.K652.J85.T98 732.JT87.QT6.QJ4 K5.Q93.AK942.A76 AT984.A4.73.K532"
        deal_str = "N:QJ6.K652.J85.T98 732.JT87.QT6.QJ4 K5.Q93.AK942.A76 AT984.A4.73.K532"

        print(f"创建牌局: {deal_str}")

        try:
            deal = Deal(deal_str)
            print(f"✅ 成功创建 Deal 对象")
        except Exception as e:
            print(f"❌ 创建 Deal 对象失败: {e}")
            # 尝试手动设置手牌
            deal = Deal()
            # 设置北家的牌
            from endplay.types import Card, Rank, Suit
            # 这里需要正确设置，但先简单测试
            print("尝试手动构建牌局...")
            return False

        # 测试 dds_table 函数
        print("\n计算双明手表...")
        try:
            table = dds_table(deal)
            print(f"✅ 双明手表计算成功")
            print(f"表格类型: {type(table)}")
            print(f"表格形状（如果可用）: {getattr(table, 'shape', 'N/A')}")

            # 尝试访问数据
            try:
                # 查看数据结构
                print("\n表格数据结构示例:")
                for i, row in enumerate(table):
                    if i < 3:  # 只显示前3行
                        print(f"  行 {i}: {row}")
            except Exception as e:
                print(f"  访问数据时出错: {e}")

        except Exception as e:
            print(f"❌ dds_table 计算失败: {e}")
            import traceback
            traceback.print_exc()
            return False

        return True

    except Exception as e:
        print(f"❌ 测试过程中出错: {e}")
        import traceback
        traceback.print_exc()
        return False

def test_simple_analysis():
    """测试简单的分析功能"""
    try:
        from endplay import Deal
        from endplay.evaluate import solve_board

        # 创建一个简单牌局
        deal = Deal()
        # 这里简化测试
        print("\n测试 solve_board...")

        # 测试一个简单定约
        try:
            # 创建一个包含定约的牌局
            from endplay.types import Denom, Player
            result = solve_board(deal, Denom.hearts, Player.north)
            print(f"solve_board 结果: {result}")
        except Exception as e:
            print(f"solve_board 失败: {e}")

        return True
    except Exception as e:
        print(f"❌ 简单分析测试失败: {e}")
        return False

def main():
    """主测试函数"""
    print("=" * 60)
    print("endplay 库测试")
    print("=" * 60)

    # 测试安装
    if not test_endplay_installation():
        return

    # 测试基础功能
    print("\n" + "=" * 60)
    print("测试双明手分析基础功能")
    print("=" * 60)
    if not test_dds_basic():
        return

    # 测试简单分析
    print("\n" + "=" * 60)
    print("测试简单分析功能")
    print("=" * 60)
    test_simple_analysis()

    print("\n" + "=" * 60)
    print("测试完成")
    print("=" * 60)

if __name__ == "__main__":
    main()