"""约定叫识别测试：技术性加倍应叫 + 雅各比转移叫"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from bridge.mcts.bid_constraint_library import (
    extract_constraints_from_bid_history, SYSTEM_JF,
    get_takeout_double_response_constraint,
    get_jacoby_transfer_constraint,
)

print("=" * 70)
print("约定叫识别修复验证")
print("=" * 70)

# ========== 测试1：技术性加倍后的弱应叫 ==========
print("\n--- 测试1：南1♥开叫 - 西技术性加倍 - 北pass - 东2♦弱应叫 ---")
bid_hist = "(南)1♥-(西)X-(北)pass-(东)2♦"
constraints = extract_constraints_from_bid_history(bid_hist, system=SYSTEM_JF)
for pos in ["南", "西", "北", "东"]:
    c = constraints.get(pos)
    if c:
        suit_info = ""
        if c.suit_min:
            suit_info = f", suit_min={c.suit_min}"
        print(f"  {pos}家: HCP {c.min_hcp}-{c.max_hcp}{suit_info}  [{c.inference_source}]")

# 验证东家：对加倍的2♦应叫应该是0-8HCP弱牌，♦≥4张
e = constraints["东"]
assert e.min_hcp == 0, f"东家对加倍应叫min_hcp应该是0，实际{e.min_hcp}"
assert e.max_hcp == 8, f"东家对加倍应叫max_hcp应该是8，实际{e.max_hcp}"
assert e.suit_min.get("♦") == 4, f"东家♦应该≥4张，实际{e.suit_min}"
assert "takeout_double" in e.inference_source
print("\n✓ 修复验证通过：东家2♦是对技术性加倍的弱应叫(0-8HCP，♦≥4)，不再误判为二盖一强牌(12-16HCP)")

# ========== 测试2：雅各比转移叫 2♥→2♠ ==========
print("\n--- 测试2：南1NT开叫 - 西pass - 北2♥(雅各比转移到♠) ---")
bid_hist2 = "(南)1NT-(西)pass-(北)2♥"
constraints2 = extract_constraints_from_bid_history(bid_hist2, system=SYSTEM_JF)
for pos in ["南", "西", "北"]:
    c = constraints2.get(pos)
    if c:
        suit_info = ""
        if c.suit_min:
            suit_info = f", suit_min={c.suit_min}"
        print(f"  {pos}家: HCP {c.min_hcp}-{c.max_hcp}{suit_info}  [{c.inference_source}]")

# 验证北家：2♥是转移叫，应该♠≥5张，点力0+（无强制上限，点力守恒可能给一个宽松上界）
n = constraints2["北"]
assert n.min_hcp == 0, f"北家转移叫min_hcp应该是0，实际{n.min_hcp}"
assert n.suit_min.get("♠") == 5, f"北家转移叫应该♠≥5张，实际{n.suit_min}"
assert "jacoby_transfer" in n.inference_source
# 关键点：不再误判为二盖一12+HCP，min_hcp=0说明是任意点力的转移叫
assert n.min_hcp < 12, f"转移叫不应该是强牌(min>=12)，实际min={n.min_hcp}"
print("\n✓ 修复验证通过：北家2♥是雅各比转移叫(♠≥5张，任意点力)，不再误判为二盖一强牌")

# ========== 测试3：雅各比转移叫 2♦→2♥ ==========
print("\n--- 测试3：南1NT开叫 - 西pass - 北2♦(雅各比转移到♥) ---")
bid_hist3 = "(南)1NT-(西)pass-(北)2♦"
constraints3 = extract_constraints_from_bid_history(bid_hist3, system=SYSTEM_JF)
n3 = constraints3["北"]
assert n3.suit_min.get("♥") == 5, f"北家2♦转移应该♥≥5张，实际{n3.suit_min}"
print(f"  北家2♦: HCP {n3.min_hcp}-{n3.max_hcp}, suit_min={n3.suit_min}  [{n3.inference_source}]")
print("✓ 验证通过：北家2♦转移到♥，♥≥5张")

# ========== 测试4：技术性加倍后1♠弱应叫 ==========
print("\n--- 测试4：南1♥ - 西X - 北pass - 东1♠(对加倍的1阶弱应叫) ---")
bid_hist4 = "(南)1♥-(西)X-(北)pass-(东)1♠"
constraints4 = extract_constraints_from_bid_history(bid_hist4, system=SYSTEM_JF)
e4 = constraints4["东"]
print(f"  东家1♠: HCP {e4.min_hcp}-{e4.max_hcp}, suit_min={e4.suit_min}  [{e4.inference_source}]")
assert e4.min_hcp == 0 and e4.max_hcp == 8, f"对加倍1♠应叫应该0-8HCP，实际{e4.min_hcp}-{e4.max_hcp}"
assert e4.suit_min.get("♠") == 4
print("✓ 验证通过：1♠对加倍应叫0-8HCP，♠≥4张")

# ========== 测试5：技术性加倍后1NT弱应叫 ==========
print("\n--- 测试5：南1♥ - 西X - 北pass - 东1NT ---")
bid_hist5 = "(南)1♥-(西)X-(北)pass-(东)1NT"
constraints5 = extract_constraints_from_bid_history(bid_hist5, system=SYSTEM_JF)
e5 = constraints5["东"]
print(f"  东家1NT: HCP {e5.min_hcp}-{e5.max_hcp}, balanced={e5.balanced is not None}  [{e5.inference_source}]")
assert e5.min_hcp == 6 and e5.max_hcp == 10, f"对加倍1NT应叫应该6-10HCP，实际{e5.min_hcp}-{e5.max_hcp}"
print("✓ 验证通过：1NT对加倍应叫6-10HCP，均型牌")

# ========== 测试6：点力守恒现在应该正常（东家不再是强牌） ==========
print("\n--- 测试6：修复后点力守恒验证（场景5） ---")
s = constraints["南"]
w = constraints["西"]
e = constraints["东"]
n = constraints["北"]
print(f"  南家: {s.min_hcp}-{s.max_hcp}")
print(f"  西家: {w.min_hcp}-{w.max_hcp}")
print(f"  东家: {e.min_hcp}-{e.max_hcp}")
print(f"  北家: {n.min_hcp}-{n.max_hcp}")
ns_min = (s.min_hcp or 0) + (n.min_hcp or 0)
ew_min = (w.min_hcp or 0) + (e.min_hcp or 0)
print(f"  NS总HCP下界: {ns_min}, EW总HCP下界: {ew_min}")
# 修复后：西12-21，东0-8 → EW min=12，NS可以更宽松
assert e.max_hcp == 8, "东家应该max 8HCP"
assert (w.min_hcp or 0) >= 12, "西家加倍应该min 12HCP"
print("✓ 点力守恒错误修复：东家不再被误判为强牌(12-16)，而是正确的弱应叫(0-8)")

print("\n" + "=" * 70)
print("✅ 所有约定叫识别测试通过！")
print("=" * 70)
print()
print("已修复的约定叫：")
print("  1. 对技术性加倍的应叫：0-8HCP弱应叫，不再误判为二盖一强牌")
print("     - 平叫花色: 0-8HCP, 4张套")
print("     - 1NT: 6-10HCP, 均型")
print("     - 跳叫: 9-11HCP邀请")
print("  2. 雅各比转移叫(Jacoby Transfer): 1NT-2♦/2♥")
print("     - 2♦: 转移到♥，♥≥5张，任意点力")
print("     - 2♥: 转移到♠，♠≥5张，任意点力")
print("     - 2♣斯台曼不受影响")
