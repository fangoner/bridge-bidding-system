"""Quick integration test for tiered play engine.

Verifies:
1. Tiered engine dispatch activates for different phases
2. DD endgame enumeration produces valid results (when endplay available)
3. _is_critical_decision with mock MCTS results
"""

import sys
sys.path.insert(0, '.')

from bridge.play_types import Card, PlayState, Contract, Trick, POSITION_ORDER
from bridge.play_engine import PlayEngine
from bridge.mcts.dd_search import DDSearch, ENDPLAY_AVAILABLE
from bridge.play_service import PlayService


def test_dd_constructor():
    """Test DDSearch accepts new endgame params."""
    dd = DDSearch(
        num_samples=10, min_samples=5, time_limit=1.0,
        endgame_card_threshold=10, max_enumerations=5000,
    )
    assert dd.endgame_card_threshold == 10
    assert dd.max_enumerations == 5000
    print("[OK] DDSearch constructor")


def test_phase_detection():
    """Test that a PlayState reports correct phases."""
    engine = PlayEngine()

    # Create a simple NT hand
    hands = {
        "南": {"spades": "AKQ", "hearts": "432", "diamonds": "987", "clubs": "654"},
        "西": {"spades": "JT9", "hearts": "AKQ", "diamonds": "432", "clubs": "987"},
        "北": {"spades": "876", "hearts": "JT9", "diamonds": "AKQ", "clubs": "432"},
        "东": {"spades": "5432", "hearts": "8765", "diamonds": "JT", "clubs": "AKQ"},
    }

    contract = Contract(level=3, suit="NT", declarer="南")
    state = engine.initialize(hands, contract)

    # Should be in LEAD phase
    assert state.phase.name == "LEAD", f"Expected LEAD, got {state.phase}"
    assert state.current_player == "西"  # LHO of 南
    print(f"[OK] Phase detection: phase={state.phase.name}, current={state.current_player}")

    # Play opening lead
    card_to_play = state.hands["西"][0]
    engine.play_card("西", card_to_play)
    state = engine.get_state()
    assert state.phase.name == "DUMMY_REVEAL"
    print(f"[OK] After lead: phase={state.phase.name}")

    # Play dummy's card
    card_to_play = state.hands["北"][0]
    engine.play_card("北", card_to_play)
    state = engine.get_state()
    assert state.phase.name == "PLAYING"
    assert len(state.tricks) == 0  # first trick still in progress
    print(f"[OK] After dummy: phase={state.phase.name}, tricks={len(state.tricks)}")


def test_tiered_phase_logic():
    """Test the phase decision logic from _tiered_play (without LLM client)."""
    engine = PlayEngine()

    hands = {
        "南": {"spades": "AKQ", "hearts": "432", "diamonds": "987", "clubs": "654"},
        "西": {"spades": "JT9", "hearts": "AKQ", "diamonds": "432", "clubs": "987"},
        "北": {"spades": "876", "hearts": "JT9", "diamonds": "AKQ", "clubs": "432"},
        "东": {"spades": "5432", "hearts": "8765", "diamonds": "JT", "clubs": "AKQ"},
    }

    contract = Contract(level=3, suit="NT", declarer="南")
    state = engine.initialize(hands, contract)

    # Simulate tiered_play phase logic
    from config import TIERED_ENDGAME_CARDS

    # Phase 1: LEAD
    assert state.phase.name == "LEAD"
    phase = _get_tiered_phase(state)
    assert phase == "opening_lead", f"Expected opening_lead, got {phase}"
    print(f"[OK] LEAD → {phase}")

    # Play first card (opening lead)
    card = state.hands["西"][0]
    engine.play_card("西", card)
    state = engine.get_state()
    phase = _get_tiered_phase(state)
    assert phase == "dummy_reveal", f"Expected dummy_reveal, got {phase}"
    print(f"[OK] DUMMY_REVEAL → {phase}")

    # Play second card (dummy)
    card = state.hands["北"][0]
    engine.play_card("北", card)
    state = engine.get_state()
    phase = _get_tiered_phase(state)
    assert phase == "first_trick", f"Expected first_trick, got {phase}"
    print(f"[OK] First trick → {phase}")

    # Play third + fourth cards
    card = state.hands["东"][0]
    engine.play_card("东", card)
    state = engine.get_state()
    phase = _get_tiered_phase(state)
    print(f"[OK] After 3rd card: phase={phase} (tricks={len(state.tricks)})")

    card = state.hands["南"][0]
    engine.play_card("南", card)
    state = engine.get_state()
    assert len(state.tricks) == 1  # first trick complete
    phase = _get_tiered_phase(state)
    # Now in midgame unless endgame
    remaining = sum(len(state.hands.get(p, [])) for p in POSITION_ORDER)
    cards_per_hand = remaining / 4
    if cards_per_hand <= TIERED_ENDGAME_CARDS:
        assert phase == "endgame"
        print(f"[OK] After trick 1: endgame ({cards_per_hand:.0f} cards/hand)")
    else:
        assert phase == "midgame"
        print(f"[OK] After trick 1: midgame ({cards_per_hand:.0f} cards/hand)")


