#!/usr/bin/env python3
"""测试系统发牌器生成的手牌格式"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from bridge.dealer import BridgeDealer, DealMode, Position

print("测试系统发牌器")
print("=" * 60)

dealer = BridgeDealer(DealMode.FREE)
dealer.deal()

hands = dealer.hands
print("生成的手牌:")

for position in [Position.SOUTH, Position.WEST, Position.NORTH, Position.EAST]:
    hand = hands[position]
    print(f"{position.value}: {hand.to_simple_string()}")
    # 跳过显示格式（包含Unicode字符）
    # print(f"  显示格式: {hand.to_display_string()}")
    print(f"  分布: {hand.distribution}")
    print(f"  HCP: {hand.hcp}")
    print()

# 检查总牌数
total_cards = 0
suit_counts = {"S": 0, "H": 0, "D": 0, "C": 0}

for position, hand in hands.items():
    total_cards += len(hand.spades) + len(hand.hearts) + len(hand.diamonds) + len(hand.clubs)
    suit_counts["S"] += len(hand.spades)
    suit_counts["H"] += len(hand.hearts)
    suit_counts["D"] += len(hand.diamonds)
    suit_counts["C"] += len(hand.clubs)

print(f"总牌数: {total_cards} (应该为52)")
print(f"花色分布: S={suit_counts['S']}, H={suit_counts['H']}, D={suit_counts['D']}, C={suit_counts['C']}")

# 测试转换为PBN
from endplay_integration import convert_hand_to_pbn

hands_dict = {pos.value: hand.to_simple_string() for pos, hand in hands.items()}
print("\n转换为PBN:")
try:
    pbn = convert_hand_to_pbn(hands_dict)
    print(f"PBN字符串: {pbn}")

    # 测试endplay解析
    from endplay import Deal
    deal = Deal(pbn)
    print("[成功] Deal对象创建成功")

    # 测试批量分析
    from endplay_integration import analyze_all_contracts_endplay
    result = analyze_all_contracts_endplay(hands_dict)
    if result["success"]:
        print("[成功] 批量分析完成")
        print(result["formatted_output"])
    else:
        print(f"[失败] 批量分析失败: {result.get('error')}")
except Exception as e:
    print(f"[失败] {e}")
    import traceback
    traceback.print_exc()