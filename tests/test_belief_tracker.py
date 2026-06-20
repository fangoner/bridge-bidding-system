"""信念跟踪器端到端测试。

验证：
1. BeliefTracker 能正确生成粒子
2. void 约束被强制执行
3. 信号证据能调整粒子权重
4. sampler.sample() 在启用信念跟踪器后走粒子路径
"""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from bridge.play_types import Card, PlayState, PlayPhase, Contract, POSITION_ORDER
from bridge.play_engine import PlayEngine
from bridge.mcts.sampler import DealSampler
from bridge.mcts.belief import BeliefTracker, collect_voids, collect_signal_evidence
from config import BELIEF_NUM_PARTICLES


# 测试用牌局（4家各13张）
TEST_HANDS = {
    "南": {"spades": "AKQ", "hearts": "53", "diamonds": "84", "clubs": "J75329"},
    "西": {"spades": "543", "hearts": "KQ8", "diamonds": "KQJ", "clubs": "864T"},
    "北": {"spades": "JT9876", "hearts": "AJT", "diamonds": "A53", "clubs": "Q"},
    "东": {"spades": "2", "hearts": "97642", "diamonds": "T9762", "clubs": "AK"},
}


def test_belief_tracker_basic():
    """测试1：基本粒子生成和加权"""
    print("\n=== 测试1：基本粒子生成 ===")

    engine = PlayEngine()
    contract = Contract.from_str("3NT", "南")
    state = engine.initialize(TEST_HANDS, contract)

    sampler = DealSampler()
    tracker = BeliefTracker(sampler, num_particles=20)
    sampler.set_belief_tracker(tracker)

    # 初始状态（无已出牌）应能正常生成粒子
    tracker.prepare(state, "西")
    stats = tracker.stats()
    print(f"  粒子数: {stats['num_particles']}")
    print(f"  有效粒子: {stats['active_particles']}")
    print(f"  void过滤: {stats['void_filtered']}")

    assert stats["prepared"] is True
    assert stats["num_particles"] == 20
    assert stats["active_particles"] == 20  # 初始无void，全部有效
    print("  ✓ 初始状态粒子生成正确")

    # 抽样测试
    for i in range(5):
        sample = sampler.sample(state, "西")
        assert len(sample) == 4
        for pos in POSITION_ORDER:
            assert len(sample[pos]) == 13
    print("  ✓ 粒子抽样返回完整4家手牌")


def test_void_enforcement():
    """测试2：void 约束强制"""
    print("\n=== 测试2：void 约束强制 ===")

    engine = PlayEngine()
    contract = Contract.from_str("3NT", "南")
    state = engine.initialize(TEST_HANDS, contract)

    # 模拟东家在黑桃上 void：东家不跟黑桃
    # 领出黑桃，东家垫红桃
    state.current_trick.add_card("西", Card(suit="♠", rank="5"), False, "test", "low")
    state.current_trick.add_card("北", Card(suit="♠", rank="J"), False, "test", "high")
    state.current_trick.add_card("东", Card(suit="♥", rank="9"), False, "test", "void")  # 不跟黑桃！

    voids = collect_voids(state)
    print(f"  检测到 void: {voids}")
    assert "东" in voids
    assert "♠" in voids["东"]
    print("  ✓ void 检测正确（东家黑桃void）")

    # 采样验证：东家不应有黑桃
    sampler = DealSampler()
    tracker = BeliefTracker(sampler, num_particles=30)
    sampler.set_belief_tracker(tracker)
    tracker.prepare(state, "南")

    void_violations = 0
    for i in range(len(tracker.particles)):
        east_hand = tracker.particles[i].get("东", [])
        for card in east_hand:
            if card.suit == "♠":
                void_violations += 1
                break

    print(f"  void 违反粒子数: {void_violations}/{len(tracker.particles)}")
    assert void_violations == 0, "存在 void 违反的粒子！"
    print("  ✓ 所有粒子都遵守 void 约束")


