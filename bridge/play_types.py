from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple
from enum import Enum


class Suit(Enum):
    SPADES = "♠"
    HEARTS = "♥"
    DIAMONDS = "♦"
    CLUBS = "♣"
    NOTRUMP = "NT"


class PlayerRole(Enum):
    HUMAN = "human"
    AI = "ai"


class PlayPhase(Enum):
    LEAD = "lead"
    DUMMY_REVEAL = "dummy_reveal"
    PLAYING = "playing"
    COMPLETE = "complete"


SUIT_SYMBOLS = {
    "♠": "spades",
    "♥": "hearts", 
    "♦": "diamonds",
    "♣": "clubs",
    "S": "spades",
    "H": "hearts",
    "D": "diamonds",
    "C": "clubs",
}

SUIT_ORDER = ["♣", "♦", "♥", "♠"]
RANK_ORDER = ["2", "3", "4", "5", "6", "7", "8", "9", "T", "J", "Q", "K", "A"]

POSITION_ORDER = ["南", "西", "北", "东"]
PARTNERS = {"南": "北", "北": "南", "西": "东", "东": "西"}


@dataclass
class Card:
    suit: str
    rank: str
    
    def __str__(self):
        return f"{self.suit}{self.rank}"
    
    def __eq__(self, other):
        if isinstance(other, Card):
            return self.suit == other.suit and self.rank == other.rank
        return False
    
    def __hash__(self):
        return hash((self.suit, self.rank))
    
    @property
    def rank_value(self) -> int:
        try:
            return RANK_ORDER.index(self.rank)
        except ValueError:
            return -1
    
    @property
    def suit_order(self) -> int:
        try:
            return SUIT_ORDER.index(self.suit)
        except ValueError:
            return -1
    
    def to_dict(self) -> dict:
        return {"suit": self.suit, "rank": self.rank}
    
    @classmethod
    def from_str(cls, card_str: str) -> "Card":
        if len(card_str) >= 2:
            suit = card_str[0]
            rank = card_str[1].upper()
            if rank == "10":
                rank = "T"
            return cls(suit=suit, rank=rank)
        raise ValueError(f"Invalid card string: {card_str}")


@dataclass
class Contract:
    level: int
    suit: str
    declarer: str
    doubled: bool = False
    redoubled: bool = False
    
    @property
    def strain(self) -> str:
        return self.suit
    
    @property
    def tricks_needed(self) -> int:
        return self.level + 6
    
    def __str__(self):
        double_str = ""
        if self.redoubled:
            double_str = "XX"
        elif self.doubled:
            double_str = "X"
        return f"{self.level}{self.suit}{double_str} by {self.declarer}"
    
    def to_dict(self) -> dict:
        return {
            "level": self.level,
            "suit": self.suit,
            "declarer": self.declarer,
            "doubled": self.doubled,
            "redoubled": self.redoubled,
            "tricks_needed": self.tricks_needed,
        }
    
    @classmethod
    def from_str(cls, contract_str: str, declarer: str) -> "Contract":
        contract_str = contract_str.strip().upper()
        doubled = False
        redoubled = False
        
        if contract_str.endswith("XX"):
            redoubled = True
            contract_str = contract_str[:-2]
        elif contract_str.endswith("X"):
            doubled = True
            contract_str = contract_str[:-1]
        
        level = int(contract_str[0])
        suit = contract_str[1]
        if suit == "N":
            suit = "NT"
        
        return cls(level=level, suit=suit, declarer=declarer, doubled=doubled, redoubled=redoubled)


@dataclass
class Trick:
    cards: List[Tuple[str, Card]] = field(default_factory=list)
    leader: Optional[str] = None
    trump: Optional[str] = None
    is_ai_cards: List[bool] = field(default_factory=list)
    ai_reasons: List[Optional[str]] = field(default_factory=list)
    ai_risks: List[Optional[str]] = field(default_factory=list)
    
    def add_card(self, position: str, card: Card, is_ai: bool = False, reason: str = None, risk: str = None):
        if not self.cards:
            self.leader = position
        self.cards.append((position, card))
        self.is_ai_cards.append(is_ai)
        self.ai_reasons.append(reason)
        self.ai_risks.append(risk)
    
    def is_complete(self) -> bool:
        return len(self.cards) == 4
    
    def get_lead_suit(self) -> Optional[str]:
        if self.cards:
            return self.cards[0][1].suit
        return None
    
    def winner(self) -> Optional[str]:
        if not self.is_complete():
            return None
        
        lead_suit = self.get_lead_suit()
        winning_pos = None
        winning_card = None
        
        for pos, card in self.cards:
            if winning_card is None:
                winning_card = card
                winning_pos = pos
                continue
            
            if self.trump and self.trump != "NT":
                if card.suit == self.trump:
                    if winning_card.suit != self.trump:
                        winning_card = card
                        winning_pos = pos
                    elif card.rank_value > winning_card.rank_value:
                        winning_card = card
                        winning_pos = pos
                elif card.suit == lead_suit and winning_card.suit != self.trump:
                    if card.rank_value > winning_card.rank_value:
                        winning_card = card
                        winning_pos = pos
            else:
                if card.suit == lead_suit and card.rank_value > winning_card.rank_value:
                    winning_card = card
                    winning_pos = pos
        
        return winning_pos
    
    def to_dict(self) -> dict:
        result = {
            "cards": [(pos, card.to_dict()) for pos, card in self.cards],
            "is_ai_cards": self.is_ai_cards,
            "ai_reasons": self.ai_reasons,
            "ai_risks": self.ai_risks,
            "leader": self.leader,
            "trump": self.trump,
            "winner": self.winner(),
        }
        print(f"[DEBUG Trick.to_dict] cards count={len(self.cards)}, is_ai_cards={self.is_ai_cards}")
        return result


