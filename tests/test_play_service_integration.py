"""PlayService 模块集成测试：覆盖从叫牌结束到出牌完成的全流程。

测试场景设计：
1. 初始化：发牌 + 定约 + 角色设置
2. 首攻阶段：Tiered 引擎触发 opening_lead 分支
3. 中盘出牌：DD / MCTS / Tiered 引擎切换
4. 残局阶段：αμ 搜索触发（≤8张）
5. 全流程：完整打完一墩（4家出牌 + 墩判定）
6. 撤销操作：undo_last_card 一致性
7. 完成判定：13墩打完后的结果计算
8. 引擎一致性：同一局面下多引擎返回合法出牌

运行方式：
    python tests/test_play_service_integration.py
"""

import sys
import os
import asyncio
import inspect

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from bridge.play_service import PlayService
from bridge.play_types import (
    Card, PlayState, Contract, PlayPhase, PlayerRole, POSITION_ORDER, PARTNERS,
)
from bridge.mcts.alpha_mu import ENDPLAY_AVAILABLE as ALPHA_MU_ENDPLAY_OK
from bridge.mcts.dd_search import ENDPLAY_AVAILABLE as DD_ENDPLAY_OK


# ──────────────────────────────────────────────────────────────────
# 测试夹具：标准 3NT 定约场景
# ──────────────────────────────────────────────────────────────────

class MockLLMClient:
    """模拟 LLM 客户端：返回固定出牌，避免真实 API 调用。"""

    def __init__(self, default_card: str = "♠A"):
        self.default_card = default_card
        self.model = "mock-model"

    def chat(self, system_prompt: str, temperature: float = 0.7,
             max_tokens: int = 1024, **kwargs) -> str:
        """同步 chat：返回包含默认牌的文本。"""
        return f"我推荐出 {self.default_card}。这是基于局面分析的最优选择。"

    def chat_json(self, system_prompt: str, user_prompt: str = "",
                  temperature: float = 0, max_tokens: int = 1024,
                  **kwargs) -> dict:
        """同步 chat_json：返回空约束（跳过约束提取）。"""
        return {}

    async def chat_async(self, system_prompt: str, temperature: float = 0.7,
                         max_tokens: int = 1024, **kwargs) -> str:
        return self.chat(system_prompt, temperature, max_tokens, **kwargs)


# 南家庄家，3NT 定约。南家强牌，北家有长套♠
# 每家 13 张：南 3+3+3+4=13, 西 3+4+2+4=13, 北 4+3+3+3=13, 东 3+4+4+2=13
STANDARD_HANDS = {
    "南": {"spades": "AKQ", "hearts": "J32", "diamonds": "AKQ", "clubs": "5432"},
    "西": {"spades": "JT9", "hearts": "Q876", "diamonds": "J5", "clubs": "T876"},
    "北": {"spades": "8765", "hearts": "AKQ", "diamonds": "432", "clubs": "AKQ"},
    "东": {"spades": "432", "hearts": "T954", "diamonds": "T987", "clubs": "J5"},
}

# 残局场景：每手 4 张牌，用于触发 αμ
ENDGAME_HANDS = {
    "南": {"spades": "AK", "hearts": "A", "diamonds": "A"},
    "西": {"spades": "Q2", "hearts": "K", "diamonds": "K"},
    "北": {"spades": "J3", "hearts": "Q", "diamonds": "Q"},
    "东": {"spades": "T4", "hearts": "J", "diamonds": "J"},
}

BIDDING_SEQUENCE = "(南)1NT-(西)pass-(北)3NT-(东)pass-(南)pass-(西)pass"
BID_HISTORY = "(南)1NT-(西)pass-(北)3NT-(东)pass-(南)pass-(西)pass"


def _make_service(llm_client=None) -> PlayService:
    """构建 PlayService 实例。

    Args:
        llm_client: LLM 客户端；None 时使用 MockLLMClient（避免真实 API 调用）。
    """
    if llm_client is None:
        llm_client = MockLLMClient()
    return PlayService(llm_client=llm_client)