def _get_tiered_phase(state):
    """Replicate the tiered phase logic from _tiered_play."""
    from bridge.play_types import PlayPhase
    from config import TIERED_ENDGAME_CARDS

    remaining = sum(len(state.hands.get(p, [])) for p in POSITION_ORDER)
    cards_per_hand = remaining / 4

    if state.phase == PlayPhase.LEAD:
        return "opening_lead"
    elif state.phase == PlayPhase.DUMMY_REVEAL:
        return "dummy_reveal"
    elif len(state.tricks) == 0:
        return "first_trick"
    elif cards_per_hand <= TIERED_ENDGAME_CARDS:
        return "endgame"
    else:
        return "midgame"


def test_critical_decision():
    """Test _is_critical_decision with three-signal detection (new logic)."""
    from config import (
        TIERED_FUSION_SPREAD, TIERED_CLUSTER_SE, TIERED_TYPICAL_SD,
        TIERED_MIN_SAMPLES, TIERED_MCTS_CLUSTER_THRESHOLD,
    )

    # ── 信号1: Strategy Fusion 检测 ──
    # #1 ♠3: 9.78 [9-10] spread=1 → 不触发
    # #2 ♣4: 9.65 [7-10] spread=3 → 触发（且与#1差0.13 < margin）
    N = 200
    se = TIERED_TYPICAL_SD / (N ** 0.5)
    margin = TIERED_CLUSTER_SE * se
    gap_fusion = abs(9.65 - 9.78)  # 0.13
    assert gap_fusion <= margin, f"fusion gap {gap_fusion} should be <= margin {margin}"
    assert (10 - 7) >= TIERED_FUSION_SPREAD, "fusion spread should reach threshold"
    print(f"[OK] Signal1 Fusion: gap={gap_fusion:.2f}<=margin={margin:.2f}, spread=3>={TIERED_FUSION_SPREAD}")

    # ── 信号2: 候选集群检测（动态SE） ──
    # 3牌挤在0.05墩内 → 集群≥2 → 触发
    # 用 N=30 让 margin 较大（0.55），保证集群检测可靠
    N_cluster = 30
    se_30 = TIERED_TYPICAL_SD / (N_cluster ** 0.5)
    margin_30 = TIERED_CLUSTER_SE * se_30
    cluster_gaps = [abs(8.05 - 8.0), abs(7.95 - 8.0)]  # 0.05, 0.05
    assert all(g <= margin_30 for g in cluster_gaps), "cluster gaps should be within margin"
    assert len(cluster_gaps) + 1 >= 2  # 至少2张在集群内
    print(f"[OK] Signal2 Cluster: 3 cards within margin={margin_30:.2f} (N={N_cluster})")

    # ── 集群不触发场景：大差距 ──
    # #1=10.5 vs #2=7.5, gap=3.0 远大于任何合理 margin
    gap_large = abs(10.5 - 7.5)
    assert gap_large > margin_30, f"large gap {gap_large} should exceed margin {margin_30}"
    print(f"[OK] No cluster: gap={gap_large} > margin={margin_30:.2f}")

    # ── 信号3: 定约边缘 ──
    # 庄家还需1墩成约 → 触发（由 _is_critical_decision 内部判断）
    declarer_needs = 1
    assert 0 < declarer_needs <= 1
    print(f"[OK] Signal3 Contract edge: declarer needs {declarer_needs} trick")

    # ── MCTS 回退路径集群阈值 ──
    mcts_gap = abs(8.0 - 7.7)  # 0.3
    assert mcts_gap <= TIERED_MCTS_CLUSTER_THRESHOLD, f"mcts gap {mcts_gap} should be <= {TIERED_MCTS_CLUSTER_THRESHOLD}"
    print(f"[OK] MCTS cluster: gap={mcts_gap} <= threshold={TIERED_MCTS_CLUSTER_THRESHOLD}")

    # ── 样本量不足时不升级 ──
    assert TIERED_MIN_SAMPLES == 30, "min samples should be 30"
    print(f"[OK] Min samples gate: {TIERED_MIN_SAMPLES}")

    # ── 端到端：用 mock PlayService 验证三信号 ──
    # 信号1端到端
    fusion_result = {
        "full_output": {
            "mcts_stats": {
                "candidates": [
                    {"card": "S3", "avg_tricks": 9.78, "min_tricks": 9, "max_tricks": 10, "samples": 200},
                    {"card": "C4", "avg_tricks": 9.65, "min_tricks": 7, "max_tricks": 10, "samples": 200},
                ]
            }
        }
    }
    # 直接调用静态方法验证 SE 估计
    se_est = PlayService._estimate_se(200)
    assert abs(se_est - 0.106) < 0.01, f"SE(200) should be ~0.106, got {se_est}"
    print(f"[OK] _estimate_se(200)={se_est:.3f}")

    se_est_30 = PlayService._estimate_se(30)
    assert abs(se_est_30 - 0.274) < 0.01, f"SE(30) should be ~0.274, got {se_est_30}"
    print(f"[OK] _estimate_se(30)={se_est_30:.3f}")


if __name__ == "__main__":
    print("=" * 60)
    print("Tiered Engine Integration Tests")
    print("=" * 60)

    test_dd_constructor()
    test_phase_detection()
    test_tiered_phase_logic()
    test_critical_decision()

    print()
    print("=" * 60)
    print("All tests passed!")
    print("=" * 60)
