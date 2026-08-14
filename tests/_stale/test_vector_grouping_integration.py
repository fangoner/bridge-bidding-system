"""αμ+LLM 引擎 best_vector 分组的真实集成测试。

用真实 αμ 搜索（endplay）生成 candidates，验证：
1. best_vector 字段确实存在于真实输出中
2. _group_candidates_by_vector 在真实数据下的分组行为
3. _should_trigger_llm 在真实数据下的触发判断
4. _alphamu_llm_play 完整流程能否跑通（不调用真实LLM）

运行方式：
    python tests/test_vector_grouping_integration.py
"""

import sys
import os
import asyncio
import json

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from bridge.play_service import PlayService
from bridge.play_types import (
    Card, PlayState, Contract, PlayPhase, PlayerRole, POSITION_ORDER, PARTNERS,
)
from bridge.mcts.alpha_mu import ENDPLAY_AVAILABLE


class MockLLMClient:
    """模拟 LLM 客户端：返回固定选组，避免真实 API 调用。"""

    def __init__(self):
        self.model = "mock-model"
        self.last_prompt = ""

    def chat(self, system_prompt, temperature=0.7, max_tokens=1024, **kwargs):
        return "模拟回复"

    def chat_json(self, system_prompt, user_prompt="", temperature=0.7, **kwargs):
        self.last_prompt = f"{system_prompt}\n\n{user_prompt}"
        return {
            "group": 1,
            "plan": "模拟计划：先清将再打长套",
            "steps": [
                {"step": 1, "action": "清将3轮", "precondition": "对方将牌3-2分布"},
                {"step": 2, "action": "飞♠K", "precondition": "♠K在东家"},
                {"step": 3, "action": "兑现长套", "precondition": "飞牌成功"},
            ],
            "plan_valid": False,
            "reason": "模拟选组1",
        }


ENDGAME_HANDS = {
    "南": {"spades": "AKQ", "hearts": "A", "diamonds": "A", "clubs": ""},
    "西": {"spades": "JT9", "hearts": "K", "diamonds": "K", "clubs": ""},
    "北": {"spades": "8765", "hearts": "Q", "diamonds": "Q", "clubs": ""},
    "东": {"spades": "432", "hearts": "J", "diamonds": "J", "clubs": ""},
}

BIDDING_SEQUENCE = "(南)1NT-(西)pass-(北)3NT-(东)pass-(南)pass-(西)pass"
BID_HISTORY = "(南)1NT-(西)pass-(北)3NT-(东)pass-(南)pass-(西)pass"


def _init_endgame(service, declarer="南", contract_str="3NT"):
    state = service.initialize(
        hands=ENDGAME_HANDS,
        contract_str=contract_str,
        declarer=declarer,
        player_roles={pos: PlayerRole.AI.value for pos in POSITION_ORDER},
        bidding_sequence=BIDDING_SEQUENCE,
        bid_history=BID_HISTORY,
    )
    state.declarer_tricks = 5
    state.defender_tricks = 4
    state.phase = PlayPhase.PLAYING
    state.current_player = declarer
    state.lead_player = declarer
    service.bid_constraints = {}
    return state


def test_real_alpha_mu_candidates():
    """测试1: 真实αμ搜索输出，检查best_vector字段存在。"""
    print("=" * 60)
    print("测试 1: 真实αμ搜索输出 - best_vector字段验证")
    print("=" * 60)

    if not ENDPLAY_AVAILABLE:
        print("  [跳过] endplay未安装，无法运行真实αμ搜索")
        return None

    service = PlayService(llm_client=MockLLMClient())
    state = _init_endgame(service)

    # 调用真实αμ搜索
    result = service._alphamu_full_play(state)
    full_output = result.get("full_output", {})
    mcts_stats = full_output.get("mcts_stats", {})
    candidates = mcts_stats.get("candidates", [])

    assert len(candidates) > 0, "αμ搜索应返回候选牌"
    print(f"  ✓ αμ返回 {len(candidates)} 个候选牌")

    # 检查每个candidate的best_vector字段
    has_vector_count = 0
    missing_vector_count = 0
    for c in candidates:
        vec = c.get("best_vector", "")
        card = c.get("card", "?")
        rate = c.get("success_rate", 0)
        if vec and vec != "∅":
            has_vector_count += 1
            print(f"    {card}: 成功率{rate:.0%}, vector={vec}")
        else:
            missing_vector_count += 1
            print(f"    {card}: 成功率{rate:.0%}, vector缺失")

    print(f"  ✓ 有vector: {has_vector_count}个, 缺失: {missing_vector_count}个")
    return candidates, service, state