def test_signal_evidence():
    """测试3：信号证据收集"""
    print("\n=== 测试3：信号证据收集 ===")

    engine = PlayEngine()
    contract = Contract.from_str("3NT", "南")
    state = engine.initialize(TEST_HANDS, contract)

    # 模拟一墩：西领黑桃5，北跟黑桃J（高），东跟黑桃2（低），南赢黑桃A
    state.current_trick.add_card("西", Card(suit="♠", rank="5"), False, "lead", "low")
    state.current_trick.add_card("北", Card(suit="♠", rank="J"), False, "follow", "high")
    state.current_trick.add_card("东", Card(suit="♠", rank="2"), False, "follow", "low")
    state.current_trick.add_card("南", Card(suit="♠", rank="A"), False, "win", "high")

    # 这墩完成后，北和东都跟了黑桃
    # 北是明手，不算防守信号
    # 东是防守方，跟黑桃2（rank_value=2，<8 → 低牌信号）

    evidence = collect_signal_evidence(state)
    print(f"  信号证据: {evidence}")

    # 西和东都是防守方（庄家=南，明手=北）
    # 西领黑桃5（rank_value=5，<8 → 低牌信号）
    # 东跟黑桃2（rank_value=2，<8 → 低牌信号）
    assert len(evidence) == 2
    positions = {e[0] for e in evidence}
    assert positions == {"西", "东"}
    assert all(e[1] == "♠" for e in evidence)
    assert all(e[2] is False for e in evidence)  # 都是低牌
    print("  ✓ 信号证据收集正确（西、东家低牌=不欢迎）")


def test_sampler_belief_integration():
    """测试4：sampler 在启用信念跟踪器后走粒子路径"""
    print("\n=== 测试4：sampler 信念跟踪器集成 ===")

    engine = PlayEngine()
    contract = Contract.from_str("3NT", "南")
    state = engine.initialize(TEST_HANDS, contract)

    sampler = DealSampler()
    tracker = BeliefTracker(sampler, num_particles=10)
    sampler.set_belief_tracker(tracker)

    # prepare 前应走原始路径
    sample1 = sampler.sample(state, "西")
    assert len(sample1) == 4
    print("  ✓ prepare 前走原始采样路径")

    # prepare 后应走粒子路径
    tracker.prepare(state, "西")
    sample2 = sampler.sample(state, "西")
    assert len(sample2) == 4
    # 验证抽样结果与某个粒子一致（深拷贝）
    found_match = False
    for particle in tracker.particles:
        if all(set((c.suit, c.rank) for c in sample2[pos]) ==
               set((c.suit, c.rank) for c in particle[pos]) for pos in POSITION_ORDER):
            found_match = True
            break
    assert found_match, "抽样结果不在粒子集中！"
    print("  ✓ prepare 后走粒子滤波路径")

    # 清空粒子后应回退到原始路径
    tracker.particles = []
    sample3 = sampler.sample(state, "西")
    assert len(sample3) == 4
    print("  ✓ 清空粒子后回退到原始路径")


def test_play_service_integration():
    """测试5：PlayService 集成（验证初始化不报错）"""
    print("\n=== 测试5：PlayService 集成 ===")

    from bridge.play_service import PlayService

    service = PlayService(llm_client=None)
    assert service.belief_tracker is not None
    print("  ✓ BeliefTracker 已创建并绑定到 DD sampler")
    assert service.dd_search.sampler.belief_tracker is not None
    print("  ✓ DD sampler 已绑定 belief_tracker")
    assert service.mcts.sampler.belief_tracker is not None
    print("  ✓ MCTS sampler 已绑定 belief_tracker")

    state = service.initialize(TEST_HANDS, "3NT", "南")
    assert service.belief_tracker.particles == []  # 初始化后应清空
    print("  ✓ initialize() 正确重置信念跟踪器")


if __name__ == "__main__":
    test_belief_tracker_basic()
    test_void_enforcement()
    test_signal_evidence()
    test_sampler_belief_integration()
    test_play_service_integration()
    print("\n=== 全部测试通过 ===")