def _init_standard_game(service: PlayService, declarer: str = "南",
                       contract_str: str = "3NT") -> PlayState:
    """初始化标准 3NT 定约游戏。"""
    state = service.initialize(
        hands=STANDARD_HANDS,
        contract_str=contract_str,
        declarer=declarer,
        player_roles={pos: PlayerRole.AI.value for pos in POSITION_ORDER},
        bidding_sequence=BIDDING_SEQUENCE,
        bid_history=BID_HISTORY,
    )
    return state


def _init_endgame_game(service: PlayService, declarer: str = "南",
                       contract_str: str = "3NT") -> PlayState:
    """初始化残局场景（每手4张牌，已打9墩）。"""
    state = service.initialize(
        hands=ENDGAME_HANDS,
        contract_str=contract_str,
        declarer=declarer,
        player_roles={pos: PlayerRole.AI.value for pos in POSITION_ORDER},
        bidding_sequence=BIDDING_SEQUENCE,
        bid_history=BID_HISTORY,
    )
    # 模拟已打完 9 墩：庄家 5 墩，防守 4 墩
    state.declarer_tricks = 5
    state.defender_tricks = 4
    state.phase = PlayPhase.PLAYING
    state.current_player = declarer  # 庄家先出
    state.lead_player = declarer
    service.bid_constraints = {}  # 跳过 LLM 约束提取
    return state


# ──────────────────────────────────────────────────────────────────
# 测试用例
# ──────────────────────────────────────────────────────────────────

def test_1_initialization():
    """测试 1: 游戏初始化。"""
    print("=" * 60)
    print("测试 1: 游戏初始化（发牌 + 定约 + 角色）")
    print("=" * 60)

    service = _make_service()
    state = _init_standard_game(service)

    # 定约解析正确
    assert state.contract.level == 3
    assert state.contract.suit == "NT"
    assert state.contract.declarer == "南"
    assert state.contract.tricks_needed == 9
    print(f"  ✓ 定约: {state.contract}, 需 {state.contract.tricks_needed} 墩")

    # 明手正确（庄家伙伴）
    assert state.dummy == "北"
    print(f"  ✓ 明手: {state.dummy}")

    # 首攻者：庄家左手
    expected_lead = POSITION_ORDER[(POSITION_ORDER.index("南") + 1) % 4]
    assert state.lead_player == expected_lead
    assert state.current_player == expected_lead
    print(f"  ✓ 首攻者: {state.lead_player}（庄家左手）")

    # 手牌解析正确
    assert len(state.hands["南"]) == 13
    assert len(state.hands["北"]) == 13
    assert Card("♠", "A") in state.hands["南"]
    print(f"  ✓ 手牌: 南 13 张, 北 13 张, ♠A 在南家")

    # 阶段为 LEAD
    assert state.phase == PlayPhase.LEAD
    print(f"  ✓ 阶段: {state.phase}")

    # 引擎状态
    assert service.alpha_mu_search is not None or not ALPHA_MU_ENDPLAY_OK
    assert service.dd_search is not None
    print(f"  ✓ 引擎: αμ={'on' if service.alpha_mu_search else 'off'}, DD=on")

    print("  测试通过!\n")


def test_2_first_playable_cards():
    """测试 2: 首攻阶段合法出牌。"""
    print("=" * 60)
    print("测试 2: 首攻阶段合法出牌")
    print("=" * 60)

    service = _make_service()
    state = _init_standard_game(service)

    # 首攻者西家
    playable = service.get_playable_cards("西")
    assert len(playable) == 13, f"西家应可出 13 张, 实际 {len(playable)}"
    print(f"  ✓ 西家首攻可选: {len(playable)} 张")

    # 当前墩为空，所有手牌均可出
    assert len(state.current_trick.cards) == 0
    print(f"  ✓ 当前墩为空，无跟牌限制")

    print("  测试通过!\n")


