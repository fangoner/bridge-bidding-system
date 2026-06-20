"""优先级 5/6/7 端到端测试。

验证：
1. 防守信号模型（态度/张数/花色偏好）正确收集和解读
2. LLM 提示词注入同伴信号
3. LLM 输出校验层正确检测违规并回退
4. 首攻 DD+LLM 融合流程（不实际调用 LLM，验证结构）
"""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from bridge.play_types import Card, PlayState, PlayPhase, Contract, POSITION_ORDER, PARTNERS
from bridge.play_engine import PlayEngine
from bridge.mcts.signals import (
    collect_all_signals, get_partner_signals,
    format_partner_signals_for_prompt, get_signal_constraints,
)
from bridge.mcts.llm_validator import validate_llm_play, ValidationResult


# 测试用牌局
TEST_HANDS = {
    "南": {"spades": "AKQ", "hearts": "53", "diamonds": "84", "clubs": "J75329"},
    "西": {"spades": "543", "hearts": "KQ8", "diamonds": "KQJ", "clubs": "864T"},
    "北": {"spades": "JT9876", "hearts": "AJT", "diamonds": "A53", "clubs": "Q"},
    "东": {"spades": "2", "hearts": "97642", "diamonds": "T9762", "clubs": "AK"},
}


def _make_state():
    """创建初始 PlayState（3NT 定约，南家庄）。"""
    engine = PlayEngine()
    contract = Contract.from_str("3NT", "南")
    return engine.initialize(TEST_HANDS, contract)


def test_attitude_signal():
    """测试1：态度信号收集（高牌=欢迎，低牌=不欢迎）"""
    print("\n=== 测试1：态度信号 ===")
    state = _make_state()

    # 西领黑桃5，北跟黑桃J（明手），东跟黑桃2（低牌=不欢迎），南赢黑桃A
    state.current_trick.add_card("西", Card(suit="♠", rank="5"), False, "lead", "low")
    state.current_trick.add_card("北", Card(suit="♠", rank="J"), False, "follow", "high")
    state.current_trick.add_card("东", Card(suit="♠", rank="2"), False, "follow", "low")
    state.current_trick.add_card("南", Card(suit="♠", rank="A"), False, "win", "high")

    signals = collect_all_signals(state)
    print(f"  信号数: {len(signals)}")
    for s in signals:
        print(f"  - {s}")

    # 西和东都是防守方（庄家=南，明手=北）
    # 西领黑桃5（rank_value=3，<8 → 低牌=不欢迎）
    # 东跟黑桃2（rank_value=0，<8 → 低牌=不欢迎）
    attitude_signals = [s for s in signals if s.signal_type == "attitude"]
    assert len(attitude_signals) == 2
    positions = {s.position for s in attitude_signals}
    assert positions == {"西", "东"}
    assert all(not s.is_high for s in attitude_signals)  # 都是低牌
    print("  ✓ 态度信号收集正确（西、东家低牌=不欢迎）")


def test_count_signal():
    """测试2：张数信号（同花色第二次跟牌）"""
    print("\n=== 测试2：张数信号 ===")
    state = _make_state()

    # 第一墩：西领黑桃5，北跟黑桃J，东跟黑桃2，南赢黑桃A
    # 用 play_card 自动推进墩
    state.play_card("西", Card(suit="♠", rank="5"))
    state.play_card("北", Card(suit="♠", rank="J"))
    state.play_card("东", Card(suit="♠", rank="2"))
    state.play_card("南", Card(suit="♠", rank="A"))
    # 第一墩完成，南家赢，南家领出第二墩

    # 第二墩：南领黑桃K，西跟黑桃4（第二次跟黑桃→张数信号），北跟黑桃T，东无黑桃垫红桃9
    state.play_card("南", Card(suit="♠", rank="K"))
    state.play_card("西", Card(suit="♠", rank="4"))
    state.play_card("北", Card(suit="♠", rank="T"))
    state.play_card("东", Card(suit="♥", rank="9"))

    signals = collect_all_signals(state)
    print(f"  信号数: {len(signals)}")
    for s in signals:
        print(f"  - {s}")

    # 西家第二次跟黑桃（第一墩跟5，第二墩跟4）→ 张数信号
    # 先大后小=偶数张
    count_signals = [s for s in signals if s.signal_type == "count"]
    west_count = [s for s in count_signals if s.position == "西"]
    assert len(west_count) == 1
    assert west_count[0].suit == "♠"
    # 西第一墩跟5（rank_value=3），第二墩跟4（rank_value=2），先大后小=偶数张
    assert west_count[0].is_high is True  # 偶数张
    print("  ✓ 张数信号收集正确（西家先大后小=偶数张）")

    # 东家第二墩不跟黑桃垫红桃9 → 花色偏好信号
    sp_signals = [s for s in signals if s.signal_type == "suit_preference"]
    east_sp = [s for s in sp_signals if s.position == "东"]
    assert len(east_sp) == 1
    assert east_sp[0].suit == "♥"
    print("  ✓ 花色偏好信号收集正确（东家垫红桃）")