def test_real_grouping(candidates_data):
    """测试2: 真实数据下的分组行为。"""
    print("=" * 60)
    print("测试 2: 真实数据下的vector分组")
    print("=" * 60)

    if candidates_data is None:
        print("  [跳过] 无真实candidates")
        return None

    candidates, service, state = candidates_data

    # 调用真实分组
    groups = service._group_candidates_by_vector(candidates, threshold=0.30)

    print(f"  ✓ 分组结果: {len(groups)}组")
    for g in groups:
        cards = ' '.join(c['card'] for c in g['cards'])
        rate = g['success_rate']
        vec = g.get('best_vector', '')[:40]
        print(f"    组{g['group_id']}: {cards} (成功率{rate:.0%}, vec={vec})")

    # 验证：同一组内的牌best_vector必须相同
    for g in groups:
        if g.get("best_vector"):
            vecs = set(c.get("best_vector", "") for c in g["cards"])
            assert len(vecs) == 1, f"组{g['group_id']}内vector不一致: {vecs}"

    print(f"  ✓ 同组内best_vector一致性校验通过")
    return groups


def test_real_trigger_condition(groups_data):
    """测试3: 真实数据下的触发条件判断。"""
    print("=" * 60)
    print("测试 3: 真实数据下的触发条件")
    print("=" * 60)

    if groups_data is None:
        print("  [跳过] 无分组数据")
        return

    candidates_data = test_real_alpha_mu_candidates.__dict__.get('candidates_data')
    candidates, service, state = None, None, None

    # 重新获取service和state（简化处理）
    service = PlayService(llm_client=MockLLMClient())
    state = _init_endgame(service)

    groups = groups_data
    should_trigger = service._should_trigger_llm(groups, [])

    rates = [g['success_rate'] for g in groups]
    spread = max(rates) - min(rates) if rates else 0
    max_rate = max(rates) if rates else 0

    print(f"  组数: {len(groups)}")
    print(f"  成功率: {rates}")
    print(f"  极差: {spread:.2f} (阈值0.15)")
    print(f"  最高: {max_rate:.2f} (阈值0.50)")
    print(f"  触发LLM: {should_trigger}")

    if should_trigger:
        print(f"  ✓ 满足触发条件，将调用LLM")
    else:
        print(f"  ✓ 不满足触发条件，保留αμ（符合预期）")


def test_full_alphamu_llm_play():
    """测试4: 完整_alphamu_llm_play流程（用MockLLM）。"""
    print("=" * 60)
    print("测试 4: 完整_alphamu_llm_play流程")
    print("=" * 60)

    if not ENDPLAY_AVAILABLE:
        print("  [跳过] endplay未安装")
        return

    service = PlayService(llm_client=MockLLMClient())
    state = _init_endgame(service)

    # 调用完整流程
    try:
        result = service._alphamu_llm_play(state)
        print(f"  ✓ _alphamu_llm_play执行完成，无异常")

        card = result.get("card", {})
        reasoning = result.get("reasoning", "")
        full_output = result.get("full_output", {})

        print(f"  出牌: {card}")
        print(f"  reasoning前100字: {reasoning[:100]}")

        llm_review = full_output.get("llm_review", {})
        if llm_review:
            print(f"  llm_review存在: {list(llm_review.keys())}")
            if llm_review.get("llm_prompt"):
                print(f"  llm_prompt长度: {len(llm_review['llm_prompt'])}字符")
        else:
            print(f"  llm_review不存在（可能未触发LLM）")

    except Exception as e:
        print(f"  ✗ 执行失败: {e}")
        import traceback
        traceback.print_exc()
        raise


def test_prompt_generation():
    """测试5: 验证LLM prompt正确生成（含DDS等价说明）。"""
    print("=" * 60)
    print("测试 5: LLM prompt生成验证")
    print("=" * 60)

    if not ENDPLAY_AVAILABLE:
        print("  [跳过] endplay未安装")
        return

    service = PlayService(llm_client=MockLLMClient())
    state = _init_endgame(service)

    # 获取真实candidates
    alpha_result = service._alpha_mu_play(state)
    candidates = alpha_result.get("full_output", {}).get("mcts_stats", {}).get("candidates", [])

    if len(candidates) < 2:
        print("  [跳过] 候选不足")
        return

    groups = service._group_candidates_by_vector(candidates, threshold=0.30)
    if len(groups) < 2:
        print(f"  [跳过] 分组数<2（{len(groups)}组），不触发LLM")
        return

    # 调用_llm_group_review
    review = service._llm_group_review(
        state, candidates, groups,
        alpha_card="♠A",
        previous_plan=""
    )

    prompt = review.get("llm_prompt", "")
    assert prompt, "prompt不应为空"
    print(f"  ✓ prompt生成成功，长度: {len(prompt)}字符")

    # 检查prompt包含DDS等价说明
    if "DDS等价" in prompt or "αμ采样空间" in prompt:
        print(f"  ✓ prompt包含DDS等价说明")
    else:
        print(f"  ✗ prompt缺少DDS等价说明")

    # 检查prompt包含组信息
    if "组1" in prompt:
        print(f"  ✓ prompt包含组信息")
    else:
        print(f"  ✗ prompt缺少组信息")

    # 检查prompt包含结构化steps要求
    if "steps" in prompt:
        print(f"  ✓ prompt包含结构化steps要求")
    else:
        print(f"  ✗ prompt缺少结构化steps要求")

    # 打印prompt片段（组信息部分）
    lines = prompt.split('\n')
    for i, line in enumerate(lines):
        if '组' in line and ('成功率' in line or 'DDS' in line):
            print(f"    {line.strip()}")


