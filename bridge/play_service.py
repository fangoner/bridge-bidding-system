import re
from typing import Optional, Dict, List, Any

from bridge.play_types import Card, PlayState, PlayPhase, POSITION_ORDER, PARTNERS
from bridge.play_engine import PlayEngine
from llm.prompts import PLAY_COMMON_RULES, PLAY_COMMON_SITUATION, PLAY_DECLARER_PROMPT, PLAY_DEFENDER_PROMPT


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
        redoubled: bool = False,
        bidding_sequence: str = "未提供"
    ) -> PlayState:
        from bridge.play_types import Contract
        
        contract = Contract.from_str(contract_str, declarer)
        contract.doubled = doubled
        contract.redoubled = redoubled
        
        return self.engine.initialize(hands, contract, player_roles, bidding_sequence)
    
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
        
        if not playable_cards:
            return {"error": "没有可出的牌"}
        
        if len(playable_cards) == 1:
            card = playable_cards[0]
            return {
                "card": card.to_dict(),
                "reasoning": "只有一张牌可出",
                "full_output": {"推荐出牌": str(card), "核心逻辑": "唯一选择"},
                "prompt": ""
            }
        
        hands_info = self._format_hands_info(state)
        completed_tricks = self._format_completed_tricks(state)
        current_trick = self._format_current_trick(state)
        played_cards_info = self._format_played_cards_info(state)
        
        # 判断当前是庄家方还是防守方出牌
        declarer_partner = PARTNERS.get(state.contract.declarer, "")
        is_declarer_side = current_player in (state.contract.declarer, declarer_partner)
        side = "庄家方" if is_declarer_side else "防守方"
        
        # 计算剩余所需墩数
        declarer_remaining = max(0, state.contract.tricks_needed - state.declarer_tricks)
        defender_remaining = max(0, (14 - state.contract.tricks_needed) - state.defender_tricks)
        
        # 判断将牌是否已清完
        trump_cleared = self._check_trump_cleared(state)
        
        # 当前墩数
        trick_number = len(state.tricks) + 1
        
        # 当前出牌位置（第几家出牌）
        current_trick_count = len(state.current_trick.cards)
        play_position = current_trick_count + 1  # 第1家=领出，第2/3/4家=跟牌
        remaining_players = 4 - play_position  # 你之后还有几家未出牌
        
        # 公共局面信息
        common_situation = PLAY_COMMON_SITUATION.format(
            contract=str(state.contract),
            bidding_sequence=state.bidding_sequence,
            declarer=state.contract.declarer,
            dummy=state.dummy or "无",
            current_player=current_player,
            play_position=play_position,
            current_trick_count=current_trick_count,
            remaining_players=remaining_players,
            trick_number=trick_number,
            side=side,
            hands_info=hands_info,
            played_cards_info=played_cards_info,
            completed_tricks=completed_tricks,
            current_trick=current_trick,
            declarer_tricks=state.declarer_tricks,
            defender_tricks=state.defender_tricks,
            tricks_needed=state.contract.tricks_needed,
            declarer_remaining=declarer_remaining,
            defender_remaining=defender_remaining,
            trump_cleared=trump_cleared,
        )
        
        # 根据角色选择不同提示词模板
        if is_declarer_side:
            prompt = PLAY_DECLARER_PROMPT.format(
                common_rules=PLAY_COMMON_RULES,
                play_position=play_position,
                current_trick_count=current_trick_count,
                common_situation=common_situation,
            )
        else:
            prompt = PLAY_DEFENDER_PROMPT.format(
                common_rules=PLAY_COMMON_RULES,
                play_position=play_position,
                current_trick_count=current_trick_count,
                common_situation=common_situation,
            )
        
        try:
            result = self.llm_client.chat_play(prompt)
            
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
                result.get("推理过程") or
                result.get("核心逻辑") or 
                result.get("理由") or 
                result.get("reasoning") or 
                ""
            )
            analysis = (
                result.get("立场分析") or
                result.get("局面分析") or 
                result.get("analysis") or 
                ""
            )
            risk = (
                result.get("风险提示") or 
                result.get("risk") or 
                ""
            )
            follow_up = result.get("后续路线建议", "")
            
            return {
                "card": card.to_dict() if card else None,
                "reasoning": reasoning,
                "analysis": analysis,
                "risk": risk,
                "follow_up": follow_up,
                "full_output": result,
                "prompt": prompt
            }
            
        except Exception as e:
            card = self._select_best_card(playable_cards, state)
            return {
                "card": card.to_dict() if card else None,
                "reasoning": f"AI分析出错，自动选择: {str(e)}",
                "error": str(e),
                "prompt": prompt if 'prompt' in dir() else ""
            }
    
    def _format_hands_info(self, state: PlayState) -> str:
        lines = []
        
        card_str = " ".join(str(c) for c in state.hands.get(state.current_player, []))
        lines.append(f"**你的手牌({state.current_player})**: {card_str}")
        
        # 判断明手是否已摊牌（首攻阶段明手不可见）
        dummy_visible = state.phase != PlayPhase.LEAD
        
        declarer = state.contract.declarer
        dummy = state.dummy
        declarer_partner = PARTNERS.get(declarer, "")
        is_declarer_side = state.current_player in (declarer, declarer_partner)
        
        if is_declarer_side and dummy:
            # 庄家方视角：显示庄家和明手两家（庄家始终能看到明手，因为首攻者不是庄家方）
            if state.current_player != declarer:
                declarer_cards = " ".join(str(c) for c in state.hands.get(declarer, []))
                lines.append(f"**庄家({declarer})**: {declarer_cards}")
            if state.current_player != dummy:
                dummy_cards = " ".join(str(c) for c in state.hands.get(dummy, []))
                lines.append(f"**明手({dummy})**: {dummy_cards}")
        elif dummy and dummy_visible:
            # 防守方视角：首攻时看不到明手，首攻后可以看到明手
            dummy_cards = " ".join(str(c) for c in state.hands.get(dummy, []))
            lines.append(f"**明手({dummy})**: {dummy_cards}")
        
        return "\n".join(lines)
    
    def _format_completed_tricks(self, state: PlayState) -> str:
        if not state.tricks:
            return "无"
        
        lines = []
        for i, trick in enumerate(state.tricks, 1):
            cards_str = " ".join(f"({pos}){card}" for pos, card in trick.cards)
            winner = trick.winner()
            leader = trick.cards[0][0] if trick.cards else "?"
            lines.append(f"第{i}墩[领出:{leader}]: {cards_str} - 赢家: {winner}")
        
        return "\n".join(lines)
    
    def _format_current_trick(self, state: PlayState) -> str:
        if not state.current_trick.cards:
            return "尚未开始（你是本墩领出者）"
        
        leader = state.current_trick.cards[0][0]
        cards_str = " ".join(f"({pos}){card}" for pos, card in state.current_trick.cards)
        return f"[领出:{leader}] {cards_str}"
    
    def _format_played_cards_info(self, state: PlayState) -> str:
        """格式化已见牌张与花色轮次信息"""
        all_suits = ["♠", "♥", "♦", "♣"]
        all_ranks = ["A", "K", "Q", "J", "T", "9", "8", "7", "6", "5", "4", "3", "2"]
        
        # 收集所有已出过的牌
        played_cards = {suit: [] for suit in all_suits}
        for trick in state.tricks:
            for pos, card in trick.cards:
                if card.suit in played_cards:
                    played_cards[card.suit].append(card.rank)
        for pos, card in state.current_trick.cards:
            if card.suit in played_cards:
                played_cards[card.suit].append(card.rank)
        
        # 统计每门花色已出轮次
        suit_rounds = {}
        for suit in all_suits:
            suit_rounds[suit] = len(played_cards[suit]) // 1  # 每张牌代表出了一次
        
        lines = []
        for suit in all_suits:
            seen = played_cards[suit]
            unseen = [r for r in all_ranks if r not in seen]
            rounds = len(seen)
            if seen:
                lines.append(f"- {suit}: 已出{rounds}张，已见{'/'.join(seen)}，未见{'/'.join(unseen)}")
            else:
                lines.append(f"- {suit}: 未出过")
        
        return "\n".join(lines)
    
    def _check_trump_cleared(self, state: PlayState) -> str:
        """检查将牌是否已清完"""
        if state.contract.suit == "NT":
            return "不适用（无将定约）"
        
        trump = state.contract.suit
        # 统计已出的将牌数
        played_trumps = 0
        for trick in state.tricks:
            for pos, card in trick.cards:
                if card.suit == trump:
                    played_trumps += 1
        for pos, card in state.current_trick.cards:
            if card.suit == trump:
                played_trumps += 1
        
        # 检查防守方和庄家方手中是否还有将牌
        declarer = state.contract.declarer
        dummy = state.dummy
        defender1 = [p for p in POSITION_ORDER if p not in (declarer, dummy, PARTNERS.get(declarer, ""))][0] if len(POSITION_ORDER) > 3 else ""
        defender2 = PARTNERS.get(defender1, "")
        
        # 检查可见手牌中是否还有将牌
        remaining_trumps_in_defenders = 0
        for pos in [defender1, defender2]:
            if pos in state.hands:
                for card in state.hands[pos]:
                    if card.suit == trump:
                        remaining_trumps_in_defenders += 1
        
        # 庄家方手中的将牌
        remaining_trumps_in_declarer = 0
        for pos in [declarer, dummy]:
            if pos in state.hands:
                for card in state.hands[pos]:
                    if card.suit == trump:
                        remaining_trumps_in_declarer += 1
        
        if remaining_trumps_in_defenders == 0 and remaining_trumps_in_declarer == 0:
            return "是"
        elif remaining_trumps_in_defenders == 0:
            return "庄家方仍有将牌"
        else:
            return "否"
    
    def _parse_card_from_str(self, card_str: str, playable: List[Card]) -> Optional[Card]:
        if not card_str:
            return None
        
        card_str = card_str.strip().upper()
        
        for card in playable:
            if str(card).upper() == card_str:
                return card
            if f"{card.suit}{card.rank}" == card_str:
                return card
        
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