def test_partner_signals_for_prompt():
    """测试3：同伴信号提示词注入"""
    print("\n=== 测试3：同伴信号提示词 ===")
    state = _make_state()

    # 西领黑桃5，东跟黑桃2（低牌=不欢迎）
    state.current_trick.add_card("西", Card(suit="♠", rank="5"), False, "lead", "low")
    state.current_trick.add_card("北", Card(suit="♠", rank="J"), False, "follow", "high")
    state.current_trick.add_card("东", Card(suit="♠", rank="2"), False, "follow", "low")
    state.current_trick.add_card("南", Card(suit="♠", rank="A"), False, "win", "high")

    # 当前出牌者是西，同伴是东
    prompt_text = format_partner_signals_for_prompt(state, "西")
    print(f"  提示词: {prompt_text[:200]}...")
    assert "同伴已发防守信号" in prompt_text
    assert "东" in prompt_text
    assert "不欢迎" in prompt_text

    # 庄家方不应有同伴信号提示
    prompt_declarer = format_partner_signals_for_prompt(state, "南")
    assert prompt_declarer == ""
    print("  ✓ 庄家方无同伴信号提示")


def test_signal_constraints():
    """测试4：信号约束提取"""
    print("\n=== 测试4：信号约束 ===")
    state = _make_state()

    # 东跟黑桃2（低牌=不欢迎 → 黑桃偏短）
    state.current_trick.add_card("西", Card(suit="♠", rank="5"), False, "lead", "low")
    state.current_trick.add_card("北", Card(suit="♠", rank="J"), False, "follow", "high")
    state.current_trick.add_card("东", Card(suit="♠", rank="2"), False, "follow", "low")
    state.current_trick.add_card("南", Card(suit="♠", rank="A"), False, "win", "high")

    constraints = get_signal_constraints(state)
    print(f"  约束: {constraints}")

    # 东家黑桃应有负约束（不欢迎=偏短）
    assert "东" in constraints
    assert "♠" in constraints["东"]
    assert constraints["东"]["♠"] < 0  # 偏短
    print("  ✓ 信号约束提取正确（东家黑桃偏短）")


def test_validator_legal_play():
    """测试5：校验器 - 合法出牌通过"""
    print("\n=== 测试5：校验器合法出牌 ===")
    state = _make_state()

    # 首攻阶段，西家可出任何手牌
    # 西家手牌：黑桃543, 红桃KQ8, 方块KQJ, 梅花864T
    playable = [
        Card(suit="♠", rank="5"), Card(suit="♠", rank="4"), Card(suit="♠", rank="3"),
        Card(suit="♥", rank="K"), Card(suit="♥", rank="Q"), Card(suit="♥", rank="8"),
        Card(suit="♦", rank="K"), Card(suit="♦", rank="Q"), Card(suit="♦", rank="J"),
        Card(suit="♣", rank="8"), Card(suit="♣", rank="6"), Card(suit="♣", rank="4"),
        Card(suit="♣", rank="T"),
    ]

    # 选黑桃5（合法首攻）
    card = Card(suit="♠", rank="5")
    result = validate_llm_play(card, playable, state)
    print(f"  校验结果: {result}")
    assert result.valid is True
    print("  ✓ 合法首攻通过校验")


def test_validator_illegal_card():
    """测试6：校验器 - 非法牌（不在 playable 中）"""
    print("\n=== 测试6：校验器非法牌 ===")
    state = _make_state()

    playable = [
        Card(suit="♠", rank="5"), Card(suit="♠", rank="4"), Card(suit="♠", rank="3"),
    ]

    # 选黑桃A（不在手牌中）
    card = Card(suit="♠", rank="A")
    result = validate_llm_play(card, playable, state)
    print(f"  校验结果: {result}")
    assert result.valid is False
    assert result.severity == "error"
    assert "不在可出牌列表中" in result.violation
    print("  ✓ 非法牌被正确检测")


