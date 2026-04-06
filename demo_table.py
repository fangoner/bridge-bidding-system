#!/usr/bin/env python3
"""演示批量双明手分析的表格输出"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from endplay_integration import analyze_all_contracts_endplay

print("演示：批量双明手分析表格输出")
print("=" * 60)

# 示例牌局
example_hands = {
    "南": "AQJT9 KQJ T9 432",
    "西": "K87 8765 AQJ 765",
    "北": "6543 A32 8765 AK",
    "东": "2 T94 432 QJT98"
}

print("示例牌局:")
for pos, hand in example_hands.items():
    print(f"  {pos}: {hand}")

print("\n进行批量双明手分析...")
result = analyze_all_contracts_endplay(example_hands)

if result["success"]:
    print("\n分析结果表格:")
    print(result["formatted_output"])

    # 解释表格
    print("\n表格说明:")
    print("- 列: 北、东、南、西 - 表示庄家位置")
    print("- 行: S(黑桃)、H(红桃)、D(方块)、C(草花)、NT(无将)")
    print("- 单元格: 最高可完成定约（如'3S'表示3♠），'-'表示无法完成任何定约")
else:
    print(f"分析失败: {result.get('error')}")

print("\n" + "=" * 60)
print("使用方法:")
print("1. 运行主程序: python main.py")
print("2. 先发牌或输入牌局（选项1-4）")
print("3. 选择选项9: '批量双明手分析（endplay）'")
print("4. 查看表格输出")