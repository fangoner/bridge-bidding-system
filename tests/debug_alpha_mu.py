"""αμ 搜索调试脚本：诊断为什么成功率全是 0%"""
import sys
import time
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from bridge.play_service import PlayService
from bridge.play_types import Card, PlayerRole, POSITION_ORDER, PlayState
from bridge.mcts.alpha_mu import AlphaMuSearch
from bridge.mcts.sampler import DealSampler
from bridge.mcts.bid_constraint_library import extract_constraints_from_bid_history, SYSTEM_JF
from bridge.mcts.state_utils import cards_to_hand_str


class MockLLMClient:
    def chat(self, *args, **kwargs):
        return ""
    def chat_json(self, *args, **kwargs):
        return {}


def hand_dict_to_cards(hands_dict):
    """把字典格式的手牌转为 Card 列表"""
    result = {}
    for pos, suits in hands_dict.items():
        cards = []
        for suit_char, suit_name in [('♠', 'spades'), ('♥', 'hearts'), ('♦', 'diamonds'), ('♣', 'clubs')]:
            ranks = suits.get(suit_name, '')
            for r in ranks:
                cards.append(Card(suit=suit_char, rank=r))
        result[pos] = cards
    return result


def debug_alpha_mu_scenario():
    """调试 αμ 搜索"""
    print("=" * 70)
    print("🔍 αμ 搜索调试：诊断全 0% 成功率问题")
    print("=" * 70)

    # 场景：4♠ 南打，一副有代表性的牌
    hands = {
        "南": {"spades": "AKQJ", "hearts": "AK", "diamonds": "T8543", "clubs": "95"},
        "西": {"spades": "652", "hearts": "975432", "diamonds": "J", "clubs": "AJ7"},
        "北": {"spades": "98743", "hearts": "J8", "diamonds": "AKQ", "clubs": "Q32"},
        "东": {"spades": "T", "hearts": "QT6", "diamonds": "9762", "clubs": "KT864"},
    }

    bid_history = "(南)1NT-(西)pass-(北)2♥-(东)pass-(南)2♠-(西)pass-(北)4♠"
    contract_str = "4♠"
    declarer = "南"

    # 提取约束
    constraints = extract_constraints_from_bid_history(bid_history, system=SYSTEM_JF)
    print(f"\n📋 叫牌约束：")
    for pos in ["北", "东", "南", "西"]:
        c = constraints.get(pos)
        if c:
            print(f"  {pos}: HCP {c.min_hcp}-{c.max_hcp}, suit_min={dict(c.suit_min)}, [{c.inference_source}]")

    # 创建 PlayService 并初始化
    service = PlayService(llm_client=MockLLMClient())
    player_roles = {pos: PlayerRole.AI.value for pos in POSITION_ORDER}
    state = service.initialize(
        hands=hands,
        contract_str=contract_str,
        declarer=declarer,
        player_roles=player_roles,
        bidding_sequence=bid_history,
        bid_history=bid_history,
    )

    print(f"\n🎴 初始状态：")
    print(f"  当前玩家: {state.current_player} (首攻)")
    print(f"  定约: {state.contract}")
    print(f"  明手: {state.dummy}")
    print(f"  需要赢墩: {state.contract.tricks_needed}")

    # 打前 8 墩，进入残局（剩余 5 张牌），然后用 αμ 搜索
    print(f"\n🎮 先打前几墩进入残局...")

    trick_count = 0
    while trick_count < 10:  # 打到剩 3 墩
        state = service.get_state()
        if state is None:
            break
        current_pos = state.current_player
        if current_pos is None:
            break
        total_tricks = state.declarer_tricks + state.defender_tricks
        if total_tricks >= 13:
            break

        playable = service.get_playable_cards(current_pos)
        if not playable:
            break

        # 简单策略：第一张随便出（用 MCTS）
        if len(playable) == 1:
            chosen = playable[0]
        else:
            result = service._mcts_play(state)
            card_dict = result.get("card")
            chosen = Card(suit=card_dict["suit"], rank=card_dict["rank"])

        success, msg = service.play_card(current_pos, chosen, is_ai=True)
        if not success:
            print(f"  出牌错误: {msg}")
            break

        new_total = state.declarer_tricks + state.defender_tricks
        state = service.get_state()
        after_total = state.declarer_tricks + state.defender_tricks
        if after_total > total_tricks:
            trick_count = after_total
            print(f"  第{trick_count}墩结束 → 庄家:{state.declarer_tricks}, 防守:{state.defender_tricks}")
            if trick_count >= 10:
                break

    state = service.get_state()
    remaining = sum(len(h) for h in state.hands.values())
    print(f"\n📍 残局状态（剩余 {remaining} 张牌，{13 - trick_count} 墩未打）：")
    print(f"  当前玩家: {state.current_player}")
    print(f"  庄家赢墩: {state.declarer_tricks}, 防守赢墩: {state.defender_tricks}")
    print(f"  当前墩已出牌: {[(p, str(c)) for p, c in state.current_trick.cards]}")
    for pos in ["北", "东", "南", "西"]:
        h = state.hands.get(pos, [])
        print(f"  {pos}家: {[str(c) for c in h]}")

    # 直接用 αμ 搜索，打印详细诊断
    print(f"\n🔬 αμ 搜索详细诊断...")

    # 获取 αμ 搜索器
    am = AlphaMuSearch(
        sampler=service.mcts.sampler,
        num_worlds=20,  # 少一点方便调试
        max_depth=4,
        time_limit=10.0,
        dds_budget=3000,
    )

    # 手动运行搜索，捕获中间状态
    perspective = state.current_player
    actual_turn = state.current_player
    declarer_pos = state.contract.declarer
    dummy_pos = state.dummy
    if perspective == dummy_pos:
        perspective = declarer_pos

    print(f"\n  视角 (perspective): {perspective}")
    print(f"  实际出牌 (actual_turn): {actual_turn}")
    print(f"  庄家: {declarer_pos}, 明手: {dummy_pos}")

    from bridge.play_types import PARTNERS
    partner = PARTNERS.get(perspective, perspective)
    our_side = frozenset({perspective, partner})
    is_our_declarer = our_side == frozenset({declarer_pos, dummy_pos})
    tricks_needed = state.contract.tricks_needed
    goal = tricks_needed if is_our_declarer else (14 - tricks_needed)

    print(f"  我方 (our_side): {our_side}")
    print(f"  我方是庄家方: {is_our_declarer}")
    print(f"  目标 (goal): {goal} 墩")
    print(f"  我方已赢: {state.declarer_tricks if is_our_declarer else state.defender_tricks} 墩")
    print(f"  还需赢: {goal - (state.declarer_tricks if is_our_declarer else state.defender_tricks)} 墩")

    # 生成 worlds
    if service.mcts.sampler.belief_tracker is not None:
        service.mcts.sampler.belief_tracker.prepare(state, perspective)

    worlds = []
    for i in range(20):
        try:
            w = service.mcts.sampler.sample(state, perspective)
            if w is not None:
                worlds.append(w)
        except Exception as e:
            print(f"  world {i} 生成失败: {e}")

    print(f"\n  生成了 {len(worlds)} 个 possible worlds")

    # 对每个 world，手动做 DDS 评估，看看庄家实际能赢几墩
    print(f"\n📊 每个 world 的双明手评估（庄家视角）：")
    print(f"  {'#':>3} {'庄家总墩':>8} {'我方达成':>8} {'OV值':>6}")

    try:
        from endplay import Deal
        from endplay.dds import solve_board
        from endplay.types import Denom
        from bridge.mcts.state_utils import SUIT_TO_DENOM, POSITION_TO_PLAYER, PLAYER_TO_POSITION
        from bridge.mcts.dd_search import _hands_to_pbn, _to_ep, _has_duplicates

        all_decl_tricks = []
        all_our_success = []

        for w_idx, world in enumerate(worlds[:10]):  # 只看前10个
            try:
                # 构造当前状态的 deal
                sim_hands = {pos: [Card(suit=c.suit, rank=c.rank) for c in cards]
                           for pos, cards in world.items()}

                # 当前墩已出的牌
                trick_cards = [(p, c) for p, c in state.current_trick.cards]
                for pos, card in trick_cards:
                    if card not in sim_hands.get(pos, []):
                        sim_hands[pos].append(card)

                if _has_duplicates(sim_hands):
                    print(f"  {w_idx:>3}: 重复牌，跳过")
                    continue

                pbn = _hands_to_pbn(sim_hands)
                deal = Deal(pbn)
                trump = state.contract.suit
                deal.trump = SUIT_TO_DENOM.get(trump, Denom.nt)

                if trick_cards:
                    trick_leader = state.current_trick.leader
                    deal.first = POSITION_TO_PLAYER.get(trick_leader, POSITION_TO_PLAYER["北"])
                    for _pos, card in trick_cards:
                        deal.play(_to_ep(card), from_hand=True)
                else:
                    deal.first = POSITION_TO_PLAYER.get(state.current_player, POSITION_TO_PLAYER["北"])

                result = solve_board(deal)
                if not result:
                    print(f"  {w_idx:>3}: DDS 无结果")
                    continue

                curplayer_pos = PLAYER_TO_POSITION.get(deal.curplayer, state.current_player)
                curplayer_is_declarer = curplayer_pos in (declarer_pos, dummy_pos)
                remaining_tricks = 13 - (state.declarer_tricks + state.defender_tricks)
                side_tricks = max(score for _, score in result)

                if curplayer_is_declarer:
                    total_decl = state.declarer_tricks + side_tricks
                else:
                    total_decl = state.declarer_tricks + (remaining_tricks - side_tricks)

                # 计算我方是否达成目标
                if is_our_declarer:
                    our_tricks = total_decl
                else:
                    our_tricks = 13 - total_decl

                ov_val = 1 if our_tricks >= goal else 0

                all_decl_tricks.append(total_decl)
                all_our_success.append(ov_val)

                print(f"  {w_idx:>3}  {total_decl:>8}  {our_tricks:>8}  {ov_val:>6}  (goal={goal}, side_tricks={side_tricks}, curplayer={curplayer_pos})")

            except Exception as e:
                print(f"  {w_idx:>3}: 错误: {e}")

        if all_decl_tricks:
            avg_decl = sum(all_decl_tricks) / len(all_decl_tricks)
            success_rate = sum(all_our_success) / len(all_our_success)
            print(f"\n  📈 统计（前{len(all_decl_tricks)}个world）：")
            print(f"     平均庄家总墩数: {avg_decl:.2f}")
            print(f"     我方成功率: {success_rate:.0%}")
            print(f"     OV向量: {''.join(str(v) for v in all_our_success)}")

    except ImportError:
        print("  endplay 不可用，跳过 DDS 验证")

    # 正式运行 αμ 搜索
    print(f"\n🚀 运行 αμ 搜索...")
    t0 = time.time()
    result = am.search(state)
    elapsed = time.time() - t0

    print(f"\n📋 αμ 搜索结果：")
    print(f"  推荐出牌: {result['card']}")
    print(f"  核心逻辑: {result['reasoning']}")
    print(f"  耗时: {elapsed:.2f}s")

    mcts_stats = result['full_output'].get('mcts_stats', {})
    candidates = mcts_stats.get('candidates', [])
    print(f"\n  候选牌详情：")
    for c in candidates:
        print(f"    {c['card']}: success_rate={c['success_rate']:.0%}, worst={c['worst']}, "
              f"front_size={c['front_size']}, {c['success_count']}/{c['total_useful']}")
        print(f"      best_vector: {c['best_vector']}")

    err_stats = mcts_stats.get('err_stats', {})
    print(f"\n  DDS 路径统计：")
    for k, v in err_stats.items():
        if v > 0:
            print(f"    {k}: {v}")

    print("\n" + "=" * 70)
    print("🏁 调试完成")
    print("=" * 70)


if __name__ == "__main__":
    debug_alpha_mu_scenario()
