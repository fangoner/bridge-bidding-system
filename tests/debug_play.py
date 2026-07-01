"""调试脚本：检查MCTS打牌为什么赢墩这么少"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from bridge.play_service import PlayService
from bridge.play_types import Card, PlayerRole, POSITION_ORDER


class MockLLMClient:
    def chat(self, *args, **kwargs):
        return ""
    def chat_json(self, *args, **kwargs):
        return {}


def main():
    service = PlayService(llm_client=MockLLMClient())
    service.mcts.time_limit = 0.5
    
    # 固定一副牌：4♠南打，强牌，每位置13张
    hands = {
        "南": {"spades": "AKQJ", "hearts": "AK", "diamonds": "T8543", "clubs": "95"},  # 4+2+5+2=13
        "西": {"spades": "652", "hearts": "975432", "diamonds": "J", "clubs": "AJ7"},  # 3+6+1+3=13
        "北": {"spades": "98743", "hearts": "J8", "diamonds": "AKQ", "clubs": "Q32"},  # 5+2+3+3=13
        "东": {"spades": "T", "hearts": "QT6", "diamonds": "9762", "clubs": "KT864"},  # 1+3+4+5=13
    }
    
    player_roles = {pos: PlayerRole.AI.value for pos in POSITION_ORDER}
    bid_history = "(南)1NT-(西)pass-(北)2♥-(东)pass-(南)2♠-(西)pass-(北)4♠"
    
    state = service.initialize(
        hands=hands,
        contract_str="4♠",
        declarer="南",
        player_roles=player_roles,
        bidding_sequence=bid_history,
        bid_history=bid_history,
    )
    
    print(f"初始状态：")
    print(f"  当前玩家: {state.current_player}")
    print(f"  定约: {state.contract}")
    print(f"  明手: {state.dummy}")
    print(f"  阶段: {state.phase}")
    print()
    
    # 打完整副牌（52张=13墩）
    while True:
        state = service.get_state()
        if state is None:
            break
        current_pos = state.current_player
        if current_pos is None:
            break
        # 判断是否打完：总赢墩=13
        total_tricks = state.declarer_tricks + state.defender_tricks
        if total_tricks >= 13:
            break
        
        playable = service.get_playable_cards(current_pos)
        if not playable:
            break
        
        trick_so_far = len(state.current_trick.cards) + sum(len(t.cards) for t in state.tricks)
        trick_num = trick_so_far // 4 + 1
        print(f"第{trick_num}墩，当前出牌: {current_pos}，可出牌数: {len(playable)}", end=" ")
        
        if len(playable) == 1:
            chosen = playable[0]
            print(f"唯一选择: {chosen}")
        else:
            result = service._mcts_play(state)
            card_dict = result.get("card")
            chosen = Card(suit=card_dict["suit"], rank=card_dict["rank"])
            print(f"MCTS选择: {chosen}")
        
        success, msg = service.play_card(current_pos, chosen, is_ai=True)
        if not success:
            print(f"  出牌错误: {msg}")
            break
        
        state = service.get_state()
        if len(state.current_trick.cards) == 0 and trick_num <= 13:
            print(f"  → 本墩结束，庄家赢墩: {state.declarer_tricks}, 防守赢墩: {state.defender_tricks}")
    
    final_state = service.get_state()
    print(f"\n🎴 最终结果：")
    print(f"   庄家赢墩: {final_state.declarer_tricks}/10")
    print(f"   防守赢墩: {final_state.defender_tricks}")
    print(f"   定约结果: {'✅ 做成' if final_state.declarer_tricks >= 10 else '❌ 宕'} {abs(final_state.declarer_tricks - 10)} 墩")


if __name__ == "__main__":
    main()
