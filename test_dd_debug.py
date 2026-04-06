#!/usr/bin/env python3
"""调试双明手分析，检查行列映射"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

try:
    from endplay import Deal
    from endplay.dds import calc_dd_table
    from endplay.types import Denom, Player
    ENDPLAY_AVAILABLE = True
except ImportError:
    print("endplay 未安装")
    sys.exit(1)

# 测试牌局
hands = {
    "南": "8 J98643 Q7654 6",
    "西": "AK762 KT2 2 AQ73",
    "北": "QJ94 5 KT98 T954",
    "东": "T53 AQ7 AJ3 KJ82"
}

print("测试牌局:")
for pos, hand in hands.items():
    print(f"  {pos}: {hand}")

# 转换为 PBN
from endplay_integration import convert_hand_to_pbn
pbn = convert_hand_to_pbn(hands)
print(f"\nPBN: {pbn}")

# 创建 Deal
deal = Deal(pbn)
print(f"\nDeal 对象创建成功")

# 计算双明手表
table = calc_dd_table(deal)
table_list = table.to_list()

print(f"\n原始双明手表 (to_list()):")
print(f"类型: {type(table_list)}")
print(f"形状: {len(table_list)} x {len(table_list[0]) if table_list else 0}")

print(f"\n完整表格数据:")
for i, row in enumerate(table_list):
    print(f"  行 {i}: {row}")

# 检查 endplay 的 Denom 和 Player 顺序
print(f"\nendplay Denom 顺序: {list(Denom)}")
print(f"endplay Player 顺序: {list(Player)}")

# 尝试直接访问表格
try:
    print(f"\n直接访问 table[Denom.spades][Player.east]:")
    print(f"  S 东: {table[Denom.spades][Player.east]}")
    print(f"  S 西: {table[Denom.spades][Player.west]}")
    print(f"  H 东: {table[Denom.hearts][Player.east]}")
    print(f"  NT 东: {table[Denom.nt][Player.east]}")
except Exception as e:
    print(f"  错误: {e}")

# 验证东西 S 配合
east_s = "T53"
west_s = "AK762"
print(f"\n东西 S 配合:")
print(f"  西: {west_s} ({len(west_s)}张)")
print(f"  东: {east_s} ({len(east_s)}张)")
print(f"  合计: {len(west_s) + len(east_s)}张")
print(f"  西家牌力: AK762 = 15点")
print(f"  东家牌力: T53 = 3点")
print(f"  联手: 18点 + 8张S")
