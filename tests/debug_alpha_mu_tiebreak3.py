"""αμ tie-break 验证：全宕场景下 avg_tricks 能否区分宕几"""
import sys
import time
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from bridge.play_service import PlayService
from bridge.play_types import Card, PlayerRole, POSITION_ORDER
from bridge.mcts.alpha_mu import AlphaMuSearch
from bridge.mcts.sampler import DealSampler


class MockLLMClient:
    def chat(self, *args, **kwargs):
        return ""
    def chat_json(self, *args, **kwargs):
        return {}


def build_test_state(hands_cards, declarer, contract_str, current_player,
                     decl_tricks=0, def_tricks=0):
    """构造测试用 PlayState"""
    service = PlayService(llm_client=MockLLMClient())
    hands_dict = {}
    for pos in POSITION_ORDER:
        cards = hands_cards.get(pos, [])
        spades = ''.join(c.rank for c in cards if c.suit == '♠')
        hearts = ''.join(c.rank for c in cards if c.suit == '♥')
        diamonds = ''.join(c.rank for c in cards if c.suit == '♦')
        clubs = ''.join(c.rank for c in cards if c.suit == '♣')
        hands_dict[pos] = {"spades": spades, "hearts": hearts, "diamonds": diamonds, "clubs": clubs}

    player_roles = {pos: PlayerRole.AI.value for pos in POSITION_ORDER}
    state = service.initialize(
        hands=hands_dict,
        contract_str=contract_str,
        declarer=declarer,
        player_roles=player_roles,
        bidding_sequence="",
        bid_history="",
    )

    state.current_player = current_player
    state.declarer_tricks = decl_tricks
    state.defender_tricks = def_tricks
    return service, state


