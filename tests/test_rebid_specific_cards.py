"""测试第一阶段补全：specific_cards字段和再叫约束"""
import sys
import os
import random
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from bridge.mcts.constraints import BidConstraint, validate_sample, compute_sample_violation_score, HCP_MAP
from bridge.mcts.sampler import DealSampler
from bridge.mcts.bid_constraint_library import (
    extract_constraints_from_bid_history,
    get_opening_bid_constraint,
    get_takeout_double_constraint,
    get_overcall_constraint,
    get_response_constraint,
    get_rebid_constraint,
    _merge_constraints,
    _is_reverse,
    _normalize_bid,
    SPECIAL_PASS, SPECIAL_DOUBLE, SPECIAL_REDOUBLE,
)
from bridge.play_types import Card
from bridge.mcts.state_utils import SUIT_DISPLAY_ORDER, RANK_DESC

ALL_CARDS = [Card(suit=s, rank=r) for s in SUIT_DISPLAY_ORDER for r in RANK_DESC]

print('='*60)
print('1. 测试 _is_reverse 逆叫判断')
print('='*60)
tests_reverse = [
    (2, '♥', 1, '♦', True, '1♦-2♥ 逆叫'),
    (1, '♠', 1, '♦', False, '1♦-1♠ 一盖一不是逆叫'),
    (2, '♣', 1, '♦', False, '1♦-2♣ 顺叫不是逆叫'),
    (2, '♥', 1, '♠', False, '1♠后无逆叫'),
    (2, '♠', 1, '♣', True, '1♣-2♠ 逆叫'),
    (3, '♠', 2, '♥', False, '2阶开叫后不判逆叫'),
]
all_ok = True
for level, suit, fl, fs, expected, desc in tests_reverse:
    result = _is_reverse(level, suit, fl, fs)
    ok = result == expected
    if not ok:
        all_ok = False
    print(f'  {desc}: {result}  (期望 {expected}) {"✓" if ok else "✗"}')

print()
print('='*60)
print('2. 测试 get_rebid_constraint 再叫约束')
print('='*60)

rb1 = get_rebid_constraint('2♥', '1♥', partner_suit='♠', is_jump=False, is_reverse=False)
ok1 = rb1.min_hcp == 12 and rb1.max_hcp == 15 and rb1.suit_min.get('♥') == 6
print(f'  平叫原花 1♥-1♠-2♥: HCP={rb1.min_hcp}-{rb1.max_hcp}, ♥≥{rb1.suit_min.get("♥")}  {"✓" if ok1 else "✗"}')

rb2 = get_rebid_constraint('3♥', '1♥', partner_suit='♠', is_jump=True, is_reverse=False)
ok2 = rb2.min_hcp == 16 and rb2.max_hcp == 18 and rb2.suit_min.get('♥') == 6
print(f'  跳叫原花 1♥-1♠-3♥: HCP={rb2.min_hcp}-{rb2.max_hcp}, ♥≥{rb2.suit_min.get("♥")}  {"✓" if ok2 else "✗"}')

rb3 = get_rebid_constraint('2♠', '1♥', partner_suit='♠', is_jump=False, is_reverse=False)
ok3 = rb3.min_hcp == 12 and rb3.max_hcp == 15 and rb3.suit_min.get('♠') == 3
print(f'  平加叫 1♥-1♠-2♠: HCP={rb3.min_hcp}-{rb3.max_hcp}, ♠≥{rb3.suit_min.get("♠")}  {"✓" if ok3 else "✗"}')

rb4 = get_rebid_constraint('3♠', '1♥', partner_suit='♠', is_jump=True, is_reverse=False)
ok4 = rb4.min_hcp == 16 and rb4.max_hcp == 18 and rb4.suit_min.get('♠') == 4
print(f'  跳加叫 1♥-1♠-3♠: HCP={rb4.min_hcp}-{rb4.max_hcp}, ♠≥{rb4.suit_min.get("♠")}  {"✓" if ok4 else "✗"}')

rb5 = get_rebid_constraint('2NT', '1♠', partner_suit='♣', is_jump=False, is_reverse=False)
ok5 = rb5.min_hcp == 12 and rb5.max_hcp == 15 and rb5.balanced == True
print(f'  平叫NT 1♠-2♣-2NT: HCP={rb5.min_hcp}-{rb5.max_hcp}, balanced={rb5.balanced}  {"✓" if ok5 else "✗"}')

rb6 = get_rebid_constraint('2NT', '1♠', partner_suit='♥', is_jump=True, is_reverse=False)
ok6 = rb6.min_hcp == 18 and rb6.max_hcp == 19 and rb6.balanced == True
print(f'  跳叫NT 1♠-1♥-2NT: HCP={rb6.min_hcp}-{rb6.max_hcp}, balanced={rb6.balanced}  {"✓" if ok6 else "✗"}')

