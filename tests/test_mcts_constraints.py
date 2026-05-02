"""测试叫牌约束采样器的核心逻辑。

运行: python -X utf8 tests/test_mcts_constraints.py
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from bridge.mcts.constraints import BidConstraint, validate_sample, _compute_hcp, _count_distribution, _is_balanced
from bridge.mcts.sampler import DealSampler
from bridge.play_types import Card, PlayState, Contract


# ── 工具函数测试 ──
def test_hcp():
    cards = [Card(suit="♠", rank=r) for r in "AKQJ"]
    assert _compute_hcp(cards) == 10, f"AKQJ should be 10, got {_compute_hcp(cards)}"
    assert _compute_hcp([]) == 0
    print("  ✓ _compute_hcp")


def test_distribution():
    cards = [
        Card(suit="♠", rank="A"), Card(suit="♠", rank="K"),
        Card(suit="♥", rank="Q"), Card(suit="♥", rank="J"),
        Card(suit="♦", rank="9"), Card(suit="♦", rank="8"),
        Card(suit="♣", rank="7"), Card(suit="♣", rank="6"),
    ]
    dist = _count_distribution(cards)
    assert dist == {"♠": 2, "♥": 2, "♦": 2, "♣": 2}
    print("  ✓ _count_distribution")


def test_balanced():
    # 4333
    assert _is_balanced({"♠": 4, "♥": 3, "♦": 3, "♣": 3}) is True
    # 5332
    assert _is_balanced({"♠": 5, "♥": 3, "♦": 3, "♣": 2}) is True
    # 55
    assert _is_balanced({"♠": 5, "♥": 5, "♦": 2, "♣": 1}) is False
    # 单缺
    assert _is_balanced({"♠": 6, "♥": 3, "♦": 2, "♣": 2}) is False
    assert _is_balanced({"♠": 4, "♥": 4, "♦": 4, "♣": 1}) is False
    print("  ✓ _is_balanced")


# ── validate_sample 直接测试 ──
def test_validate_hcp_min():
    """点力下限：南家必须≥12点"""
    c = {"南": BidConstraint(position="南", min_hcp=12)}
    # 满足
    hands = {"南": [Card(suit="♠", rank=r) for r in "AKQJ"]  # 10HCP
             + [Card(suit="♥", rank="Q")]}  # +2 = 12
    hands.update({"西": [], "北": [], "东": []})
    assert validate_sample(hands, c) is True
    # 不满足
    hands_low = {"南": [Card(suit="♠", rank=r) for r in "AKQJ"]}  # 10HCP
    hands_low.update({"西": [], "北": [], "东": []})
    assert validate_sample(hands_low, c) is False
    print("  ✓ validate HCP min")


def test_validate_hcp_max():
    """点力上限：pass牌 ≤5点 non-pass不需要约束"""
    c = {"西": BidConstraint(position="西", max_hcp=5)}
    hands = {"西": [Card(suit="♠", rank="A"), Card(suit="♥", rank="2")]}  # 4HCP
    hands.update({"南": [], "北": [], "东": []})
    assert validate_sample(hands, c) is True

    hands_high = {"西": [Card(suit="♠", rank="A"), Card(suit="♥", rank="K")]}  # 7HCP
    hands_high.update({"南": [], "北": [], "东": []})
    assert validate_sample(hands_high, c) is False
    print("  ✓ validate HCP max")


def test_validate_suit_min():
    """花色最少张数：北家≥5张S"""
    c = {"北": BidConstraint(position="北", suit_min={"♠": 5})}
    hands = {"北": [Card(suit="♠", rank=r) for r in "AKQJ9"]}
    hands.update({"南": [], "西": [], "东": []})
    assert validate_sample(hands, c) is True

    hands_fail = {"北": [Card(suit="♠", rank=r) for r in "AKQ"]}
    hands_fail.update({"南": [], "西": [], "东": []})
    assert validate_sample(hands_fail, c) is False
    print("  ✓ validate suit_min")


def test_validate_balanced():
    """均型校验"""
    c = {"东": BidConstraint(position="东", balanced=True)}
    hands_balanced = {"东": [
        Card(suit="♠", rank=r) for r in "AKQ2"
    ] + [
        Card(suit="♥", rank=r) for r in "KJ3"
    ] + [
        Card(suit="♦", rank=r) for r in "QT4"
    ] + [
        Card(suit="♣", rank=r) for r in "987"
    ]}  # 4333
    hands_balanced.update({"南": [], "西": [], "北": []})
    assert validate_sample(hands_balanced, c) is True

    hands_unbal = {"东": [
        Card(suit="♠", rank=r) for r in "AKQJT9"
    ] + [
        Card(suit="♥", rank=r) for r in "KJ3"
    ] + [
        Card(suit="♦", rank=r) for r in "QT"
    ] + [
        Card(suit="♣", rank=r) for r in "98"
    ]}  # 6223 非均
    hands_unbal.update({"南": [], "西": [], "北": []})
    assert validate_sample(hands_unbal, c) is False
    print("  ✓ validate balanced")


def test_validate_multi_constraints():
    """多约束组合：南12-14均型5+S，西0-5点"""
    constraints = {
        "南": BidConstraint(position="南", min_hcp=12, max_hcp=14, balanced=True, suit_min={"♠": 5}),
        "西": BidConstraint(position="西", max_hcp=5),
    }
    # 正确：南12HCP, 5332, 西3HCP
    hands_ok = {
        "南": [Card(suit="♠", rank=r) for r in "AKQJ9"]  # S:5张, 10HCP
        + [Card(suit="♥", rank=r) for r in "QT2"]  # H:3, +2HCP = 12
        + [Card(suit="♦", rank=r) for r in "432"]
        + [Card(suit="♣", rank=r) for r in "32"],  # 5332, 均型
        "西": [Card(suit="♥", rank="K"), Card(suit="♥", rank="2")],  # 3HCP
        "北": [],
        "东": [],
    }
    assert validate_sample(hands_ok, constraints) is True

    # 南HCP不够（仅10点）
    hands_low = dict(hands_ok)
    hands_low["南"] = [
        Card(suit="♠", rank=r) for r in "KQJ98"  # S:5, 5HCP
    ] + [
        Card(suit="♥", rank=r) for r in "542"
    ] + [
        Card(suit="♦", rank=r) for r in "432"
    ] + [
        Card(suit="♣", rank=r) for r in "32"
    ]  # 5332, 均型, 10HCP
    assert validate_sample(hands_low, constraints) is False
    print("  ✓ validate multi-constraints")


# ── DealSampler 约束集成测试 ──
def make_test_state():
    """构建一个完整的 PlayState 用于测试采样器。

    南家 S:AKQJ H:KQJ D:987 C:654, 定约1♠ 庄家南, 北=明手。
    其余三家手牌填充剩余牌张（采样器会重分配未知位置）。
    """
    # 南家手牌
    south = [Card(suit="♠", rank=r) for r in "AKQJ"] \
        + [Card(suit="♥", rank=r) for r in "KQJ"] \
        + [Card(suit="♦", rank=r) for r in "987"] \
        + [Card(suit="♣", rank=r) for r in "654"]

    # 剩余牌张分配到西/北/东（采样器会重分配未知位置）
    all_cards_set = {Card(suit=s, rank=r) for s in "♠♥♦♣" for r in "AKQJT98765432"}
    south_set = set(south)
    remaining = list(all_cards_set - south_set)

    hands = {
        "南": south,
        "西": remaining[0:13],
        "北": remaining[13:26],
        "东": remaining[26:39],
    }

    contract = Contract.from_str("1S", "南")
    state = PlayState(
        contract=contract,
        hands={pos: [Card(suit=c.suit, rank=c.rank) for c in cards] for pos, cards in hands.items()},
        bidding_sequence="(南)1S-(西)pass-(北)2S-",
    )
    state.hands = {pos: [Card(suit=c.suit, rank=c.rank) for c in cards] for pos, cards in hands.items()}
    return state


def test_sampler_no_constraints():
    """采样器无约束时正常采样"""
    sampler = DealSampler()
    state = make_test_state()
    result = sampler.sample(state, "南")
    assert "南" in result
    assert "西" in result
    assert "北" in result
    assert "东" in result
    # 南的手牌应和原始一致
    south_cards = {str(c) for c in result["南"]}
    assert "♠A" in south_cards and "♠K" in south_cards
    # 每家13张
    for pos in result:
        assert len(result[pos]) == 13, f"{pos} has {len(result[pos])} cards"
    print("  ✓ sampler without constraints")


def test_sampler_with_constraints():
    """采样器带约束时应过滤不合规采样"""
    sampler = DealSampler()
    state = make_test_state()

    # 约束：西家 ≤5HCP（pass过的牌手）
    constraints = {
        "西": BidConstraint(position="西", max_hcp=5),
    }
    sampler.set_constraints(constraints)

    # 采样100次，全部验证
    for i in range(100):
        result = sampler.sample(state, "南")
        assert validate_sample(result, constraints), f"Sample {i} failed constraints"
        # 南家手牌不变
        south_cards = {str(c) for c in result["南"]}
        assert "♠A" in south_cards
    print("  ✓ sampler with constraints (100 samples all valid)")


def test_sampler_impossible_constraints():
    """不可能满足的约束 → 回退到无约束采样（不应卡死）"""
    sampler = DealSampler()
    state = make_test_state()

    # 不可能：西家≥50HCP
    constraints = {
        "西": BidConstraint(position="西", min_hcp=50),
    }
    sampler.set_constraints(constraints)

    result = sampler.sample(state, "南")
    assert "西" in result
    assert len(result["西"]) == 13
    # 回退采样可能不满足约束（这是预期行为）
    print("  ✓ sampler impossible constraints fallback")


def test_sampler_set_constraints_clears():
    """set_constraints({}) 清空约束"""
    sampler = DealSampler()
    sampler.set_constraints({"西": BidConstraint(position="西", max_hcp=5)})
    assert len(sampler.constraints) == 1
    sampler.set_constraints({})
    assert len(sampler.constraints) == 0
    print("  ✓ set_constraints clear")


# ── LLM 约束提取测试（需要 API） ──
def test_llm_constraint_extraction():
    """测试 LLM 从叫牌含义中提取约束。需要 DEEPSEEK_API_KEY。"""
    from llm.deepseek_client import DeepSeekClient
    from bridge.play_service import PlayService

    client = DeepSeekClient()
    if not client.is_configured():
        print("  ⚠ 跳过 LLM 测试：未配置 API Key")
        return

    svc = PlayService(client)
    svc.bid_history = ""
    svc.bid_constraints = None
    # 一个简单的叫牌：南开叫1S(12+,5+S)，西pass(不够开叫)，北加叫2S(6-10,3+S)
    svc.bid_history = """(南)1S: 12-21点，5张以上S，非均型
