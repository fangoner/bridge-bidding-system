#!/usr/bin/env python3
"""测试手牌格式修复"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

# 测试修复后的转换函数
from endplay_integration import convert_hand_to_pbn, analyze_all_contracts_endplay

# 之前出错的手牌
example_hands = {
    "南": "95 K982 A653 852",
    "西": "KQT7 QJ763 K872",
    "北": "A3 AT4 QJT94 A94",
    "东": "J8642 5 KQJT763"  # 只有3个花色
}

print("测试手牌格式转换")
print("=" * 60)

# 测试convert_hand_to_pbn
try:
    pbn_str = convert_hand_to_pbn(example_hands)
    print(f"生成的PBN字符串: {pbn_str}")

    # 测试是否可以被endplay解析
    try:
        from endplay import Deal
        deal = Deal(pbn_str)
        print(f"✅ 成功创建Deal对象")
        print(f"北: {deal.north}")
        print(f"东: {deal.east}")
        print(f"南: {deal.south}")
        print(f"西: {deal.west}")

        # 测试批量分析
        print("\n测试批量分析...")
        result = analyze_all_contracts_endplay(example_hands)
        if result["success"]:
            print("✅ 批量分析成功")
            print(result["formatted_output"])
        else:
            print(f"❌ 批量分析失败: {result.get('error')}")
            if "traceback" in result:
                print(f"错误详情: {result['traceback']}")

    except ImportError as e:
        print(f"❌ endplay导入失败: {e}")
    except Exception as e:
        print(f"❌ Deal创建失败: {e}")
        import traceback
        traceback.print_exc()

except Exception as e:
    print(f"❌ convert_hand_to_pbn失败: {e}")
    import traceback
    traceback.print_exc()

# 测试其他手牌格式
print("\n\n测试其他手牌格式")
print("=" * 60)

test_cases = [
    {
        "描述": "完整4个花色",
        "手牌": {
            "南": "AKQJ T98 765 432",
            "西": "AKQJ T98 765 432",
            "北": "AKQJ T98 765 432",
            "东": "AKQJ T98 765 432"
        }
    },
    {
        "描述": "缺少最后一个花色",
        "手牌": {
            "南": "AKQJ T98 765",
            "西": "AKQJ T98 765",
            "北": "AKQJ T98 765",
            "东": "AKQJ T98 765"
        }
    },
    {
        "描述": "使用'-'表示空花色",
        "手牌": {
            "南": "AKQJ - 765 432",
            "西": "AKQJ T98 - 432",
            "北": "AKQJ T98 765 -",
            "东": "- T98 765 432"
        }
    }
]

for test in test_cases:
    print(f"\n测试: {test['描述']}")
    try:
        pbn = convert_hand_to_pbn(test['手牌'])
        print(f"  PBN: {pbn}")

        from endplay import Deal
        deal = Deal(pbn)
        print(f"  ✅ Deal创建成功")
    except Exception as e:
        print(f"  ❌ 失败: {e}")