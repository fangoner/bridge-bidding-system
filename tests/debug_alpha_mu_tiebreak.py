"""αμ tie-break 调试：验证宕牌时 avg_tricks 能区分宕几"""
import sys
import time
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from bridge.play_service import PlayService
from bridge.play_types import Card, PlayerRole, POSITION_ORDER
from bridge.mcts.alpha_mu import AlphaMuSearch


class MockLLMClient:
    def chat(self, *args, **kwargs):
        return ""
    def chat_json(self, *args, **kwargs):
        return {}


def debug_tiebreak():
    """测试宕牌场景下 avg_tricks tie-break 是否正常"""
    print("=" * 70)
    print("🔍 αμ Tie-break 调试：宕牌场景下区分宕几")
    print("=" * 70)

    # 构造一个宕牌场景：4♠ 南打，但庄家只有 7 个赢墩，还剩 3 张牌
    # 让防守方有 AKQ 等大牌，不同出牌导致宕1或宕2
    hands = {
        "南": {"spades": "AKQ", "hearts": "", "diamonds": "", "clubs": ""},          # 3 将牌，都是赢墩
        "西": {"spades": "", "hearts": "AKQ", "diamonds": "", "clubs": ""},          # 3 张红桃大牌
        "北": {"spades": "J", "hearts": "432", "diamonds": "", "clubs": ""},        # 明手：1小将 + 3小红心
        "东": {"spades": "T", "hearts": "", "diamonds": "AKQ", "clubs": ""},        # 东家：1小将 + 3方块大牌
    }

    bid_history = "(南)1♠-(西)pass-(北)4♠"
    contract_str = "4♠"
    declarer = "南"

    service = PlayService(llm_client=MockLLMClient())

    player_roles = {pos: PlayerRole.AI.value for pos in POSITION_ORDER}

    # 手动构造 PlayState 来模拟打到第 10 墩的状态
    # 直接用 initialize 然后手动调整
    state = service.initialize(
        hands=hands,
        contract_str=contract_str,
        declarer=declarer,
        player_roles=player_roles,
        bidding_sequence=bid_history,
        bid_history=bid_history,
    )

    print(f"\n🎴 测试牌局（简化残局）：")
    print(f"  定约: {state.contract} (需要 {state.contract.tricks_needed} 墩)")
    print(f"  明手: {state.dummy}")

    # 直接构造一个更清晰的测试：南家出牌，有两张选择
    # 选 A 能拿 9 墩（宕1），选 B 能拿 8 墩（宕2）
    # 验证 avg_tricks 能区分

    # 简化：我们直接在已有残局上测试，看看输出中 avg_tricks 是否有差异
    # 先打前 7 墩（都让南家将牌赢），然后进入宕牌场景
    # 实际上这个牌太简单了，让我们直接看 αμ 的输出

    print(f"\n📊 当前手牌：")
    for pos in ["北", "东", "南", "西"]:
        h = state.hands.get(pos, [])
        print(f"  {pos}: {[str(c) for c in h]}")

    # 看看 αμ 对首攻的评估
    print(f"\n🚀 首攻时 αμ 评估（西家首攻）：")
    am = AlphaMuSearch(
        sampler=service.mcts.sampler,
        num_worlds=10,
        max_depth=3,
        time_limit=10.0,
    )

    # 先打几墩到一个更有区分度的局面
    print(f"\n🎮 打前 7 墩进入残局...")

    for i in range(7 * 4):  # 7墩 = 28张
        state = service.get_state()
        if state is None:
            break
        current_pos = state.current_player
        if current_pos is None:
            break
        total = state.declarer_tricks + state.defender_tricks
        if total >= 7:
            break

        playable = service.get_playable_cards(current_pos)
        if not playable:
            break

        if len(playable) == 1:
            chosen = playable[0]
        else:
            # 用简单策略：南家出将牌，其他随便出
            if current_pos == "南":
                # 出最大的将牌
                spades = [c for c in playable if c.suit == '♠']
                chosen = max(spades, key=lambda c: c.rank_value) if spades else playable[0]
            else:
                chosen = playable[0]

        service.play_card(current_pos, chosen, is_ai=True)

    state = service.get_state()
    remaining = sum(len(h) for h in state.hands.values())
    total_tricks = state.declarer_tricks + state.defender_tricks
    print(f"  已打 {total_tricks} 墩，剩 {remaining} 张牌")
    print(f"  庄家赢墩: {state.declarer_tricks}, 防守赢墩: {state.defender_tricks}")
    print(f"  当前玩家: {state.current_player}")
    print(f"  当前墩: {[(p, str(c)) for p, c in state.current_trick.cards]}")

    for pos in ["北", "东", "南", "西"]:
        h = state.hands.get(pos, [])
        print(f"  {pos}: {[str(c) for c in h]}")

    # 确保当前是南家（庄家）或北家（明手）出牌，有多个选择
    playable = service.get_playable_cards(state.current_player)
    print(f"\n  可出牌: {[str(c) for c in playable]}")

    if len(playable) >= 2:
        print(f"\n🔬 运行 αμ 搜索...")
        t0 = time.time()
        result = am.search(state)
        elapsed = time.time() - t0

        mcts_stats = result['full_output'].get('mcts_stats', {})
        candidates = mcts_stats.get('candidates', [])

        print(f"\n📋 候选牌详情：")
        print(f"  {'牌':<6} {'成功率':>8} {'worst':>6} {'min_tricks':>11} {'avg_tricks':>11} {'front':>6}")
        print(f"  {'-'*6} {'-'*8} {'-'*6} {'-'*11} {'-'*11} {'-'*6}")
        for c in candidates:
            print(f"  {c['card']:<6} {c['success_rate']:>7.0%} {c['worst']:>6} {c.get('min_tricks','?'):>11} {c.get('avg_tricks','?'):>11} {c['front_size']:>6}")
            print(f"         best_vector: {c['best_vector']}")

        print(f"\n  推荐: {result['card']}")
        print(f"  耗时: {elapsed:.2f}s, DDS: {mcts_stats.get('dds_calls', '?')} 次")

        # 检查 tie-break 是否有效
        all_same_rate = len(set(c['success_rate'] for c in candidates)) == 1
        all_same_worst = len(set(c['worst'] for c in candidates)) == 1
        diff_avg = len(set(c.get('avg_tricks', 0) for c in candidates)) > 1

        print(f"\n📊 Tie-break 有效性：")
        print(f"  所有牌成功率相同: {'是' if all_same_rate else '否'}")
        print(f"  所有牌 worst 相同: {'是' if all_same_worst else '否'}")
        print(f"  avg_tricks 有差异: {'是' if diff_avg else '否'}")
        if all_same_rate and all_same_worst and diff_avg:
            print(f"  ✅ Tie-break 生效！avg_tricks 将决定最终选牌")
    else:
        print(f"\n  只有 1 张可出，跳过 αμ 测试")

    print("\n" + "=" * 70)
    print("🏁 调试完成")
    print("=" * 70)


if __name__ == "__main__":
    debug_tiebreak()