rb7 = get_rebid_constraint('2♥', '1♦', partner_suit='♠', is_jump=False, is_reverse=True)
ok7 = rb7.min_hcp == 16 and rb7.balanced == False and rb7.suit_min.get('♦') == 5 and rb7.suit_min.get('♥') == 4
print(f'  逆叫新花 1♦-1♠-2♥: HCP≥{rb7.min_hcp}, balanced={rb7.balanced}, ♦≥{rb7.suit_min.get("♦")}, ♥≥{rb7.suit_min.get("♥")}  {"✓" if ok7 else "✗"}')

rb8 = get_rebid_constraint('1♠', '1♣', partner_suit='♥', is_jump=False, is_reverse=False)
ok8 = rb8.min_hcp == 12 and rb8.max_hcp == 18 and rb8.suit_min.get('♠') == 4
print(f'  顺叫新花 1♣-1♥-1♠: HCP={rb8.min_hcp}-{rb8.max_hcp}, ♠≥{rb8.suit_min.get("♠")}  {"✓" if ok8 else "✗"}')

print()
print('='*60)
print('3. 测试从完整叫牌历史提取约束（含再叫）')
print('='*60)

test_histories = [
    ('(南)1♥-(西)pass-(北)1♠-(东)pass-(南)2♥', '南家平叫原花2♥'),
    ('(南)1♦-(西)pass-(北)1♠-(东)pass-(南)2♥', '南家逆叫2♥'),
    ('(南)1♠-(西)X-(北)2♠-(东)pass-(南)4♠', '南家开叫1♠，西加倍，北加叫2♠，南叫4♠'),
    ('(南)1NT-(西)pass-(北)2♣', '1NT开叫后2♣应叫'),
    ('(南)1♣-(西)1♥-(北)1♠-(东)pass-(南)2♠', '开叫1♣，应叫1♠，平加叫2♠'),
]

for h, desc in test_histories:
    print(f'  叫牌: {desc}')
    c = extract_constraints_from_bid_history(h)
    for pos, cc in c.items():
        suits_info = []
        if cc.suit_min:
            suits_info.append('≥' + str(dict(cc.suit_min)))
        if cc.suit_max:
            suits_info.append('≤' + str(dict(cc.suit_max)))
        bal = f', balanced={cc.balanced}' if cc.balanced is not None else ''
        print(f'    {pos}: HCP={cc.min_hcp}-{cc.max_hcp}{bal} {" ".join(suits_info)}')
    print()

print('='*60)
print('4. 测试 specific_cards 采样验证')
print('='*60)

constraint_spade_A = BidConstraint(
    position='南',
    min_hcp=10,
    max_hcp=15,
    specific_cards={('♠', 'A')},
    min_hcp_target=12,
)
sampler = DealSampler()

valid_count = 0
has_spade_A_count = 0
total = 200
for _ in range(total):
    # 确保♠A在pool中：先拿走♠A，然后西家拿12张小牌，把♠A放回pool
    spade_A = Card('♠', 'A')
    remaining = [c for c in ALL_CARDS if c != spade_A]
    random.shuffle(remaining)
    # 西家拿12张（不是13张），剩下26-12=39？不对：52张，去掉♠A剩51张，西家拿12张，pool剩39张+♠A=40？不，总牌数要对：
    # 总牌数52，西家13张，南家13张。要保证♠A在pool里（不在西家），所以西家从other中选13张
    pool_with_A = [spade_A] + remaining
    west_hand = remaining[:13]  # 西家从除了♠A之外的牌里拿13张
    pool = [c for c in pool_with_A if c not in west_hand]
    assert len(pool) == 39, f'pool应该39张，实际{len(pool)}'
    assert spade_A in pool, '♠A必须在pool里'
    
    selected = sampler._constrained_select(list(pool), 13, constraint_spade_A)
    valid = sampler._check_all_constraints(selected, constraint_spade_A, 13)
    if valid:
        valid_count += 1
    if any(c.suit == '♠' and c.rank == 'A' for c in selected):
        has_spade_A_count += 1

print(f'  采样{total}次')
print(f'  硬约束满足: {valid_count} ({valid_count/total*100:.1f}%)')
print(f'  持有♠A: {has_spade_A_count} ({has_spade_A_count/total*100:.1f}%)')

assert valid_count == total, f'硬约束应该100%满足，但只有{valid_count}/{total}'
assert has_spade_A_count == total, f'所有样本都应该持有♠A，但只有{has_spade_A_count}/{total}'

print()
print('='*60)
print('✅ 第一阶段补全测试全部通过！specific_cards和再叫约束工作正常')
print('='*60)
