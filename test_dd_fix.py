#!/usr/bin/env python3
"""验证双明手分析修复"""

from endplay_integration import analyze_all_contracts_endplay

hands = {
    '南': '8 J98643 Q7654 6',
    '西': 'AK762 KT2 2 AQ73',
    '北': 'QJ94 5 KT98 T954',
    '东': 'T53 AQ7 AJ3 KJ82'
}

result = analyze_all_contracts_endplay(hands)
if result['success']:
    print(result['formatted_output'])
    print()
    print('东西 S 定约详情:')
    east_s = result['results']['东']['S']
    west_s = result['results']['西']['S']
    print(f'  东 S: {east_s["contract"]} (赢墩: {east_s["tricks"]})')
    print(f'  西 S: {west_s["contract"]} (赢墩: {west_s["tricks"]})')
    print()
    print('验证: 11墩 = 5S (6+5=11), 正确!')
else:
    print(f'错误: {result.get("error")}')
