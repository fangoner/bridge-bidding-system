"""测试技术性加倍约束的采样满足率。"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import random
from collections import Counter
from bridge.mcts.constraints import BidConstraint, HCP_MAP
from bridge.mcts.sampler import DealSampler
from bridge.mcts.bid_constraint_library import get_takeout_double_constraint, get_overcall_constraint
from bridge.play_types import Card
from bridge.mcts.state_utils import SUIT_DISPLAY_ORDER, RANK_DESC

ALL_CARDS = [Card(suit=s, rank=r) for s in SUIT_DISPLAY_ORDER for r in RANK_DESC]
sampler = DealSampler()

# 测试1：对1♠开叫的技术性加倍约束
print("=== 测试技术性加倍(对1♠开叫)采样 ===")
constraint = get_takeout_double_constraint("1♠")
print(f"约束: HCP {constraint.min_hcp}-{constraint.max_hcp}, balanced={constraint.balanced}")
print(f"  suit_min: {constraint.suit_min}")
print(f"  suit_max: {constraint.suit_max}")
print()

random.shuffle(ALL_CARDS)
spades = [c for c in ALL_CARDS if c.suit == "♠"]
others = [c for c in ALL_CARDS if c.suit != "♠"]
south_hand = spades[:5] + others[:8]
south_set = set((c.suit, c.rank) for c in south_hand)
pool = [c for c in ALL_CARDS if (c.suit, c.rank) not in south_set]

print(f"南家♠张数: {sum(1 for c in south_hand if c.suit == '♠')}")
print(f"牌池♠张数: {sum(1 for c in pool if c.suit == '♠')}")
print(f"牌池大小: {len(pool)}")
print()

valid_count = 0
n_trials = 200
hcp_samples = []
spade_lengths = []
heart_lengths = []

for _ in range(n_trials):
    selected = sampler._constrained_select(list(pool), 13, constraint)
    valid = sampler._check_all_constraints(selected, constraint, 13)
    if valid:
        valid_count += 1
        hcp = sum(HCP_MAP.get(c.rank, 0) for c in selected)
        hcp_samples.append(hcp)
        spade_len = sum(1 for c in selected if c.suit == "♠")
        heart_len = sum(1 for c in selected if c.suit == "♥")
        spade_lengths.append(spade_len)
        heart_lengths.append(heart_len)

valid_rate = valid_count / n_trials * 100
avg_hcp = sum(hcp_samples) / len(hcp_samples) if hcp_samples else 0
avg_spade = sum(spade_lengths) / len(spade_lengths) if spade_lengths else 0
avg_heart = sum(heart_lengths) / len(heart_lengths) if heart_lengths else 0
spade_counter = Counter(spade_lengths)

print(f"样本数: {n_trials}")
print(f"有效样本: {valid_count} ({valid_rate:.1f}%)")
print(f"平均HCP: {avg_hcp:.2f}（目标14）")
print(f"平均♠张数: {avg_spade:.2f}（要求≤2）")
print(f"平均♥张数: {avg_heart:.2f}（要求≥4）")
print(f"♠张数分布: {dict(sorted(spade_counter.items()))}")
print()

# 测试2：2阶争叫2♣（对1♥开叫）
print("=== 测试2阶争叫2♣采样 ===")
constraint2 = get_overcall_constraint("2♣", is_jump=False)
print(f"约束: HCP {constraint2.min_hcp}-{constraint2.max_hcp}, suit_min={constraint2.suit_min}")
print()

random.shuffle(ALL_CARDS)
hearts = [c for c in ALL_CARDS if c.suit == "♥"]
others2 = [c for c in ALL_CARDS if c.suit != "♥"]
south_hand2 = hearts[:5] + others2[:8]
south_set2 = set((c.suit, c.rank) for c in south_hand2)
pool2 = [c for c in ALL_CARDS if (c.suit, c.rank) not in south_set2]

valid_count2 = 0
hcp_samples2 = []
club_lengths2 = []

for _ in range(n_trials):
    selected = sampler._constrained_select(list(pool2), 13, constraint2)
    valid = sampler._check_all_constraints(selected, constraint2, 13)
    if valid:
        valid_count2 += 1
        hcp = sum(HCP_MAP.get(c.rank, 0) for c in selected)
        hcp_samples2.append(hcp)
        club_len = sum(1 for c in selected if c.suit == "♣")
        club_lengths2.append(club_len)

valid_rate2 = valid_count2 / n_trials * 100
avg_hcp2 = sum(hcp_samples2) / len(hcp_samples2) if hcp_samples2 else 0
avg_club2 = sum(club_lengths2) / len(club_lengths2) if club_lengths2 else 0

print(f"有效样本: {valid_count2} ({valid_rate2:.1f}%)")
print(f"平均HCP: {avg_hcp2:.2f}（目标13）")
print(f"平均♣张数: {avg_club2:.2f}（要求≥5）")
print()

print("=" * 50)
if valid_rate >= 90 and valid_rate2 >= 90:
    print("✓ 所有新加束采样测试通过！")
else:
    print(f"⚠ 通过率: 加倍={valid_rate:.1f}%, 2♣争叫={valid_rate2:.1f}%")