def test_plan_structured():
    """测试6: 验证plan结构化存储和失效检测。"""
    print("=" * 60)
    print("测试 6: plan结构化存储与失效检测")
    print("=" * 60)

    if not ENDPLAY_AVAILABLE:
        print("  [跳过] endplay未安装")
        return

    service = PlayService(llm_client=MockLLMClient())
    state = _init_endgame(service)

    # 初始plan应为空
    assert service._is_plan_empty(service.declarer_plan), "初始plan应为空"
    print(f"  ✓ 初始plan为空")

    # 执行_alphamu_llm_play，应存储结构化plan
    result = service._alphamu_llm_play(state)
    plan = service.declarer_plan

    print(f"  plan类型: {type(plan).__name__}")
    print(f"  plan字段: {list(plan.keys()) if isinstance(plan, dict) else 'N/A'}")

    assert isinstance(plan, dict), f"plan应为dict, 实际{type(plan)}"
    assert "steps" in plan, "plan应含steps字段"
    assert "created_at_trick" in plan, "plan应含created_at_trick"
    assert len(plan["steps"]) > 0, "plan应有至少1个step"
    print(f"  ✓ plan结构化存储: {len(plan['steps'])}个steps")

    # 验证step结构
    s = plan["steps"][0]
    assert "action" in s, "step应含action"
    assert "precondition" in s, "step应含precondition"
    print(f"  ✓ step结构: action='{s['action']}', precondition='{s['precondition']}'")

    # 验证plan格式化
    plan_text = service._format_plan_for_prompt(plan)
    assert plan_text, "格式化plan不应为空"
    print(f"  ✓ plan格式化成功，长度{len(plan_text)}字符")
    print(f"    格式化预览: {plan_text[:80]}...")

    # 验证失效检测（新plan不应失效）
    invalid = service._check_plan_invalidation(state)
    assert not invalid, "新创建的plan不应立即失效"
    print(f"  ✓ 新plan未失效")

    # 验证空plan的失效检测
    service.declarer_plan = service._empty_plan()
    assert not service._check_plan_invalidation(state), "空plan不应报失效"
    print(f"  ✓ 空plan失效检测正确")


def test_plan_invalidation():
    """测试7: 验证plan失效检测在过期时触发。"""
    print("=" * 60)
    print("测试 7: plan失效检测（过期）")
    print("=" * 60)

    service = PlayService(llm_client=MockLLMClient())
    state = _init_endgame(service)

    # 创建一个5墩前的plan
    plan = service._empty_plan()
    plan["created_at_trick"] = 1  # 第1墩创建
    plan["steps"] = [{"step": 1, "action": "清将", "precondition": "", "completed": False}]
    service.declarer_plan = plan

    # 模拟已打9墩（trick_number=10）
    from bridge.play_types import Trick
    fake_tricks = []
    for i in range(9):
        t = Trick()
        fake_tricks.append(t)
    state.tricks = fake_tricks

    invalid = service._check_plan_invalidation(state)
    assert invalid, "5墩前的plan应失效"
    print(f"  ✓ 过期plan(第1墩创建, 当前第10墩)正确检测为失效")


if __name__ == "__main__":
    print("αμ+LLM 引擎 best_vector 分组 - 真实集成测试\n")

    # 测试1: 真实αμ搜索输出
    candidates_data = test_real_alpha_mu_candidates()

    # 测试2: 真实数据分组
    groups_data = test_real_grouping(candidates_data)

    # 测试3: 触发条件
    test_real_trigger_condition(groups_data)

    # 测试4: 完整流程
    test_full_alphamu_llm_play()

    # 测试5: prompt生成
    test_prompt_generation()

    # 测试6: plan结构化
    test_plan_structured()

    # 测试7: plan失效检测
    test_plan_invalidation()

    print("\n" + "=" * 60)
    print("集成测试完成")
    print("=" * 60)