@dataclass
class PlayState:
    contract: Contract
    hands: Dict[str, List[Card]]
    dummy: Optional[str] = None
    player_roles: Dict[str, str] = field(default_factory=dict)
    tricks: List[Trick] = field(default_factory=list)
    current_trick: Trick = field(default_factory=Trick)
    current_player: Optional[str] = None
    lead_player: Optional[str] = None
    declarer_tricks: int = 0
    defender_tricks: int = 0
    phase: PlayPhase = PlayPhase.LEAD
    
    def __post_init__(self):
        if self.contract:
            self.current_trick = Trick(trump=self.contract.suit)
            if self.contract.suit != "NT":
                self.dummy = PARTNERS.get(self.contract.declarer)
            else:
                self.dummy = PARTNERS.get(self.contract.declarer)
            
            self.lead_player = self._get_left_hand(self.contract.declarer)
            self.current_player = self.lead_player
            self.phase = PlayPhase.LEAD
    
    def _get_left_hand(self, position: str) -> str:
        idx = POSITION_ORDER.index(position)
        return POSITION_ORDER[(idx + 1) % 4]
    
    def _get_right_hand(self, position: str) -> str:
        idx = POSITION_ORDER.index(position)
        return POSITION_ORDER[(idx - 1) % 4]
    
    def is_human_turn(self) -> bool:
        if not self.current_player:
            return False
        
        if self.current_player == self.dummy:
            return self.player_roles.get(self.contract.declarer) == PlayerRole.HUMAN.value
        
        return self.player_roles.get(self.current_player) == PlayerRole.HUMAN.value
    
    def get_playable_cards(self, position: str) -> List[Card]:
        hand = self.hands.get(position, [])
        if not hand:
            return []
        
        if not self.current_trick.cards:
            return list(hand)
        
        lead_suit = self.current_trick.get_lead_suit()
        same_suit_cards = [c for c in hand if c.suit == lead_suit]
        
        if same_suit_cards:
            return same_suit_cards
        
        return list(hand)
    
    def play_card(self, position: str, card: Card, is_ai: bool = False, reason: str = None, risk: str = None) -> bool:
        if position != self.current_player:
            return False
        
        playable = self.get_playable_cards(position)
        if card not in playable:
            return False
        
        print(f"[DEBUG PlayState.play_card] position={position}, card={card}, is_ai={is_ai}")
        self.current_trick.add_card(position, card, is_ai, reason, risk)
        print(f"[DEBUG PlayState.play_card] current_trick.is_ai_cards={self.current_trick.is_ai_cards}")
        self.hands[position].remove(card)
        
        if self.current_trick.is_complete():
            winner = self.current_trick.winner()
            if winner:
                if winner in [self.contract.declarer, self.dummy]:
                    self.declarer_tricks += 1
                else:
                    self.defender_tricks += 1
            
            self.tricks.append(self.current_trick)
            self.current_trick = Trick(trump=self.contract.suit)
            self.current_player = winner
            
            if len(self.tricks) == 13:
                self.phase = PlayPhase.COMPLETE
            else:
                self.phase = PlayPhase.PLAYING
        else:
            idx = POSITION_ORDER.index(position)
            self.current_player = POSITION_ORDER[(idx + 1) % 4]
            
            if self.phase == PlayPhase.LEAD:
                self.phase = PlayPhase.DUMMY_REVEAL
            elif self.phase == PlayPhase.DUMMY_REVEAL:
                self.phase = PlayPhase.PLAYING
        
        return True
    
    def to_dict(self) -> dict:
        return {
            "contract": self.contract.to_dict() if self.contract else None,
            "hands": {pos: [c.to_dict() for c in cards] for pos, cards in self.hands.items()},
            "dummy": self.dummy,
            "player_roles": self.player_roles,
            "tricks": [t.to_dict() for t in self.tricks],
            "current_trick": self.current_trick.to_dict(),
            "current_player": self.current_player,
            "lead_player": self.lead_player,
            "declarer_tricks": self.declarer_tricks,
            "defender_tricks": self.defender_tricks,
            "phase": self.phase.value,
            "is_human_turn": self.is_human_turn(),
        }


def parse_hand_to_cards(hand_dict: dict) -> List[Card]:
    cards = []
    for suit_name in ["spades", "hearts", "diamonds", "clubs"]:
        suit_cards = hand_dict.get(suit_name, "")
        suit_symbol = {"spades": "♠", "hearts": "♥", "diamonds": "♦", "clubs": "♣"}[suit_name]
        for rank in suit_cards:
            if rank.upper() in "AKQJT98765432":
                cards.append(Card(suit=suit_symbol, rank=rank.upper()))
    return cards


def parse_hands_dict(hands_dict: Dict[str, dict]) -> Dict[str, List[Card]]:
    result = {}
    for position, hand_dict in hands_dict.items():
        result[position] = parse_hand_to_cards(hand_dict)
    return result
