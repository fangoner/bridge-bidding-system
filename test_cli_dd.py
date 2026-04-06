#!/usr/bin/env python3
"""直接测试 CLI 的双明手分析功能"""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))

from endplay_integration import analyze_all_contracts_endplay

# 测试牌局 - 同一副牌
hands = {
    '南': '8 J98643 Q7654 6',
    '西': 'AK762 KT2 2 AQ73',
    '北': 'QJ94 5 KT98 T954',
    '东': 'T53 AQ7 AJ3 KJ82'
}

print("=" * 60)
print("CLI 双明手分析测试（使用修复后的 endplay_integration）")
print("=" * 60)
print("\n当前牌局:")
for pos, hand in hands.items():
    print(f"  {pos}: {hand}")

result = analyze_all_contracts_endplay(hands)

if result['success']:
    print(result['formatted_output'])
    print("\n关键验证 - 东西 S 定约:")
    east_s = result['results']['东']['S']
    west_s = result['results']['西']['S']
    print(f"  东 S: {east_s['contract']} (赢墩: {east_s['tricks']})")
    print(f"  西 S: {west_s['contract']} (赢墩: {west_s['tricks']})")

    if east_s['max_level'] == 5 and west_s['max_level'] == 5:
        print("\n[OK] CLI 版本修复成功！东西都可以打到 5S")
    else:
        print(f"\n[ERROR] 结果异常: 东{east_s['contract']}, 西{west_s['contract']}")
else:
    print(f"错误: {result.get('error')}")