def test_3_full_trick_flow():
    """测试 3: 完整打完一墩（4家出牌 + 墩判定）。"""
    print("=" * 60)
    print("测试 3: 完整打完一墩")
    print("=" * 60)

    service = _make_service()
    state = _init_standard_game(service)

    initial_trick_count = len(state.tricks)
    initial_decl_tricks = state.declarer_tricks
    initial_def_tricks = state.defender_tricks

    # 西家首攻 ♠T
    ok, msg = service.play_card("西", Card("♠", "T"), is_ai=True, reason="首攻")
    assert ok, f"西家出 ♠T 失败: {msg}"
    assert state.current_player == "北"
    print(f"  ✓ 西家 ♠T → 下一家: 北")

    # 北家跟 ♠5
    ok, msg = service.play_card("北", Card("♠", "5"), is_ai=True)
    assert ok, f"北家出 ♠5 失败: {msg}"
    assert state.current_player == "东"
    print(f"  ✓ 北家 ♠5 → 下一家: 东")

    # 东家跟 ♠2
    ok, msg = service.play_card("东", Card("♠", "2"), is_ai=True)
    assert ok, f"东家出 ♠2 失败: {msg}"
    assert state.current_player == "南"
    print(f"  ✓ 东家 ♠2 → 下一家: 南")

    # 南家跟 ♠A（赢墩）
    ok, msg = service.play_card("南", Card("♠", "A"), is_ai=True)
    assert ok, f"南家出 ♠A 失败: {msg}"
    print(f"  ✓ 南家 ♠A → 墩完成")

    # 墩判定：♠A 最大，南家庄家方赢墩
    assert len(state.tricks) == initial_trick_count + 1
    assert state.declarer_tricks == initial_decl_tricks + 1
    assert state.current_player == "南"  # 赢家首攻下一墩
    print(f"  ✓ 墩判定: 庄家方赢墩 (decl={state.declarer_tricks}, def={state.defender_tricks})")
    print(f"  ✓ 下一墩首攻者: {state.current_player}")

    # 当前墩已清空
    assert len(state.current_trick.cards) == 0
    print(f"  ✓ 当前墩已清空，准备下一墩")

    print("  测试通过!\n")


def test_4_follow_suit_rule():
    """测试 4: 跟花色规则。"""
    print("=" * 60)
    print("测试 4: 跟花色规则")
    print("=" * 60)

    service = _make_service()
    state = _init_standard_game(service)

    # 西家首攻 ♥Q
    service.play_card("西", Card("♥", "Q"), is_ai=True)

    # 北家必须跟 ♥（有 ♥AKQ）
    playable_north = service.get_playable_cards("北")
    assert all(c.suit == "♥" for c in playable_north), f"北家必须跟 ♥, 实际 {playable_north}"
    print(f"  ✓ 北家必须跟 ♥: {[str(c) for c in playable_north]}")

    # 北家出 ♥K
    service.play_card("北", Card("♥", "K"), is_ai=True)

    # 东家必须跟 ♥（有 ♥T954）
    playable_east = service.get_playable_cards("东")
    assert all(c.suit == "♥" for c in playable_east)
    print(f"  ✓ 东家必须跟 ♥: {[str(c) for c in playable_east]}")

    # 东家出 ♥4
    service.play_card("东", Card("♥", "4"), is_ai=True)

    # 南家有 ♥J32，必须跟 ♥
    playable_south = service.get_playable_cards("南")
    assert all(c.suit == "♥" for c in playable_south)
    print(f"  ✓ 南家必须跟 ♥: {[str(c) for c in playable_south]}")

    # 试图出非 ♥ 牌应失败
    ok, msg = service.play_card("南", Card("♠", "K"), is_ai=True)
    assert not ok, "南家出 ♠K 应失败（必须跟 ♥）"
    print(f"  ✓ 违规检测: 南家试图出 ♠K 被拒绝 ({msg})")

    print("  测试通过!\n")


def test_5_undo_last_card():
    """测试 5: 撤销出牌。"""
    print("=" * 60)
    print("测试 5: 撤销出牌")
    print("=" * 60)

    service = _make_service()
    state = _init_standard_game(service)

    # 西家出 ♠T
    service.play_card("西", Card("♠", "T"), is_ai=True)
    assert len(state.current_trick.cards) == 1
    assert Card("♠", "T") not in state.hands["西"]
    print(f"  ✓ 出牌后: 当前墩 1 张, 西家手牌 12 张")

    # 撤销
    ok, msg = service.undo_last_card()
    assert ok, f"撤销失败: {msg}"
    assert len(state.current_trick.cards) == 0
    assert Card("♠", "T") in state.hands["西"]
    assert state.current_player == "西"
    print(f"  ✓ 撤销后: 当前墩 0 张, 西家手牌 13 张, 当前出牌者回到西")

    print("  测试通过!\n")


