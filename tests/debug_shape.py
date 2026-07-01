import sys
import random
sys.path.insert(0, '.')

from bridge.mcts.sampler import (
    _generate_valid_shape_distribution, 
    _allocate_hcp_budget, 
    _assign_cards_by_shape_and_hcp, 
    _distribute_global_constrained,
    ALL_CARDS, 
    SUITS
)
from bridge.mcts.bid_constraint_library import extract_constraints_from_bid_history, SYSTEM_JF
from bridge.mcts.constraints import validate_sample, _compute_hcp
from bridge.play_types import POSITION_ORDER

# 测试场景5：pass-1♠-2♠
bid_hist = "(南)pass-(西)1♠-(北)pass-(东)2♠"
constraints = extract_constraints_from_bid_history(bid_hist, system=SYSTEM_JF)
positions = POSITION_ORDER

print("Constraints:")
for p in positions:
    c = constraints.get(p)
    if c:
        print(f"  {p}: min_hcp={c.min_hcp} max_hcp={c.max_hcp} suit_min={c.suit_min} suit_max={c.suit_max} exact={c.exact_suit}")

print("\nTesting shape generation...")
targets = {p: 13 for p in positions}
shape = _generate_valid_shape_distribution(constraints, positions, targets)
print("Shape:", shape)
if shape:
    for p in positions:
        total = sum(shape[p].values())
        print(f"  {p}: {shape[p]} total={total}")
    for s in SUITS:
        total = sum(shape[p][s] for p in positions)
        print(f"  {s} total: {total}")

print("\nTesting HCP allocation...")
pool = list(ALL_CARDS)
random.shuffle(pool)
budgets = _allocate_hcp_budget(constraints, positions, pool=pool)
print("HCP budgets:", budgets)
total = sum(budgets.values()) if budgets else 0
pool_hcp = sum(4 for c in pool if c.rank == 'A') + sum(3 for c in pool if c.rank == 'K') + sum(2 for c in pool if c.rank == 'Q') + sum(1 for c in pool if c.rank == 'J')
print(f"Pool total HCP: {pool_hcp}, Budget total: {total}")

if shape and budgets:
    print("\nTesting card assignment...")
    result = _assign_cards_by_shape_and_hcp(pool, shape, budgets, constraints, positions)
    print("Result counts:", {p: len(v) for p,v in result.items()})
    valid = validate_sample(result, constraints)
    print("Validation:", valid)
    for p in positions:
        h = _compute_hcp(result[p])
        print(f"  {p}: HCP={h} expected={budgets[p]}")

print("\n\nTesting full _distribute_global_constrained...")
valid_count = 0
for i in range(100):
    result = {}
    pool = list(ALL_CARDS)
    random.shuffle(pool)
    remaining_counts = {p:13 for p in positions}
    _distribute_global_constrained(result, pool, remaining_counts, constraints, {})
    counts = {p: len(v) for p,v in result.items()}
    v = validate_sample(result, constraints)
    if v:
        valid_count += 1
    if i < 5:
        print(f"  Trial {i}: counts={counts} valid={v}")
        if not v:
            for p in positions:
                h = _compute_hcp(result[p])
                c = constraints.get(p)
                bad = []
                if c and c.min_hcp is not None and h < c.min_hcp:
                    bad.append(f"HCP too low ({h}<{c.min_hcp})")
                if c and c.max_hcp is not None and h > c.max_hcp:
                    bad.append(f"HCP too high ({h}>{c.max_hcp})")
                if bad:
                    print(f"    {p}: {bad}")
print(f"\nValid: {valid_count}/100 = {valid_count}%")
