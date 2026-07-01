"""完整对局模拟测试：验证三阶段改进后采样器在实际打牌中的表现
使用PlayService正确流程，每个位置使用正确的视角"""
import sys
import random
import time
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from bridge.mcts.bid_constraint_library import extract_constraints_from_bid_history, SYSTEM_JF
from bridge.mcts.sampler import DealSampler, ALL_CARDS, _distribute_global_constrained
from bridge.mcts.constraints import validate_sample, _compute_hcp
from bridge.play_service import PlayService
from bridge.play_types import (
    Card, PlayerRole, POSITION_ORDER,
)
from bridge.mcts.state_utils import cards_to_hand_str, clone_hands

try:
    from endplay import Deal as EDDeal
    from endplay.types import Denom, Player
    from endplay.dds import calc_dd_table
    ENDPLAY_AVAILABLE = True
except ImportError:
    ENDPLAY_AVAILABLE = False


class MockLLMClient:
    """模拟LLM客户端，不实际调用API"""
    def chat(self, *args, **kwargs):
        return ""
    def chat_json(self, *args, **kwargs):
        return {}


def generate_constrained_deal(constraints, max_attempts=500):
    """生成满足约束的随机发牌"""
    for _ in range(max_attempts):
        pool = list(ALL_CARDS)
        random.shuffle(pool)
        remaining_counts = {pos: 13 for pos in POSITION_ORDER}
        result = {}
        _distribute_global_constrained(result, pool, remaining_counts, constraints, known_voids={})
        if validate_sample(result, constraints):
            return result
    return None


def hands_to_dict(hands):
    """将Card列表转换为PlayService.initialize需要的字典格式"""
    result = {}
    for pos in POSITION_ORDER:
        cards = hands[pos]
        spades = ''.join(c.rank for c in cards if c.suit == '♠')
        hearts = ''.join(c.rank for c in cards if c.suit == '♥')
        diamonds = ''.join(c.rank for c in cards if c.suit == '♦')
        clubs = ''.join(c.rank for c in cards if c.suit == '♣')
        result[pos] = {
            "spades": spades,
            "hearts": hearts,
            "diamonds": diamonds,
            "clubs": clubs,
        }
    return result


def double_dummy_tricks(hands, contract_declarer, contract_suit):
    """使用双明手分析计算庄家理论得墩数"""
    if not ENDPLAY_AVAILABLE:
        return None
    try:
        deal = EDDeal()
        denom_map = {"♠": Denom.spades, "♥": Denom.hearts, "♦": Denom.diamonds, "♣": Denom.clubs, "NT": Denom.nt}
        player_map = {"南": Player.south, "西": Player.west, "北": Player.north, "东": Player.east}
        for pos in POSITION_ORDER:
            deal[player_map[pos]] = cards_to_hand_str(hands[pos])
        dd_table = calc_dd_table(deal)
        dd_tricks = dd_table[player_map[contract_declarer]][denom_map[contract_suit]]
        return dd_tricks
    except Exception:
        return None


def play_one_deal(hands, contract_str, declarer, bid_history, time_limit=2.0):
    """使用PlayService打一副牌，返回庄家实际得墩数、统计信息"""
    # 创建PlayService（使用Mock LLM避免API调用，强制使用MCTS）
    service = PlayService(llm_client=MockLLMClient())
    
    # 设置MCTS时间限制
    service.mcts.time_limit = time_limit
    
    # 初始化游戏
    hands_dict = hands_to_dict(hands)
    player_roles = {pos: PlayerRole.AI.value for pos in POSITION_ORDER}
    state = service.initialize(
        hands=hands_dict,
        contract_str=contract_str,
        declarer=declarer,
        player_roles=player_roles,
        bidding_sequence=bid_history,
        bid_history=bid_history,
    )
    
    # 提取将牌花色
    if contract_str.endswith("NT"):
        contract_suit = "NT"
    else:
        contract_suit = contract_str[-1]
    dd_tricks = double_dummy_tricks(hands, declarer, contract_suit)
    
    total_time = 0
    total_searches = 0
    
    # 打完13墩（52张牌）
    while True:
        state = service.get_state()
        if state is None:
            break
        current_pos = service.get_current_player()
        if current_pos is None:
            break
        total_tricks = state.declarer_tricks + state.defender_tricks
        if total_tricks >= 13:
            break
        
        playable = service.get_playable_cards(current_pos)
        if not playable:
            break
        
        if len(playable) == 1:
            chosen_card = playable[0]
            search_time = 0
        else:
            # 使用MCTS引擎打牌（同步调用），使用最新state
            t0 = time.time()
            result = service._mcts_play(state)
            search_time = time.time() - t0
            total_time += search_time
            total_searches += 1
            
            card_dict = result.get("card")
            if card_dict:
                chosen_card = Card(suit=card_dict["suit"], rank=card_dict["rank"])
            else:
                chosen_card = playable[0]
        
        # 执行出牌
        service.play_card(current_pos, chosen_card, is_ai=True)
    
    actual_tricks = state.declarer_tricks
    tricks_needed = state.contract.level + 6
    return {
        "actual_tricks": actual_tricks,
        "dd_tricks": dd_tricks,
        "total_time": total_time,
        "total_searches": total_searches,
        "contract_made": actual_tricks >= tricks_needed,
        "tricks_needed": tricks_needed,
    }


