"""αμ 搜索算法测试。

测试覆盖：
1. OutcomeVector 支配关系
2. ParetoFront 添加/合并
3. AlphaMuSearch 在残局场景的端到端调用
4. 与 DD 搜索结果对比（一致性 sanity check）
"""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from bridge.mcts.alpha_mu import (
    OutcomeVector, ParetoFront, AlphaMuSearch, ENDPLAY_AVAILABLE,
)
from bridge.play_types import (
    Card, PlayState, Contract, PlayPhase, PlayerRole,
)


def test_outcome_vector_dominance():
    """测试 OutcomeVector 支配关系（布尔版本）。"""
    print("=" * 60)
    print("测试 1: OutcomeVector 支配关系")
    print("=" * 60)

    # v1 = [1,1,0], v2 = [1,0,0] → v1 支配 v2
    v1 = OutcomeVector([1, 1, 0])
    v2 = OutcomeVector([1, 0, 0])
    assert v1.dominates(v2), f"v1{v1.values} 应支配 v2{v2.values}"
    assert not v2.dominates(v1), f"v2 不应支配 v1"
    print(f"  ✓ [1,1,0] 支配 [1,0,0]")

    # v3 = [0,1,1], v4 = [1,1,1] → v4 支配 v3
    v3 = OutcomeVector([0, 1, 1])
    v4 = OutcomeVector([1, 1, 1])
    assert v4.dominates(v3)
    assert not v3.dominates(v4)
    print(f"  ✓ [1,1,1] 支配 [0,1,1]")

    # 不可比较：v5 = [1,0], v6 = [0,1]
    v5 = OutcomeVector([1, 0])
    v6 = OutcomeVector([0, 1])
    assert not v5.dominates(v6)
    assert not v6.dominates(v5)
    print(f"  ✓ [1,0] 与 [0,1] 互不支配")

    # success_rate 计算
    assert abs(v1.success_rate() - 2/3) < 1e-6, f"v1 应为 2/3, 实际 {v1.success_rate()}"
    assert v4.success_rate() == 1.0
    print(f"  ✓ success_rate: v1={v1.success_rate():.1%}, v4={v4.success_rate():.1%}")

    # worst
    assert v1.worst() == 0
    assert v4.worst() == 1
    print(f"  ✓ worst: v1={v1.worst()}, v4={v4.worst()}")

    # useful_mask
    v7 = OutcomeVector([1, 0, 1], useful_mask=[True, False, True])
    assert v7.success_rate() == 1.0, f"v7 success_rate 应为 1.0, 实际 {v7.success_rate()}"
    print(f"  ✓ useful_mask: impossible world 不计入")

    print("  测试通过!\n")


def test_pareto_front():
    """测试 ParetoFront 添加和合并（布尔版本）。"""
    print("=" * 60)
    print("测试 2: ParetoFront 添加/合并")
    print("=" * 60)

    pf = ParetoFront()
    v2 = OutcomeVector([1, 0, 0])
    assert pf.add(v2)
    assert len(pf) == 1
    print(f"  ✓ 添加 [1,0,0], front size = {len(pf)}")

    # 添加 v1 = [1,1,0]，应支配 v2 并替换
    v1 = OutcomeVector([1, 1, 0])
    assert pf.add(v1)
    assert len(pf) == 1, f"v1 应替换 v2, front size = {len(pf)}"
    assert v1 in pf.vectors
    print(f"  ✓ [1,1,0] 支配 [1,0,0], front size = {len(pf)}")

    # 添加 v3 = [0,1,1]，不可比较，应保留
    v3 = OutcomeVector([0, 1, 1])
    assert pf.add(v3)
    assert len(pf) == 2
    print(f"  ✓ 添加 [0,1,1] (不可比较), front size = {len(pf)}")

    # 添加被支配的 v4 = [0,1,0]，应被拒绝（被 [0,1,1] 支配）
    v4 = OutcomeVector([0, 1, 0])
    assert not pf.add(v4)
    assert len(pf) == 2
    print(f"  ✓ 拒绝 [0,1,0] (被 [0,1,1] 支配), front size = {len(pf)}")

    # 合并两个 front
    pf2 = ParetoFront([OutcomeVector([1, 1, 1])])
    pf_merged = pf.union(pf2)
    assert len(pf_merged) == 1
    assert OutcomeVector([1, 1, 1]) in pf_merged.vectors
    print(f"  ✓ 合并: [1,1,1] 支配所有, merged size = {len(pf_merged)}")

    # best_score / maximin
    pf3 = ParetoFront([
        OutcomeVector([1, 0, 0]),
        OutcomeVector([0, 1, 1]),
    ])
    assert abs(pf3.best_score() - 2/3) < 1e-6
    print(f"  ✓ best_score = {pf3.best_score():.1%}")
    mv = pf3.maximin_vector()
    assert mv is not None and mv.worst() == 0  # both have worst=0, maximin picks the one with higher rate
    assert mv.success_rate() == 2/3
    print(f"  ✓ maximin: worst={mv.worst()}, rate={mv.success_rate():.1%} (picks [0,1,1] with 2/3)")

    print("  测试通过!\n")


