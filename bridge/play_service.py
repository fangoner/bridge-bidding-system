from typing import Optional, Dict, List, Any

from bridge.play_types import Card, PlayState, PlayPhase, POSITION_ORDER, PARTNERS
from bridge.play_engine import PlayEngine
from llm.prompts import PLAY_SYSTEM_PROMPT


class PlayService:
    
    def __init__(self, llm_client):
        self.llm_client = llm_client
        self.engine = PlayEngine()
    
    def initialize(
        self,
        hands: Dict[str, dict],
        contract_str: str,
        declarer: str,
        player_roles: Dict[str, str] = None,
        doubled: bool = False,
        redoubled: bool = False
    ) -> PlayState:
        from bridge.play_types import Contract
        
        contract = Contract.from_str(contract_str, declarer)
        contract.doubled = doubled
        contract.redoubled = redoubled
        
        return self.engine.initialize(hands, contract, player_roles)
    
    def get_state(self) -> Optional[PlayState]:
        return self.engine.get_state()
    
    def get_state_dict(self) -> Optional[dict]:
        return self.engine.get_state_dict()
    
    def play_card(self, position: str, card: Card, is_ai: bool = False, reason: str = None, risk: str = None) -> tuple:
        return self.engine.play_card(position, card, is_ai, reason, risk)
    
    def get_playable_cards(self, position: str = None) -> List[Card]:
        return self.engine.get_playable_cards(position)
    
    def is_human_turn(self) -> bool:
        return self.engine.is_human_turn()
    
    def update_player_roles(self, player_roles: Dict[str, str]) -> bool:
        return self.engine.update_player_roles(player_roles)
    
    def get_current_player(self) -> Optional[str]:
        return self.engine.get_current_player()
    
    def is_complete(self) -> bool:
        return self.engine.is_complete()
    
    def get_result(self) -> Optional[dict]:
        return self.engine.get_result()
    
    async def get_ai_play(self, use_reasoning: bool = True) -> Dict[str, Any]:
        state = self.engine.get_state()
        if not state:
            return {"error": "游戏未初始化"}
        
        current_player = state.current_player
        playable_cards = self.engine.get_playable_cards()
        
        print(f"[DEBUG get_ai_play] current_player={current_player}, playable_cards={[str(c) for c in playable_cards]}")
        
        if not playable_cards:
            return {"error": "没有可出的牌"}
        
        if len(playable_cards) == 1:
            card = playable_cards[0]
            print(f"[DEBUG get_ai_play] 只有一张牌可出: {card}")
            return {
                "card": card.to_dict(),
                "reasoning": "只有一张牌可出",
                "full_output": {"推荐出牌": str(card), "理由": "唯一选择"}
            }
        
        hands_info = self._format_hands_info(state)
        completed_tricks = self._format_completed_tricks(state)
        current_trick = self._format_current_trick(state)
        
        prompt = PLAY_SYSTEM_PROMPT.format(
            contract=str(state.contract),
            trump=state.contract.suit,
            declarer=state.contract.declarer,
            dummy=state.dummy or "无",
            current_player=current_player,
            hands_info=hands_info,
            completed_tricks=completed_tricks,
            current_trick=current_trick,
            declarer_tricks=state.declarer_tricks,
            defender_tricks=state.defender_tricks,
            tricks_needed=state.contract.tricks_needed
        )
        
        try:
            result = self.llm_client.chat_play(prompt)
            
            print(f"[DEBUG get_ai_play] LLM result: {result}")
            
            recommended = (
                result.get("推荐出牌") or 
                result.get("recommended_card") or 
                result.get("recommended_play") or 
                ""
            )
            card = self._parse_card_from_str(recommended, playable_cards)
            
            if not card:
                card = self._select_best_card(playable_cards, state)
            
            reasoning = (
                result.get("理由") or 
                result.get("reasoning") or 
                result.get("risk_assessment") or 
                ""
            )
            analysis = (
                result.get("局面分析") or 
                result.get("analysis") or 
                result.get("current_trick_analysis") or 
                ""
            )
            risk = (
                result.get("风险提示") or 
                result.get("risk") or 
                result.get("risk_assessment") or 
                ""
            )
            
            return {
                "card": card.to_dict() if card else None,
                "reasoning": reasoning,
                "analysis": analysis,
                "risk": risk,
                "full_output": result
            }
            
        except Exception as e:
            card = self._select_best_card(playable_cards, state)
            return {
                "card": card.to_dict() if card else None,
                "reasoning": f"AI分析出错，自动选择: {str(e)}",
                "error": str(e)
            }
    
    def _format_hands_info(self, state: PlayState) -> str:
        lines = []
        
        card_str = " ".join(str(c) for c in state.hands.get(state.current_player, []))
        lines.append(f"**你的手牌**: {card_str}")
        
        if state.dummy:
            dummy_cards = " ".join(str(c) for c in state.hands.get(state.dummy, []))
            lines.append(f"**明手({state.dummy})**: {dummy_cards}")
        
        return "\n".join(lines)
    
    def _format_completed_tricks(self, state: PlayState) -> str:
        if not state.tricks:
            return "无"
        
        lines = []
        for i, trick in enumerate(state.tricks, 1):
            cards_str = " ".join(f"({pos}){card}" for pos, card in trick.cards)
            winner = trick.winner()
            lines.append(f"第{i}墩: {cards_str} - 赢家: {winner}")
        
        return "\n".join(lines)
    
    def _format_current_trick(self, state: PlayState) -> str:
        if not state.current_trick.cards:
            return "尚未开始"
        
        cards_str = " ".join(f"({pos}){card}" for pos, card in state.current_trick.cards)
        return cards_str
    
    def _parse_card_from_str(self, card_str: str, playable: List[Card]) -> Optional[Card]:
        if not card_str:
            return None
        
        card_str = card_str.strip().upper()
        
        for card in playable:
            if str(card).upper() == card_str:
                return card
            if f"{card.suit}{card.rank}" == card_str:
                return card
        
        import re
        matches = re.findall(r'([♠♥♦♣])([AKQJT98765432])', card_str)
        for suit, rank in matches:
            for card in playable:
                if card.suit == suit and card.rank == rank:
                    return card
        
        return None
    
    def _select_best_card(self, playable: List[Card], state: PlayState) -> Card:
        if len(playable) == 1:
            return playable[0]
        
        if state.current_trick.cards:
            lead_suit = state.current_trick.get_lead_suit()
            same_suit = [c for c in playable if c.suit == lead_suit]
            if same_suit:
                return min(same_suit, key=lambda c: c.rank_value)
        
        return min(playable, key=lambda c: (c.suit_order, c.rank_value))