def run_benchmark():
    """运行完整对局基准测试"""
    print("=" * 70)
    print("🎴 完整对局模拟测试 - 三阶段改进后采样器性能验证")
    print("   使用PlayService标准流程，MCTS引擎")
    print("=" * 70)
    
    if ENDPLAY_AVAILABLE:
        print("\n✅ 检测到endplay库，将提供双明手对比数据")
    else:
        print("\n⚠️  未检测到endplay库，无双明手对比")
    
    scenarios = [
        {
            "name": "1NT开叫 - 雅各比转移4♠进局（南打4♠）",
            "bid_history": "(南)1NT-(西)pass-(北)2♥-(东)pass-(南)2♠-(西)pass-(北)4♠",
            "contract_str": "4♠",
            "declarer": "南",
        },
        {
            "name": "1♥开叫 - 2♥加叫进局（南打4♥）",
            "bid_history": "(南)1♥-(西)pass-(北)2♥-(东)pass-(南)4♥",
            "contract_str": "4♥",
            "declarer": "南",
        },
    ]
    
    num_deals_per_scenario = 4
    
    overall_stats = {
        "total_deals": 0,
        "contracts_made": 0,
        "total_actual_tricks": 0,
        "total_dd_tricks": 0,
        "total_play_time": 0,
        "total_searches": 0,
        "dd_comparison_deals": 0,
        "trick_diff_sum": 0,
    }
    
    for scenario in scenarios:
        print(f"\n{'='*70}")
        print(f"📋 场景: {scenario['name']}")
        print(f"🎯 定约: {scenario['contract_str']} by {scenario['declarer']}")
        print('='*70)
        
        constraints = extract_constraints_from_bid_history(scenario["bid_history"], system=SYSTEM_JF)
        print("\n叫牌约束已提取并应用到MCTS采样器")
        for pos in POSITION_ORDER:
            c = constraints.get(pos)
            if c:
                print(f"  {pos}家: HCP {c.min_hcp}-{c.max_hcp}, suit_min={dict(c.suit_min)}, [{c.inference_source}]")
        
        for deal_idx in range(num_deals_per_scenario):
            hands = generate_constrained_deal(constraints)
            if hands is None:
                print(f"  ❌ 第{deal_idx+1}副: 发牌生成失败")
                continue
            
            if deal_idx < 2:
                print(f"\n  🎴 第{deal_idx+1}副牌:")
                for pos in POSITION_ORDER:
                    hcp = _compute_hcp(hands[pos])
                    print(f"    {pos}家 (HCP={hcp:2d}): {cards_to_hand_str(hands[pos])}")
            
            sys.stdout.write(f"  正在打第{deal_idx+1}副...")
            sys.stdout.flush()
            
            result = play_one_deal(
                hands, scenario["contract_str"], scenario["declarer"],
                scenario["bid_history"], time_limit=2.0
            )
            
            overall_stats["total_deals"] += 1
            overall_stats["total_actual_tricks"] += result["actual_tricks"]
            overall_stats["total_play_time"] += result["total_time"]
            overall_stats["total_searches"] += result["total_searches"]
            if result["contract_made"]:
                overall_stats["contracts_made"] += 1
            
            made_str = "✅ 做成" if result["contract_made"] else "❌ 宕"
            dd_str = ""
            if result["dd_tricks"] is not None:
                overall_stats["dd_comparison_deals"] += 1
                overall_stats["total_dd_tricks"] += result["dd_tricks"]
                diff = result["actual_tricks"] - result["dd_tricks"]
                overall_stats["trick_diff_sum"] += diff
                diff_str = f"{diff:+d}" if diff != 0 else "="
                dd_str = f", 双明手={result['dd_tricks']}, 差异={diff_str}"
            
            print(f"实际得墩={result['actual_tricks']}/{result['tricks_needed']} {made_str}{dd_str}, "
                  f"搜索{result['total_searches']}次, {result['total_time']:.1f}s")
    
    print("\n" + "=" * 70)
    print("📊 总体统计")
    print("=" * 70)
    
    n = overall_stats["total_deals"]
    if n == 0:
        print("没有完成任何对局")
        return
    
    avg_tricks = overall_stats["total_actual_tricks"] / n
    avg_time = overall_stats["total_play_time"] / n
    avg_searches = overall_stats["total_searches"] / n
    made_rate = overall_stats["contracts_made"] / n * 100
    
    print(f"  完成对局数: {n}副")
    print(f"  定约做成率: {made_rate:.1f}% ({overall_stats['contracts_made']}/{n})")
    print(f"  平均庄家得墩: {avg_tricks:.2f}墩")
    print(f"  平均每局搜索: {avg_searches:.0f}次")
    print(f"  平均打牌耗时: {avg_time:.1f}秒/副")
    
    if overall_stats["dd_comparison_deals"] > 0:
        avg_dd = overall_stats["total_dd_tricks"] / overall_stats["dd_comparison_deals"]
        avg_diff = overall_stats["trick_diff_sum"] / overall_stats["dd_comparison_deals"]
        print(f"\n  📈 双明手对比（共{overall_stats['dd_comparison_deals']}副有数据）:")
        print(f"     平均双明手理论得墩: {avg_dd:.2f}墩")
        print(f"     实际与双明手差异: {avg_diff:+.2f}墩（负数表示比双明手少得墩）")
        if abs(avg_diff) <= 0.5:
            print(f"     🌟 接近双明手最优表现！")
        elif abs(avg_diff) <= 1.0:
            print(f"     👍 表现良好")
        elif abs(avg_diff) <= 2.0:
            print(f"     📝 表现中等，有改进空间")
        else:
            print(f"     ⚠️  差异较大（注：MCTS时间限制2秒，未使用DD/αμ残局搜索）")
    
    print("\n" + "=" * 70)
    print("🏁 测试完成")
    print("=" * 70)


if __name__ == "__main__":
    run_benchmark()