def _build_endgame_state():
    """构建一个残局测试场景（每手 4 张牌）。

    南家庄家，3NT 定约，需要 9 墩，已赢 5 墩，还需 4 墩。
    南家当前出牌。
    """
    contract = Contract(level=3, suit="NT", declarer="南")
    state = PlayState(
        contract=contract,
        hands={
            "南": [Card("♠", "A"), Card("♠", "K"), Card("♥", "A"), Card("♦", "A")],
            "西": [Card("♠", "Q"), Card("♠", "2"), Card("♥", "K"), Card("♦", "K")],
            "北": [Card("♠", "J"), Card("♠", "3"), Card("♥", "Q"), Card("♦", "Q")],
            "东": [Card("♠", "T"), Card("♠", "4"), Card("♥", "J"), Card("♦", "J")],
        },
        player_roles={"南": PlayerRole.AI.value, "西": PlayerRole.AI.value,
                      "北": PlayerRole.AI.value, "东": PlayerRole.AI.value},
        declarer_tricks=5,
        defender_tricks=4,
        phase=PlayPhase.PLAYING,
    )
    state.current_player = "南"
    state.lead_player = "南"
    return state


def test_alpha_mu_endgame():
    """端到端测试：αμ 在残局场景的搜索。"""
    print("=" * 60)
    print("测试 3: αμ 残局端到端搜索")
    print("=" * 60)

    if not ENDPLAY_AVAILABLE:
        print("  ⚠ 跳过: endplay 未安装")
        return

    state = _build_endgame_state()
    print(f"  场景: {state.contract}, 南家出牌, 手牌 {len(state.hands['南'])} 张")
    print(f"  南: {[str(c) for c in state.hands['南']]}")
    print(f"  已赢墩: 庄家 {state.declarer_tricks}, 防守 {state.defender_tricks}")

    search = AlphaMuSearch(
        num_worlds=8,       # 测试用少量 worlds 加速
        max_depth=2,        # 浅深度
        time_limit=15.0,
    )

    try:
        result = search.search(state)
        card = result.get("card")
        reasoning = result.get("reasoning", "")
        print(f"  αμ 推荐: {card}")
        print(f"  推理: {reasoning}")

        assert card is not None, "αμ 应返回有效出牌"
        # 推荐牌必须在合法出牌中
        playable = state.get_playable_cards("南")
        assert card in playable, f"推荐 {card} 不在合法出牌 {playable} 中"
        print(f"  ✓ 推荐牌合法")

        # 检查 full_output
        full = result.get("full_output", {})
        stats = full.get("mcts_stats", {})
        assert stats.get("algorithm") == "alpha_mu"
        print(f"  ✓ 算法标识: {stats.get('algorithm')}")
        print(f"  ✓ DDS 调用数: {stats.get('iterations')}")
        print(f"  ✓ 搜索节点数: {stats.get('nodes_searched')}")

    except Exception as e:
        print(f"  ✗ 异常: {e}")
        import traceback
        traceback.print_exc()
        raise

    print("  测试通过!\n")


def test_alpha_mu_vs_dd_consistency():
    """αμ 与 DD 在确定场景下应给出合理建议（sanity check）。"""
    print("=" * 60)
    print("测试 4: αμ vs DD 一致性 sanity check")
    print("=" * 60)

    if not ENDPLAY_AVAILABLE:
        print("  ⚠ 跳过: endplay 未安装")
        return

    state = _build_endgame_state()

    # αμ 搜索
    alpha_search = AlphaMuSearch(
        num_worlds=6, max_depth=2, time_limit=10.0,
    )
    alpha_result = alpha_search.search(state)
    alpha_card = alpha_result.get("card")
    print(f"  αμ 推荐: {alpha_card}")

    # DD 搜索（全知，作为参考）
    from bridge.mcts.dd_search import DDSearch
    dd = DDSearch(num_samples=20, min_samples=5, time_limit=10.0,
                  endgame_card_threshold=10)  # 强制走残局枚举
    dd_result = dd.search(state)
    dd_card = dd_result.get("card")
    print(f"  DD  推荐: {dd_card}")

    # 两者都应返回合法出牌
    playable = state.get_playable_cards("南")
    assert alpha_card in playable, f"αμ 推荐 {alpha_card} 不合法"
    assert dd_card in playable, f"DD 推荐 {dd_card} 不合法"
    print(f"  ✓ 两者推荐均合法")

    # 在这个场景（南家 AKQJ 强牌），两者都应推荐 ♠A（赢墩+出牌权）
    # 但不强制相等，只检查都是合法的
    print(f"  ✓ sanity check 通过（不强制相等）")

    print("  测试通过!\n")


def test_alpha_mu_single_card():
    """测试唯一选择场景：αμ 应直接返回。"""
    print("=" * 60)
    print("测试 5: 唯一选择快速返回")
    print("=" * 60)

    if not ENDPLAY_AVAILABLE:
        print("  ⚠ 跳过: endplay 未安装")
        return

    # 南家只有 1 张牌
    contract = Contract(level=3, suit="NT", declarer="南")
    state = PlayState(
        contract=contract,
        hands={
            "南": [Card("♠", "A")],
            "西": [Card("♠", "Q")],
            "北": [Card("♠", "K")],
            "东": [Card("♠", "J")],
        },
        player_roles={"南": PlayerRole.AI.value, "西": PlayerRole.AI.value,
                      "北": PlayerRole.AI.value, "东": PlayerRole.AI.value},
        declarer_tricks=8,
        defender_tricks=4,
        phase=PlayPhase.PLAYING,
    )
    state.current_player = "南"

    search = AlphaMuSearch(num_worlds=4, max_depth=1, time_limit=5.0)
    result = search.search(state)
    card = result.get("card")
    assert card == Card("♠", "A"), f"应返回唯一牌 ♠A, 实际 {card}"
    print(f"  ✓ 唯一选择直接返回: {card}")

    print("  测试通过!\n")


if __name__ == "__main__":
    test_outcome_vector_dominance()
    test_pareto_front()
    test_alpha_mu_endgame()
    test_alpha_mu_vs_dd_consistency()
    test_alpha_mu_single_card()
    print("=" * 60)
    print("所有测试通过!")
    print("=" * 60)