def test_all_down_scenario():
    """全宕场景：大满贯定约，肯定宕，看不同出牌宕几"""
    print("=" * 70)
    print("🔍 测试：全宕场景下 avg_tricks tie-break")
    print("=" * 70)

    # 南打 7♠（大满贯，需 13 墩）
    # 剩 4 张牌，庄家已赢 9 墩 → 最多再赢 4 墩 = 13 墩
    # 但防守方有 ♠A（确定的 1 个将牌赢墩），所以肯定宕
    #
    # 南家：♠KQ ♥AK  （2将牌（缺A） + 2红桃赢墩）
    # 北家：♠JT ♥QJ  （2小将 + 2红桃）
    # 西家：♠A ♥T ♦AK （♠A = 1个将牌赢墩 + ♦AK = 2个方块赢墩）
    # 东家：♠9 ♦QJT ♣A （杂牌）
    #
    # 当前出牌：南家
    # 分析（理想双明手）：
    # - 出 ♠K：被 ♠A 吃。之后庄家只能拿 ♠Q + ♥AK = 3 墩（共 12，宕1）
    #   不对，还要考虑防守方的 ♦AK。如果防守方拿到出牌权，还能拿方块赢墩
    #
    # 让我简化：只有 3 张牌，防守方有 1 个确定赢墩，还有 1 个可能赢墩
    # 南打 7♠，剩 3 张，已赢 9 墩（需 13，还需 4 → 至少宕1）
    # 南家：♠K ♥AK  （1将 + 2红桃赢墩）
    # 北家：♠QJ ♥Q  （2小将 + 1红桃）
    # 西家：♠A ♥T ♦A  （♠A = 确定赢墩 + ♦A = 可能赢墩）
    # 东家：♠T ♦KJ ♣A  （杂牌）
    #
    # 不对，3张牌每人3张 = 12张 = 3墩
    # 防守方有 ♠A 和 ♦A = 2个顶张
    # 但 ♦A 能不能兑现要看有没有出牌权

    # 为了构造一个"不同出牌导致不同宕墩数"的场景，
    # 关键是：庄家的选择影响"防守方能拿到几个赢墩"
    #
    # 经典场景：飞牌 vs 敲落
    # 南打 7♠，剩 4 张，已赢 9 墩
    # 南家有 ♠AKQ ♥A （3将 + 1红桃）
    # 北家有 ♠JT ♥KQ  （2小将 + 2红桃）
    # 西家有 ♠9 ♥JT ♦A  （小将 + 红桃 + ♦A）
    # 东家有 ♥9 ♦KQJ ♣A  （杂牌）
    #
    # 当前出牌：南家
    # 分析：
    # - 出 ♠A：清将，然后 ♠KQ + ♥A = 4 墩全拿（共 13，铁成）— 不对，这是铁成

    # 要构造全宕，防守方必须有一个不可避免的赢墩
    # 同时不同出牌影响"庄家还能拿几墩"

    # 场景：南打 7NT，剩 4 张，已赢 9 墩
    # 南家：♠AKQ ♥Q  （黑桃 AKQ = 3 赢墩 + 红桃 Q）
    # 北家：♠JT9 ♥A  （小黑桃 + 红桃 A）
    # 西家：♠87 ♥KJ ♦A  （♦A = 1 确定赢墩 + 红桃 K）
    # 东家：♥65 ♥T9 ♦KQJ  （杂牌）
    #
    # 等等，7NT需13墩，已赢9墩，还需4墩
    # 防守方有 ♦A = 至少能拿1墩 = 庄家最多拿 3 墩（共 12，宕1）
    # 但是... 怎么让不同出牌导致宕1 vs 宕2？

    # 答案：当庄家出一张牌，可能让防守方获得出牌权，
    # 防守方拿到出牌权后就能兑现他们的赢墩
    #
    # 场景：南打 7NT，剩 4 张，已赢 9 墩
    # 南家（庄家）出牌
    # 南家：♠AKQ ♦Q  （♠AKQ = 3赢墩 + ♦Q）
    # 北家：♠JT9 ♣A  （♣A = 1赢墩 + 小黑桃）
    # 西家：♥AKQ ♦A  （♥AKQ = 3个红桃赢墩 + ♦A = 1个方块赢墩）
    # 东家：♥JT9 ♦KJT  （杂牌）
    #
    # 当前出牌：南家
    # 注意：庄家已经赢了 9 墩，这 9 墩里包括了红桃 AKQ 吗？
    # 不，红桃 AKQ 在西家手里！
    #
    # 等等，不对。如果西家有 ♥AKQ，庄家怎么赢的 9 墩？
    # 让我重新想... 这是残局测试，前面的 9 墩已经打完了，
    # 我们只需要看剩下的 4 墩里庄家能拿几墩。

    # 最终方案（简单清晰）：
    # 南打 7♠（需 13 墩），剩 4 张，已赢 9 墩
    # 当前出牌：南家
    # 南家：♠KQ ♥AK   （2将 + ♥AK = 2红桃赢墩）
    # 北家：♠JT ♥QJ   （2小将 + 2红桃）
    # 西家：♠A ♥T ♦AK （♠A = 将牌赢墩 + ♦AK = 2方块赢墩）
    # 东家：♠9 ♦QJT ♣A （杂牌）
    #
    # 分析（从庄家视角，还需 4 墩 = 不可能）：
    #
    # 选项 A：出 ♠K（吊将）
    #   - 西家 ♠A 赢这墩 → 防守方拿到出牌权
    #   - 西家出 ♦A → 再赢 1 墩
    #   - 西家继续出 ♦K → 再赢 1 墩（如果北家没有了）
    #   ... 太复杂了，还需要考虑北家有没有方块

    # 我直接用代码跑，看结果，然后验证 avg_tricks 有差异就行

    hands_cards = {
        "南": [Card('♠', 'K'), Card('♠', 'Q'), Card('♥', 'A'), Card('♥', 'K')],
        "北": [Card('♠', 'J'), Card('♠', 'T'), Card('♥', 'Q'), Card('♥', 'J')],
        "西": [Card('♠', 'A'), Card('♥', 'T'), Card('♦', 'A'), Card('♦', 'K')],
        "东": [Card('♠', '9'), Card('♦', 'Q'), Card('♦', 'J'), Card('♦', 'T')],
    }

    print(f"\n📋 测试场景：")
    print(f"  定约: 7♠ 南打（需 13 墩，大满贯）")
    print(f"  已赢: 庄家 9 墩，防守 0 墩")
    print(f"  剩余: 4 张牌 = 4 墩")
    print(f"  当前出牌: 南家")
    print(f"  预期: 肯定宕（西家有 ♠A），但不同出牌宕几不同")
    for pos in ["北", "东", "南", "西"]:
        print(f"  {pos}: {[str(c) for c in hands_cards.get(pos, [])]}")

    service, state = build_test_state(
        hands_cards, declarer="南", contract_str="7♠",
        current_player="南", decl_tricks=9, def_tricks=0,
    )

    playable = service.get_playable_cards("南")
    print(f"\n  南家可出: {[str(c) for c in playable]}")

    # 双明手验证
    try:
        from endplay import Deal
        from endplay.dds import solve_board
        from endplay.types import Denom, Player
        from bridge.mcts.state_utils import SUIT_TO_DENOM, POSITION_TO_PLAYER
        from bridge.mcts.dd_search import _hands_to_pbn

        pbn = _hands_to_pbn(hands_cards)
        deal = Deal(pbn)
        deal.trump = Denom.spades
        deal.first = Player.south
        result = solve_board(deal)
        side_tricks = max(score for _, score in result)
        total_decl = 9 + side_tricks  # 庄家总共能赢的墩数
        print(f"\n  📊 双明手分析：")
        print(f"    剩余 4 墩庄家赢: {side_tricks} 墩")
        print(f"    总赢墩: {total_decl}/13 → {'做成' if total_decl >= 13 else f'宕{13 - total_decl}'}")
    except Exception as e:
        print(f"  DDS 验证失败: {e}")

    print(f"\n🚀 运行 αμ 搜索（20 worlds）...")
    am = AlphaMuSearch(
        sampler=service.mcts.sampler,
        num_worlds=20,
        max_depth=4,
        time_limit=15.0,
    )

    t0 = time.time()
    result = am.search(state)
    elapsed = time.time() - t0

    mcts_stats = result['full_output'].get('mcts_stats', {})
    candidates = mcts_stats.get('candidates', [])

    print(f"\n📊 αμ 搜索结果：")
    print(f"  {'牌':<6} {'成功率':>8} {'worst':>6} {'min_tricks':>11} {'avg_tricks':>11} {'front':>6}")
    print(f"  {'-'*6} {'-'*8} {'-'*6} {'-'*11} {'-'*11} {'-'*6}")
    for c in candidates:
        rate_pct = f"{c['success_rate']*100:.0f}%"
        print(f"  {c['card']:<6} {rate_pct:>8} {c['worst']:>6} "
              f"{c.get('min_tricks','?'):>11} {c.get('avg_tricks','?'):>11} {c['front_size']:>6}")
        print(f"         best_vector: {c['best_vector']}")

    print(f"\n  ✅ 推荐: {result['card']}")
    print(f"  耗时: {elapsed:.2f}s, DDS: {mcts_stats.get('err_stats', {}).get('path_D_ok', '?')} 次")

    # 检查：是否全宕（成功率都是0%），avg_tricks 是否有差异
    all_zero = all(c['success_rate'] == 0.0 for c in candidates)
    avg_vals = [c.get('avg_tricks', 0) for c in candidates]
    diff_avg = len(set(avg_vals)) > 1

    print(f"\n📈 Tie-break 验证：")
    print(f"  所有牌成功率 = 0%（全宕）: {'是 ✅' if all_zero else '否'}")
    print(f"  avg_tricks 有差异: {'是 ✅' if diff_avg else '否'}")
    print(f"  avg_tricks 值: {avg_vals}")

    if all_zero and diff_avg:
        best_idx = avg_vals.index(max(avg_vals))
        best_card = candidates[best_idx]['card']
        print(f"  Tie-break 选择: {best_card} (avg_tricks = {max(avg_vals)})")
        print(f"  实际推荐: {result['card']}")
        if str(result['card']) == best_card:
            print(f"  🎯 一致！avg_tricks tie-break 正常工作")
        else:
            print(f"  ⚠️  不一致，检查 min_tricks 或其他 tie-break 层级")

    print("\n" + "=" * 70)
    print("🏁 测试完成")
    print("=" * 70)


if __name__ == "__main__":
    test_all_down_scenario()
