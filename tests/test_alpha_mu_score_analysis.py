"""验证 αμ 在不同场景下的行为。

场景1: 必成定约（所有 worlds 都成约）→ 预期所有候选 score=1.0，无法区分
场景2: 必败定约（所有 worlds 都不成约）→ 预期所有候选 score=0.0，无法区分
场景3: 边缘定约（部分 worlds 成约）→ 预期不同候选 score 不同，αμ 有意义
"""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from bridge.mcts.alpha_mu import AlphaMuSearch, ENDPLAY_AVAILABLE
from bridge.play_types import Card, PlayState, Contract, PlayPhase, PlayerRole


def build_marginal_endgame():
    """边缘定约场景：3NT 需要 9 墩，庄家已赢 7 墩，还需 2 墩，剩余 3 墩。

    南家手牌：♠A ♠K ♥Q（3张）
    西家手牌：♠J ♥K ♥J（3张）
    北家手牌：♠2 ♥A ♦2（3张）
    东家手牌：♠3 ♥T ♦3（3张）

    南家出 ♠A 后，北家必须跟 ♠2，东家 ♠3，西家 ♠J。
    第二墩：北家出 ♥A，东家 ♥T，南家 ♥Q（赢），西家 ♥K。
    但实际取决于分布——这里构造的是已知分布，αμ 应该能算出。
    """
    contract = Contract(level=3, suit="NT", declarer="南")
    state = PlayState(
        contract=contract,
        hands={
            "南": [Card("♠", "A"), Card("♠", "K"), Card("♥", "Q")],
            "西": [Card("♠", "J"), Card("♥", "K"), Card("♥", "J")],
            "北": [Card("♠", "2"), Card("♥", "A"), Card("♦", "2")],
            "东": [Card("♠", "3"), Card("♥", "T"), Card("♦", "3")],
        },
        player_roles={"南": PlayerRole.AI.value, "西": PlayerRole.AI.value,
                      "北": PlayerRole.AI.value, "东": PlayerRole.AI.value},
        declarer_tricks=7,
        defender_tricks=3,
        phase=PlayPhase.PLAYING,
    )
    state.current_player = "南"
    state.lead_player = "南"
    return state


def build_made_endgame():
    """必成场景：3NT 需要 9 墩，庄家已赢 8 墩，剩余 2 墩都是庄家的 A。"""
    contract = Contract(level=3, suit="NT", declarer="南")
    state = PlayState(
        contract=contract,
        hands={
            "南": [Card("♠", "A"), Card("♠", "K")],
            "西": [Card("♠", "Q"), Card("♠", "2")],
            "北": [Card("♠", "J"), Card("♠", "3")],
            "东": [Card("♠", "T"), Card("♠", "4")],
        },
        player_roles={"南": PlayerRole.AI.value, "西": PlayerRole.AI.value,
                      "北": PlayerRole.AI.value, "东": PlayerRole.AI.value},
        declarer_tricks=8,
        defender_tricks=3,
        phase=PlayPhase.PLAYING,
    )
    state.current_player = "南"
    state.lead_player = "南"
    return state


def build_defeated_endgame():
    """必败场景：3NT 需要 9 墩，庄家已赢 5 墩，剩余 4 墩防守方全赢。"""
    contract = Contract(level=3, suit="NT", declarer="南")
    state = PlayState(
        contract=contract,
        hands={
            "南": [Card("♠", "2"), Card("♠", "3"), Card("♥", "2"), Card("♥", "3")],
            "西": [Card("♠", "A"), Card("♠", "K"), Card("♥", "A"), Card("♥", "K")],
            "北": [Card("♠", "4"), Card("♠", "5"), Card("♥", "4"), Card("♥", "5")],
            "东": [Card("♠", "Q"), Card("♠", "J"), Card("♥", "Q"), Card("♥", "J")],
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


def run_scenario(name, state):
    print(f"\n{'='*60}")
    print(f"场景: {name}")
    print(f"{'='*60}")
    print(f"定约: {state.contract}, 需 {state.contract.tricks_needed} 墩")
    print(f"已赢: 庄家 {state.declarer_tricks}, 防守 {state.defender_tricks}")
    print(f"南家手牌: {[str(c) for c in state.hands['南']]}")
    print(f"还需赢墩: {state.contract.tricks_needed - state.declarer_tricks}")
    print(f"剩余墩数: {13 - state.declarer_tricks - state.defender_tricks}")

    if not ENDPLAY_AVAILABLE:
        print("  ⚠ endplay 未安装，跳过")
        return

    search = AlphaMuSearch(num_worlds=8, max_depth=3, time_limit=15.0)
    result = search.search(state)

    print(f"\nαμ 推荐: {result.get('card')}")
    print(f"推理: {result.get('reasoning')}")

    stats = result.get("full_output", {}).get("mcts_stats", {})
    candidates = stats.get("candidates", [])
    print(f"\n候选牌得分对比:")
    for c in candidates:
        rate = c.get("success_rate", 0)
        won = c.get("success_count", 0)
        total = c.get("total_useful", 0)
        w = c.get("worst", 0)
        print(f"  {c['card']}: rate={rate:.1%} ({won}/{total}), worst={w}, front={c['front_size']}, vec={c['best_vector']}")

    # 分析
    rates = [c.get("success_rate", 0) for c in candidates]
    worsts = [c.get("worst", 0) for c in candidates]
    if len(set(rates)) == 1 and len(set(worsts)) == 1:
        print(f"\n⚠ 所有候选 rate({rates[0]:.1%}) 和 worst({worsts[0]}) 相同，αμ 用 rank_bonus 兜底")
    else:
        print(f"\n✓ 候选 rate/worst 有差异，αμ 能区分优劣")


if __name__ == "__main__":
    run_scenario("必成定约（庄家已赢8墩，剩余2墩都是A）", build_made_endgame())
    run_scenario("必败定约（庄家已赢5墩，剩余4墩防守全赢）", build_defeated_endgame())
    run_scenario("边缘定约（庄家已赢7墩，还需2墩，有猜断）", build_marginal_endgame())