def test_validator_fourth_hand_winning():
    """测试7：校验器 - 第四家能赢却出小牌"""
    print("\n=== 测试7：第四家能赢却出小牌 ===")
    state = _make_state()

    # 设置局面：庄家=南，明手=北，防守方=西/东
    # 当前墩：西领红桃3，北跟红桃5，东跟红桃2，南是第四家
    # 南手牌有红桃A，能赢墩，定约3NT需9墩
    # 假设南已赢8墩，还需1墩成约

    # 先完成几墩让南家赢8墩
    # 简化：直接设置 declarer_tricks
    state.declarer_tricks = 8  # 还需1墩成约
    state.defender_tricks = 4

    # 当前墩：西领红桃3，北跟红桃5，东跟红桃2
    state.current_trick.add_card("西", Card(suit="♥", rank="3"), False, "lead", "low")
    state.current_trick.add_card("北", Card(suit="♥", rank="5"), False, "follow", "low")
    state.current_trick.add_card("东", Card(suit="♥", rank="2"), False, "follow", "low")

    # 南是第四家，手牌有红桃A（能赢）和红桃4（不能赢）
    # 但南实际手牌红桃是53，3已出，剩5（已出给北？不对）
    # 重新设计：南手牌红桃A,4
    # playable 应该是南能出的牌
    playable = [Card(suit="♥", rank="A"), Card(suit="♥", rank="4")]

    # LLM 选了红桃4（小牌，不能赢）
    card = Card(suit="♥", rank="4")
    result = validate_llm_play(card, playable, state)
    print(f"  校验结果: {result}")
    assert result.valid is False
    assert "第四家" in result.violation or "应赢墩" in result.violation
    print("  ✓ 第四家能赢却出小牌被检测")


def test_validator_second_hand_cover():
    """测试8：校验器 - 第二家有A不盖K"""
    print("\n=== 测试8：第二家有A不盖K ===")
    state = _make_state()

    # 设置局面：西领黑桃K，南是第二家，手牌有黑桃A
    # 但南是庄家方，西是防守方领出
    # 西领黑桃K，南应该盖A（否则K赢墩）
    state.current_trick.add_card("西", Card(suit="♠", rank="K"), False, "lead", "high")

    # 南手牌有黑桃A和小牌
    playable = [Card(suit="♠", rank="A"), Card(suit="♠", rank="3")]

    # LLM 选了黑桃3（小牌，不盖A）
    card = Card(suit="♠", rank="3")
    result = validate_llm_play(card, playable, state)
    print(f"  校验结果: {result}")
    # 西是防守方，南是庄家方，西领K，南有A应该盖
    assert result.valid is False
    assert "应盖A" in result.violation
    print("  ✓ 第二家有A不盖K被检测")


def test_play_service_validator_integration():
    """测试9：PlayService 校验层集成"""
    print("\n=== 测试9：PlayService 校验层集成 ===")
    from bridge.play_service import PlayService

    service = PlayService(llm_client=None)
    state = _make_state()

    # 西家首攻，手牌有黑桃543等
    playable = [
        Card(suit="♠", rank="5"), Card(suit="♠", rank="4"), Card(suit="♠", rank="3"),
        Card(suit="♥", rank="K"),
    ]

    # 测试合法牌
    card, warning = service._validate_and_fallback(
        Card(suit="♠", rank="5"), playable, state)
    assert warning == ""
    assert card == Card(suit="♠", rank="5")
    print("  ✓ 合法牌通过校验")

    # 测试非法牌（不在 playable 中）
    card, warning = service._validate_and_fallback(
        Card(suit="♠", rank="A"), playable, state)
    assert warning != ""
    assert "校验失败" in warning
    assert card in playable  # 回退到 playable 中的牌
    print(f"  ✓ 非法牌回退到 {card}")


def test_play_service_opening_lead_structure():
    """测试10：首攻 DD+LLM 融合结构（不实际调用 LLM/DD）"""
    print("\n=== 测试10：首攻融合结构 ===")
    from bridge.play_service import PlayService

    service = PlayService(llm_client=None)
    state = _make_state()

    # 验证 _opening_lead_play 方法存在
    assert hasattr(service, '_opening_lead_play')
    print("  ✓ _opening_lead_play 方法存在")

    # 验证 _apply_dd_override 方法存在
    assert hasattr(service, '_apply_dd_override')
    print("  ✓ _apply_dd_override 方法存在")

    # 测试 _apply_dd_override 无 DD 候选时直接返回
    result = {"card": {"suit": "♠", "rank": "5"}, "reasoning": "test"}
    result = service._apply_dd_override(result, [])
    assert result["card"]["suit"] == "♠"
    print("  ✓ _apply_dd_override 空候选时直接返回")


if __name__ == "__main__":
    test_attitude_signal()
    test_count_signal()
    test_partner_signals_for_prompt()
    test_signal_constraints()
    test_validator_legal_play()
    test_validator_illegal_card()
    test_validator_fourth_hand_winning()
    test_validator_second_hand_cover()
    test_play_service_validator_integration()
    test_play_service_opening_lead_structure()
    print("\n=== 全部测试通过 ===")