def test_6_dd_engine():
    """测试 6: DD 引擎返回合法出牌。"""
    print("=" * 60)
    print("测试 6: DD 引擎")
    print("=" * 60)

    if not DD_ENDPLAY_OK:
        print("  ⚠ 跳过: endplay 未安装")
        return

    service = _make_service()
    _init_standard_game(service)

    loop = asyncio.new_event_loop()
    try:
        result = loop.run_until_complete(
            service.get_ai_play(use_dd=True, dd_samples=10)
        )
    finally:
        loop.close()

    card = result.get("card")
    assert card is not None, f"DD 应返回出牌, 实际: {result}"
    card_obj = Card(suit=card["suit"], rank=card["rank"])
    playable = service.get_playable_cards()
    assert card_obj in playable, f"DD 推荐 {card_obj} 不在合法出牌中"
    print(f"  ✓ DD 推荐: {card_obj}")
    print(f"  ✓ 推理: {result.get('reasoning', '')[:100]}")

    print("  测试通过!\n")


def test_7_mcts_engine():
    """测试 7: MCTS 引擎返回合法出牌。"""
    print("=" * 60)
    print("测试 7: MCTS 引擎")
    print("=" * 60)

    service = _make_service()
    _init_standard_game(service)

    loop = asyncio.new_event_loop()
    try:
        result = loop.run_until_complete(service.get_ai_play(use_mcts=True))
    finally:
        loop.close()

    card = result.get("card")
    assert card is not None, f"MCTS 应返回出牌, 实际: {result}"
    card_obj = Card(suit=card["suit"], rank=card["rank"])
    playable = service.get_playable_cards()
    assert card_obj in playable, f"MCTS 推荐 {card_obj} 不在合法出牌中"
    print(f"  ✓ MCTS 推荐: {card_obj}")
    print(f"  ✓ 推理: {result.get('reasoning', '')[:100]}")

    print("  测试通过!\n")


def test_8_dd_alphamu_llm_midgame():
    """测试 8: DD-αμ-LLM 引擎中盘（DD+LLM审查）。"""
    print("=" * 60)
    print("测试 8: DD-αμ-LLM 引擎中盘阶段")
    print("=" * 60)

    if not DD_ENDPLAY_OK:
        print("  ⚠ 跳过: endplay 未安装")
        return

    service = _make_service()
    _init_standard_game(service)

    loop = asyncio.new_event_loop()
    try:
        result = loop.run_until_complete(
            service.get_ai_play(use_dd_alphamu_llm=True, dd_samples=10, dd_alphamu_switch_cards=8)
        )
    finally:
        loop.close()

    card = result.get("card")
    engine_phase = result.get("full_output", {}).get("engine_phase", "")
    assert card is not None, f"DD-αμ-LLM 应返回出牌, 实际: {result}"
    card_obj = Card(suit=card["suit"], rank=card["rank"])
    playable = service.get_playable_cards()
    assert card_obj in playable, f"DD-αμ-LLM 推荐 {card_obj} 不在合法出牌中"
    print(f"  ✓ DD-αμ-LLM 推荐: {card_obj} (phase={engine_phase})")

    print("  测试通过!\n")


def test_9_dd_alphamu_llm_endgame_alpha_mu():
    """测试 9: DD-αμ-LLM 引擎残局阶段走 αμ。"""
    print("=" * 60)
    print("测试 9: DD-αμ-LLM 残局阶段")
    print("=" * 60)

    if not ALPHA_MU_ENDPLAY_OK:
        print("  ⚠ 跳过: endplay 未安装")
        return

    service = _make_service()
    _init_endgame_game(service)

    loop = asyncio.new_event_loop()
    try:
        result = loop.run_until_complete(
            service.get_ai_play(use_dd_alphamu_llm=True)
        )
    finally:
        loop.close()

    card = result.get("card")
    assert card is not None, f"αμ 应返回出牌, 实际: {result}"
    card_obj = Card(suit=card["suit"], rank=card["rank"])
    playable = service.get_playable_cards()
    assert card_obj in playable, f"αμ 推荐 {card_obj} 不在合法出牌中"
    print(f"  ✓ αμ 推荐: {card_obj}")
    print(f"  ✓ 推理: {result.get('reasoning', '')[:120]}")

    print("  测试通过!\n")


