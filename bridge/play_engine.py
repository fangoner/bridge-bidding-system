from typing import Dict, List, Optional, Tuple
from bridge.play_types import (
    Card, Contract, Trick, PlayState, PlayPhase, PlayerRole,
    parse_hands_dict, POSITION_ORDER, PARTNERS
)


class PlayEngine:
    
    def __init__(self):
        self.state: Optional[PlayState] = None
    
    def initialize(
        self,
        hands: Dict[str, dict],
        contract: Contract,
        player_roles: Dict[str, str] = None,
        bidding_sequence: str = "未提供",
        vulnerability: str = "NV"
    ) -> PlayState:
        parsed_hands = parse_hands_dict(hands)
        
        if player_roles is None:
            player_roles = {pos: PlayerRole.AI.value for pos in POSITION_ORDER}
        
        self.state = PlayState(
            contract=contract,
            hands=parsed_hands,
            player_roles=player_roles,
            bidding_sequence=bidding_sequence,
            vulnerability=vulnerability
        )
        
        return self.state
    
    def get_state(self) -> Optional[PlayState]:
        return self.state
    
    def can_play_card(self, position: str, card: Card) -> Tuple[bool, str]:
        if not self.state:
            return False, "游戏未初始化"
        
        if self.state.phase == PlayPhase.COMPLETE:
            return False, "打牌已结束"
        
        if position != self.state.current_player:
            return False, f"当前不是{position}出牌"

        is_human = self.state.player_roles.get(position) == PlayerRole.HUMAN.value
        is_hand_unknown = not self.state.hands.get(position)

        if is_human and is_hand_unknown:
            return True, "可以出牌"

        playable = self.state.get_playable_cards(position)
        if card not in playable:
            return False, f"不能出这张牌，必须跟{self.state.current_trick.get_lead_suit()}" if self.state.current_trick.get_lead_suit() else "不能出这张牌"
        
        return True, "可以出牌"
    
    def play_card(self, position: str, card: Card, is_ai: bool = False, reason: str = None, risk: str = None) -> Tuple[bool, str]:
        can_play, message = self.can_play_card(position, card)
        if not can_play:
            return False, message
        
        success = self.state.play_card(position, card, is_ai, reason, risk)
        if success:
            return True, f"{position}出{card}"
        return False, "出牌失败"
    
    def get_playable_cards(self, position: str = None) -> List[Card]:
        if not self.state:
            return []
        
        pos = position or self.state.current_player
        return self.state.get_playable_cards(pos)
    
    def get_current_player(self) -> Optional[str]:
        if not self.state:
            return None
        return self.state.current_player
    
    def is_human_turn(self) -> bool:
        if not self.state:
            return False
        return self.state.is_human_turn()
    
    def update_player_roles(self, player_roles: Dict[str, str]) -> bool:
        if not self.state:
            return False
        self.state.player_roles = player_roles
        return True
    
    def get_trick_count(self) -> Tuple[int, int]:
        if not self.state:
            return 0, 0
        return self.state.declarer_tricks, self.state.defender_tricks
    
    def is_complete(self) -> bool:
        if not self.state:
            return False
        return self.state.phase == PlayPhase.COMPLETE
    
    def get_result(self) -> Optional[dict]:
        if not self.state or not self.is_complete():
            return None
        
        needed = self.state.contract.tricks_needed
        made = self.state.declarer_tricks
        
        if made >= needed:
            overtricks = made - needed
            return {
                "result": "made",
                "contract": str(self.state.contract),
                "tricks_made": made,
                "overtricks": overtricks,
                "message": f"定约完成！{self.state.contract}做成{overtricks}超" if overtricks > 0 else f"定约完成！{self.state.contract}刚好做成"
            }
        else:
            undertricks = needed - made
            return {
                "result": "down",
                "contract": str(self.state.contract),
                "tricks_made": made,
                "undertricks": undertricks,
                "message": f"定约失败，宕{undertricks}"
            }
    
    def get_state_dict(self) -> Optional[dict]:
        if not self.state:
            return None
        return self.state.to_dict()
    
    def set_hand(self, position: str, hand: Dict[str, str]) -> Tuple[bool, str]:
        if not self.state:
            return False, "游戏未初始化"
        success = self.state.set_hand(position, hand)
        if not success:
            return False, "设置手牌失败"
        return True, "设置成功"
    
    def undo_last_card(self) -> Tuple[bool, str]:
        """撤销最近一次出牌"""
        if not self.state:
            return False, "游戏未初始化"
        
        if not self.state.current_trick.cards and not self.state.tricks:
            return False, "没有可撤销的出牌"
        
        success = self.state.undo_last_card()
        if success:
            return True, "撤销成功"
        return False, "撤销失败"
    
    def get_visible_hands(self, for_position: str = None) -> Dict[str, List[Card]]:
        if not self.state:
            return {}
        
        if not for_position:
            return {pos: cards for pos, cards in self.state.hands.items()}
        
        visible = {}
        for pos, cards in self.state.hands.items():
            if pos == for_position:
                visible[pos] = cards
            elif pos == self.state.dummy and self.state.phase != PlayPhase.LEAD:
                visible[pos] = cards
        
        return visible
