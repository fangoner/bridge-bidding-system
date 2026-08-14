"""验证叫牌体系切换功能：JF vs 自然

主要差异（基于JF约定卡文档确认）：
- 一盖一应叫起点：自然6点 → pass≤5；JF5点 → pass≤4
- 1阶争叫起点：两者都是8点 → pass≤7（相同）
- 开叫起点：两者都是12点 → pass≤11（相同）
- 1NT开叫：两者都是15-17均型（相同）
- 弱二阻击：两者都是6-10点（相同）
- 2♣强开叫：两者都是22+点（相同）
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from bridge.mcts.bid_constraint_library import (
    extract_constraints_from_bid_history, SYSTEM_NATURAL, SYSTEM_JF
)

print("=" * 60)
print("叫牌体系切换验证：JF约定 vs 标准自然")
print("=" * 60)

# 场景1：同伴1♥开叫后应叫人pass（关键差异点）
print("\n--- 场景：南1♥开叫，三家pass ---")
bid_hist = "(南)1♥-(西)pass-(北)pass-(东)pass"
c_nat = extract_constraints_from_bid_history(bid_hist, system=SYSTEM_NATURAL)
c_jf = extract_constraints_from_bid_history(bid_hist, system=SYSTEM_JF)

print("标准自然体系约束:")
for pos in ["南", "西", "北", "东"]:
    c = c_nat.get(pos)
    if c:
        print(f"  {pos}家: HCP {c.min_hcp}-{c.max_hcp}  [{c.inference_source}]")

print("JF约定体系约束:")
for pos in ["南", "西", "北", "东"]:
    c = c_jf.get(pos)
    if c:
        print(f"  {pos}家: HCP {c.min_hcp}-{c.max_hcp}  [{c.inference_source}]")

# 验证：同伴开叫后应叫pass，JF阈值更紧（4 vs 5）
assert c_nat["北"].max_hcp == 5, f"自然北家应叫pass应该≤5，实际{c_nat['北'].max_hcp}"
assert c_jf["北"].max_hcp == 4, f"JF北家应叫pass应该≤4，实际{c_jf['北'].max_hcp}"
print(f"\n✓ 关键差异验证通过：北家（同伴开叫后应叫pass）自然≤{c_nat['北'].max_hcp}，JF≤{c_jf['北'].max_hcp}")
print(f"  原因：自然6点必须应叫；JF5点必须应叫（1D-1H=5点以上）")

# 场景2：第一家pass + 对方开叫，争叫位置pass（相同）
print("\n--- 场景：南pass - 西1♠开叫 - 北pass - 东2♠ ---")
bid_hist2 = "(南)pass-(西)1♠-(北)pass-(东)2♠"
c2_nat = extract_constraints_from_bid_history(bid_hist2, system=SYSTEM_NATURAL)
c2_jf = extract_constraints_from_bid_history(bid_hist2, system=SYSTEM_JF)

assert c2_nat["南"].max_hcp == 11 and c2_jf["南"].max_hcp == 11
print(f"✓ 第一家pass：自然≤{c2_nat['南'].max_hcp}，JF≤{c2_jf['南'].max_hcp}（相同，都是12点开叫）")

assert c2_nat["北"].max_hcp == 7 and c2_jf["北"].max_hcp == 7
print(f"✓ 对方开叫后争叫位置pass：自然≤{c2_nat['北'].max_hcp}，JF≤{c2_jf['北'].max_hcp}（相同，都是8点争叫）")

assert c2_nat["西"].min_hcp == 8 and c2_jf["西"].min_hcp == 8
print(f"✓ 1阶花色开叫/争叫：自然min={c2_nat['西'].min_hcp}，JFmin={c2_jf['西'].min_hcp}（相同）")

# 场景3：1NT开叫（相同）
print("\n--- 场景：南1NT开叫，三家pass ---")
bid_hist3 = "(南)1NT-(西)pass-(北)pass-(东)pass"
c3_nat = extract_constraints_from_bid_history(bid_hist3, system=SYSTEM_NATURAL)
c3_jf = extract_constraints_from_bid_history(bid_hist3, system=SYSTEM_JF)
assert c3_nat["南"].min_hcp == 15 and c3_nat["南"].max_hcp == 17
assert c3_jf["南"].min_hcp == 15 and c3_jf["南"].max_hcp == 17
print(f"✓ 1NT开叫：自然{c3_nat['南'].min_hcp}-{c3_nat['南'].max_hcp}，JF{c3_jf['南'].min_hcp}-{c3_jf['南'].max_hcp}（相同，15-17均型）")

# 验证体系来源标记
assert c_jf["南"].inference_source == "hard_coded_jf"
assert c_nat["南"].inference_source == "hard_coded_natural"
print(f"✓ 约束来源标记正确：JF={c_jf['南'].inference_source}，Natural={c_nat['南'].inference_source}")

print("\n" + "=" * 60)
print("✅ 所有体系切换验证通过！")
print("=" * 60)
print()
print("体系选择规则（已在play_service.py中实现）：")
print("  ├─ 有叫牌历史（bid_history非空）→ SYSTEM_JF（JF约定）")
print("  │   ├─ 从叫牌阶段进入打牌阶段 → 有叫牌历史，用JF")
print("  │   └─ 从历史牌例载入 → 用JF")
print("  └─ 无叫牌历史 → 返回空约束（纯随机发牌，按普通自然处理）")
print()
print("基础约定（两个体系相同）：")
print("  • 开叫: 12+HCP")
print("  • 1阶争叫: 8-16HCP，5张套")
print("  • 2阶争叫: 10-17HCP，5张套")
print("  • 1NT: 15-17HCP，均型")
print("  • 弱二开叫: 6-10HCP，6张套")
print("  • 2♣强开叫: 22+HCP")
print()
print("JF特有差异（更激进的部分）：")
print("  • 一盖一应叫: 5点起（自然6点起）")
print("  • 同伴花色开叫后pass: ≤4点（自然≤5点）")
print("  • 约定叫部分（后续第三阶段实现）:")
print("    - 1NT-2♠: 梅花套或双低花（非自然弱斯台曼）")
print("    - CAPP争叫对抗1NT（非自然争叫）")
print("    - 傀儡斯台曼等特殊约定")