def test_10_perfect_dd_engine():
    """测试 10: Perfect DD 引擎（全知双明手）。"""
    print("=" * 60)
    print("测试 10: Perfect DD 引擎（全知）")
    print("=" * 60)

    if not DD_ENDPLAY_OK:
        print("  ⚠ 跳过: endplay 未安装")
        return

    service = _make_service()
    _init_standard_game(service)

    loop = asyncio.new_event_loop()
    try:
        result = loop.run_until_complete(service.get_ai_play(use_perfect=True))
    finally:
        loop.close()

    card = result.get("card")
    assert card is not None, f"Perfect DD 应返回出牌, 实际: {result}"
    card_obj = Card(suit=card["suit"], rank=card["rank"])
    playable = service.get_playable_cards()
    assert card_obj in playable, f"Perfect DD 推荐 {card_obj} 不在合法出牌中"
    print(f"  ✓ Perfect DD 推荐: {card_obj}")

    print("  测试通过!\n")


def test_11_engine_consistency():
    """测试 11: 多引擎在同一局面下都返回合法出牌。"""
    print("=" * 60)
    print("测试 11: 多引擎一致性")
    print("=" * 60)

    if not DD_ENDPLAY_OK:
        print("  ⚠ 跳过: endplay 未安装")
        return

    engines_to_test = [
        ("DD", {"use_dd": True, "dd_samples": 8}),
        ("MCTS", {"use_mcts": True}),
        ("DD-αμ-LLM", {"use_dd_alphamu_llm": True, "dd_samples": 8}),
        ("Perfect", {"use_perfect": True}),
    ]

    for engine_name, kwargs in engines_to_test:
        service = _make_service()
        _init_standard_game(service)

        loop = asyncio.new_event_loop()
        try:
            result = loop.run_until_complete(service.get_ai_play(**kwargs))
        finally:
            loop.close()

        card = result.get("card")
        assert card is not None, f"{engine_name} 未返回出牌"
        card_obj = Card(suit=card["suit"], rank=card["rank"])
        playable = service.get_playable_cards()
        assert card_obj in playable, f"{engine_name} 推荐 {card_obj} 不合法"
        print(f"  ✓ {engine_name}: {card_obj}")

    print("  测试通过!\n")


def test_12_complete_game_result():
    """测试 12: 完成判定与结果计算。"""
    print("=" * 60)
    print("测试 12: 完成判定与结果计算")
    print("=" * 60)

    service = _make_service()
    state = _init_standard_game(service)

    # 模拟打完 13 墩：庄家赢 9 墩（刚好成约）
    state.declarer_tricks = 9
    state.defender_tricks = 4
    state.phase = PlayPhase.COMPLETE
    state.tricks = [Trick_stub() for _ in range(13)]  # 占位

    assert service.is_complete()
    result = service.get_result()
    assert result is not None
    assert result["result"] == "made"
    assert result["tricks_made"] == 9
    print(f"  ✓ 成约判定: {result['message']}")

    # 模拟宕 1
    state.declarer_tricks = 8
    state.defender_tricks = 5
    result = service.get_result()
    assert result["result"] == "down"
    assert result["undertricks"] == 1
    print(f"  ✓ 宕墩判定: {result['message']}")

    print("  测试通过!\n")


class Trick_stub:
    """占位 Trick，用于完成判定测试。"""
    def __init__(self):
        from bridge.play_types import Trick
        self._real = Trick(trump="NT")
        self.cards = [("南", Card("♠", "A"))]  # 最小占位
    def is_complete(self):
        return True
    def winner(self):
        return "南"