(西)pass: 牌力不足，没有合适叫品
(北)2S: 6-10点，3张以上S支持
(东)pass: 牌力不足，没有合适叫品"""

    try:
        constraints = svc._get_bid_constraints()
    except Exception as e:
        print(f"  ⚠ LLM调用失败: {e}")
        return

    print(f"  提取到 {len(constraints)} 条约束:")
    for pos, c in constraints.items():
        parts = []
        if c.min_hcp is not None:
            parts.append(f"min_hcp={c.min_hcp}")
        if c.max_hcp is not None:
            parts.append(f"max_hcp={c.max_hcp}")
        if c.balanced is not None:
            parts.append(f"balanced={c.balanced}")
        if c.suit_min:
            for suit, n in c.suit_min.items():
                parts.append(f"{suit}≥{n}")
        print(f"    {pos}: {', '.join(parts) if parts else '(无约束)'}")


if __name__ == "__main__":
    print("=== 叫牌约束采样器测试 ===\n")

    print("[工具函数]")
    test_hcp()
    test_distribution()
    test_balanced()

    print("\n[validate_sample]")
    test_validate_hcp_min()
    test_validate_hcp_max()
    test_validate_suit_min()
    test_validate_balanced()
    test_validate_multi_constraints()

    print("\n[DealSampler 集成]")
    test_sampler_no_constraints()
    test_sampler_with_constraints()
    test_sampler_impossible_constraints()
    test_sampler_set_constraints_clears()

    print("\n[LLM 约束提取]")
    test_llm_constraint_extraction()

    print("\n全部测试通过 ✓")
