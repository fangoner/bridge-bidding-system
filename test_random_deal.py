#!/usr/bin/env python3
"""测试随机牌局的批量分析"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from endplay import Deal
from endplay_integration import analyze_all_contracts_endplay

print("测试随机牌局的批量分析")
print("=" * 60)

# 创建一个随机牌局
deal = Deal()
deal.shuffle()  # 随机发牌
print("随机牌局:")
print(f"北: {deal.north}")
print(f"东: {deal.east}")
print(f"南: {deal.south}")
print(f"西: {deal.west}")

# 转换为项目手牌格式
hands_dict = {
    "北": str(deal.north),
    "东": str(deal.east),
    "南": str(deal.south),
    "西": str(deal.west)
}

print("\n转换为项目格式:")
for pos, hand in hands_dict.items():
    print(f"  {pos}: {hand}")

# 测试批量分析
print("\n进行批量分析...")
result = analyze_all_contracts_endplay(hands_dict)

if result["success"]:
    print("[成功] 批量分析完成")
    print(result["formatted_output"])
else:
    print(f"[失败] 批量分析失败: {result.get('error')}")
    if "traceback" in result:
        print(f"错误详情: {result['traceback']}")

# 测试直接使用Deal对象
print("\n\n测试直接使用Deal对象...")
result2 = analyze_all_contracts_endplay(deal)
if result2["success"]:
    print("[成功] 使用Deal对象分析完成")
else:
    print(f"[失败] 使用Deal对象分析失败: {result2.get('error')}")