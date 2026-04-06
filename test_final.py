#!/usr/bin/env python3
"""最终测试批量分析功能"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from endplay_integration import analyze_all_contracts_endplay

print("测试1: 系统生成的手牌")
print("=" * 60)

from bridge.dealer import BridgeDealer, DealMode
dealer = BridgeDealer(DealMode.FREE)
dealer.deal()

hands_dict = {}
for position, hand in dealer.hands.items():
    hands_dict[position.value] = hand.to_simple_string()
    print(f"{position.value}: {hand.to_simple_string()}")

result = analyze_all_contracts_endplay(hands_dict)
if result["success"]:
    print("\n" + result["formatted_output"])
else:
    print(f"\n分析失败: {result.get('error')}")

print("\n\n测试2: 原始出错手牌（不完整）")
print("=" * 60)

original_hands = {
    "南": "95 K982 A653 852",
    "西": "KQT7 QJ763 K872",
    "北": "A3 AT4 QJT94 A94",
    "东": "J8642 5 KQJT763"
}

print("手牌（注意：草花不完整）:")
for pos, hand in original_hands.items():
    print(f"  {pos}: {hand}")

result2 = analyze_all_contracts_endplay(original_hands)
if result2["success"]:
    print("\n" + result2["formatted_output"])
else:
    print(f"\n分析失败（预期中）: {result2.get('error')}")

print("\n\n测试3: 完整手牌字符串")
print("=" * 60)

complete_hands = {
    "南": "AKQJ T98 765 432",
    "西": "AKQJ T98 765 432",
    "北": "AKQJ T98 765 432",
    "东": "AKQJ T98 765 432"
}

print("手牌（所有花色完整）:")
for pos, hand in complete_hands.items():
    print(f"  {pos}: {hand}")

result3 = analyze_all_contracts_endplay(complete_hands)
if result3["success"]:
    print("\n" + result3["formatted_output"])
else:
    print(f"\n分析失败: {result3.get('error')}")

print("\n所有测试完成！")