def test_13_belief_tracker_reset():
    """测试 13: 信念跟踪器在新局开始时重置。"""
    print("=" * 60)
    print("测试 13: 信念跟踪器重置")
    print("=" * 60)

    service = _make_service()
    if service.belief_tracker is None:
        print("  ⚠ 跳过: belief_tracker 未启用")
        return

    # 模拟旧粒子
    service.belief_tracker.particles = ["old_particle_1", "old_particle_2"]
    service.belief_tracker.weights = [0.5, 0.5]
    print(f"  旧粒子数: {len(service.belief_tracker.particles)}")

    # 重新初始化
    _init_standard_game(service)

    assert len(service.belief_tracker.particles) == 0
    assert len(service.belief_tracker.weights) == 0
    print(f"  ✓ 重置后粒子数: {len(service.belief_tracker.particles)}")

    print("  测试通过!\n")


def test_14_doubled_contract():
    """测试 14: 加倍定约解析。"""
    print("=" * 60)
    print("测试 14: 加倍定约解析")
    print("=" * 60)

    service = _make_service()
    state = service.initialize(
        hands=STANDARD_HANDS,
        contract_str="3NT",
        declarer="南",
        doubled=True,
        bidding_sequence="(南)1NT-(西)X-(北)3NT-(东)pass-(南)pass-(西)pass",
        bid_history="(南)1NT-(西)X-(北)3NT",
    )

    assert state.contract.doubled is True
    assert state.contract.redoubled is False
    print(f"  ✓ 加倍定约: {state.contract}")

    print("  测试通过!\n")


def test_15_dd_alphamu_llm_structure():
    """测试 15: DD-αμ-LLM 引擎结构存在性。"""
    print("=" * 60)
    print("测试 15: DD-αμ-LLM 引擎结构")
    print("=" * 60)

    service = _make_service()

    # 验证 DD-αμ-LLM 引擎方法存在
    assert hasattr(service, "_dd_alphamu_llm_play"), "缺少 _dd_alphamu_llm_play 方法"
    assert hasattr(service, "_dd_llm_play"), "缺少 _dd_llm_play 方法"
    assert hasattr(service, "_group_candidates_by_tricks_vec"), "缺少 _group_candidates_by_tricks_vec 方法"
    print("  ✓ _dd_alphamu_llm_play: 存在")
    print("  ✓ _dd_llm_play: 存在")
    print("  ✓ _group_candidates_by_tricks_vec: 存在")

    # 验证方法签名
    sig = inspect.signature(service._dd_alphamu_llm_play)
    params = list(sig.parameters.keys())
    assert "state" in params
    assert "use_reasoning" in params
    assert "dd_samples" in params
    assert "switch_cards" in params
    print(f"  ✓ 方法签名: {params}")

    print("  测试通过!\n")


# ──────────────────────────────────────────────────────────────────
# 主入口
# ──────────────────────────────────────────────────────────────────

ALL_TESTS = [
    test_1_initialization,
    test_2_first_playable_cards,
    test_3_full_trick_flow,
    test_4_follow_suit_rule,
    test_5_undo_last_card,
    test_6_dd_engine,
    test_7_mcts_engine,
    test_8_dd_alphamu_llm_midgame,
    test_9_dd_alphamu_llm_endgame_alpha_mu,
    test_10_perfect_dd_engine,
    test_11_engine_consistency,
    test_12_complete_game_result,
    test_13_belief_tracker_reset,
    test_14_doubled_contract,
    test_15_dd_alphamu_llm_structure,
]


def main():
    print("\n" + "=" * 60)
    print("PlayService 集成测试：从叫牌到出牌全流程")
    print("=" * 60 + "\n")

    passed = 0
    failed = 0
    skipped = 0

    for test in ALL_TESTS:
        try:
            test()
            passed += 1
        except AssertionError as e:
            failed += 1
            print(f"  ✗ 失败: {e}\n")
        except Exception as e:
            failed += 1
            print(f"  ✗ 异常: {type(e).__name__}: {e}\n")
            import traceback
            traceback.print_exc()

    print("\n" + "=" * 60)
    print(f"测试结果: {passed} 通过, {failed} 失败, {skipped} 跳过")
    print("=" * 60)

    return 0 if failed == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
