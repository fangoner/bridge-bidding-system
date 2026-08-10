"""模拟防守方残局出牌场景，诊断 αμ 返回 0 分的问题。"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from bridge.play_types import Card, Contract, PlayState, PlayPhase, PlayerRole
from bridge.mcts.alpha_mu import AlphaMuSearch, ENDPLAY_AVAILABLE


def build_defender_endgame():
    """防守方（东）残局出牌：4 张牌，庄家是南。"""
    contract = Contract(level=3, suit="NT", declarer="南")
    state = PlayState(
        contract=contract,
        hands={
            "南": [Card("♠", "A"), Card("♥", "K"), Card("♦", "A"), Card("♣", "2")],
            "西": [Card("♠", "Q"), Card("♥", "T"), Card("♦", "K"), Card("♣", "3")],
            "北": [Card("♠", "K"), Card("♥", "J"), Card("♦", "Q"), Card("♣", "4")],
            "东": [Card("♠", "2"), Card("♥", "8"), Card("♦", "3"), Card("♣", "5")],
        },
        player_roles={"南": PlayerRole.AI.value, "西": PlayerRole.AI.value,
                      "北": PlayerRole.AI.value, "东": PlayerRole.AI.value},
        declarer_tricks=5,
        defender_tricks=4,
        phase=PlayPhase.PLAYING,
    )
    state.current_player = "东"  # 防守方出牌
    state.lead_player = "东"
    return state


def build_declarer_endgame_with_trick():
    """庄家方残局出牌，当前墩已有牌。"""
    contract = Contract(level=3, suit="NT", declarer="南")
    state = PlayState(
        contract=contract,
        hands={
            "南": [Card("♠", "A"), Card("♥", "8"), Card("♥", "6"), Card("♣", "4"), Card("♣", "3")],
            "西": [Card("♠", "Q"), Card("♥", "T"), Card("♥", "9"), Card("♣", "7"), Card("♣", "6")],
            "北": [Card("♠", "K"), Card("♥", "K"), Card("♥", "5"), Card("♣", "T"), Card("♣", "8")],
            "东": [Card("♠", "2"), Card("♥", "J"), Card("♥", "7"), Card("♣", "5"), Card("♣", "2")],
        },
        player_roles={"南": PlayerRole.AI.value, "西": PlayerRole.AI.value,
                      "北": PlayerRole.AI.value, "东": PlayerRole.AI.value},
        declarer_tricks=5,
        defender_tricks=3,
        phase=PlayPhase.PLAYING,
    )
    state.current_player = "南"
    state.lead_player = "南"
    return state


if __name__ == "__main__":
    if not ENDPLAY_AVAILABLE:
        print("endplay 未安装，跳过")
        sys.exit(0)

    print("=" * 60)
    print("场景 1: 防守方（东）残局出牌")
    print("=" * 60)
    state = build_defender_endgame()
    print(f"  当前出牌: {state.current_player}, 庄家: {state.contract.declarer}")
    print(f"  已赢墩: 庄家 {state.declarer_tricks}, 防守 {state.defender_tricks}")
    print(f"  东家手牌: {[str(c) for c in state.hands['东']]}")

    search = AlphaMuSearch(num_worlds=8, M=2, time_limit=10.0)
    result = search.search(state)
    print(f"  推荐: {result.get('card')}")
    print(f"  推理: {result.get('reasoning', '')[:200]}")
    print()

    print("=" * 60)
    print("场景 2: 庄家方（南）残局出牌，5 张牌")
    print("=" * 60)
    state2 = build_declarer_endgame_with_trick()
    print(f"  当前出牌: {state2.current_player}, 庄家: {state2.contract.declarer}")
    print(f"  已赢墩: 庄家 {state2.declarer_tricks}, 防守 {state2.defender_tricks}")
    print(f"  南家手牌: {[str(c) for c in state2.hands['南']]}")

    search2 = AlphaMuSearch(num_worlds=8, M=2, time_limit=10.0)
    result2 = search2.search(state2)
    print(f"  推荐: {result2.get('card')}")
    print(f"  推理: {result2.get('reasoning', '')[:200]}")
