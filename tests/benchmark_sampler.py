"""基准测试：测量当前采样器在不同叫牌场景下的约束满足率（使用新全局算法）"""
import sys
import random
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from bridge.mcts.bid_constraint_library import extract_constraints_from_bid_history, SYSTEM_JF
from bridge.mcts.sampler import DealSampler, ALL_CARDS, _distribute_global_constrained
from bridge.mcts.constraints import validate_sample, _compute_hcp, _count_distribution
from bridge.play_types import Card, POSITION_ORDER

def random_deal():
    """生成随机发牌，返回4家各13张"""
    cards = list(ALL_CARDS)
    random.shuffle(cards)
    hands = {}
    for i, pos in enumerate(POSITION_ORDER):
        hands[pos] = cards[i*13:(i+1)*13]
    return hands

def benchmark_scenario(name: str, bid_history: str, n_samples: int = 500):
    """测试一个场景的约束满足率"""
    print(f"\n{'='*60}")
    print(f"场景: {name}")
    print(f"叫牌: {bid_history}")
    print(f"{'='*60}")
    
    constraints = extract_constraints_from_bid_history(bid_history, system=SYSTEM_JF)
    print("提取到的约束:")
    for pos in POSITION_ORDER:
        c = constraints.get(pos)
        if not c:
            continue
        suit_info = ""
        if c.suit_min:
            suit_info += f" suit_min={c.suit_min}"
        if c.suit_max:
            suit_info += f" suit_max={c.suit_max}"
        if c.exact_suit:
            suit_info += f" exact={c.exact_suit}"
        balanced = ""
        if c.balanced is True:
            balanced = " 均型"
        elif c.balanced is False:
            balanced = " 非均型"
        print(f"  {pos}家: HCP {c.min_hcp}-{c.max_hcp}{suit_info}{balanced}  [{c.inference_source}]")
    
    # 测试纯随机发牌满足率
    valid_random = 0
    for _ in range(n_samples):
        hands = random_deal()
        if validate_sample(hands, constraints):
            valid_random += 1
    random_rate = valid_random / n_samples * 100
    print(f"\n纯随机发牌满足率: {random_rate:.1f}% ({valid_random}/{n_samples})")
    
    # 测试新全局约束采样
    valid_new = 0
    hcp_errors = 0
    shape_errors = 0
    for _ in range(n_samples):
        pool = list(ALL_CARDS)
        random.shuffle(pool)
        remaining_counts = {pos: 13 for pos in POSITION_ORDER}
        result = {}
        
        _distribute_global_constrained(result, pool, remaining_counts, constraints, {})
        
        # 验证
        if validate_sample(result, constraints):
            valid_new += 1
        else:
            # 统计错误类型
            for pos in POSITION_ORDER:
                c = constraints.get(pos)
                if not c:
                    continue
                cards = result.get(pos, [])
                h = _compute_hcp(cards)
                if c.min_hcp is not None and h < c.min_hcp:
                    hcp_errors += 1
                if c.max_hcp is not None and h > c.max_hcp:
                    hcp_errors += 1
                dist = _count_distribution(cards)
                for s, mn in c.suit_min.items():
                    if dist.get(s, 0) < mn:
                        shape_errors += 1
    
    new_rate = valid_new / n_samples * 100
    print(f"新全局约束采样满足率: {new_rate:.1f}% ({valid_new}/{n_samples})")
    if new_rate < 100:
        print(f"  失败样本中: HCP错误 {hcp_errors}次, 牌型错误 {shape_errors}次")
    
    return random_rate, new_rate

if __name__ == "__main__":
    print("=" * 70)
    print("PIMC采样器约束满足率基准测试（新全局算法 v2）")
    print("=" * 70)
    
    results = []
    
    # 场景1：简单开叫+加叫
    r = benchmark_scenario(
        "1. 南1♥ - 北2♥加叫",
        "(南)1♥-(西)pass-(北)2♥-(东)pass",
    )
    results.append(r)
    
    # 场景2：技术性加倍弱应叫
    r = benchmark_scenario(
        "2. 南1♥ - 西X - 北pass - 东2♦",
        "(南)1♥-(西)X-(北)pass-(东)2♦",
    )
    results.append(r)
    
    # 场景3：雅各比转移+进局
    r = benchmark_scenario(
        "3. 1NT - 雅各比转移 - 4♠进局",
        "(南)1NT-(西)pass-(北)2♥-(东)pass-(南)2♠-(西)pass-(北)4♠",
    )
    results.append(r)
    
    # 场景4：竞叫
    r = benchmark_scenario(
        "4. 南1♠ - 西2♥争叫 - 北3♠邀请",
        "(南)1♠-(西)2♥-(北)3♠-(东)pass",
    )
    results.append(r)
    
    # 场景5：第一家pass后开叫
    r = benchmark_scenario(
        "5. 南pass - 西1♠ - 北pass - 东2♠",
        "(南)pass-(西)1♠-(北)pass-(东)2♠",
    )
    results.append(r)
    
    print("\n" + "=" * 70)
    print("总结:")
    print(f"  {'场景':<30} {'随机满足率':>12} {'新算法满足率':>12}")
    print("  " + "-" * 58)
    names = ["1♥-2♥加叫", "加倍-弱应叫", "1NT转移进局", "1♠-2♥-3♠", "pass-1♠-2♠"]
    for i, ((nr, br), name) in enumerate(zip(results, names)):
        n_status = "✅" if nr >= 10 else ("⚠️" if nr >= 5 else "❌")
        b_status = "✅" if br >= 95 else ("⚠️" if br >= 80 else "❌")
        print(f"  {name:<30} {nr:>10.1f}% {n_status} {br:>10.1f}% {b_status}")
    
    avg_nr = sum(nr for nr, br in results) / len(results)
    avg_br = sum(br for nr, br in results) / len(results)
    print("  " + "-" * 58)
    print(f"  {'平均':<30} {avg_nr:>10.1f}%     {avg_br:>10.1f}%")
    
    print("\n目标: 约束满足率 >= 95%")
    print("=" * 70)
