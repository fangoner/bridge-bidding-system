import random
import re
from collections import defaultdict
from dataclasses import dataclass, field
from typing import Dict, List, Optional
from enum import Enum


class Position(Enum):
    SOUTH = "南"
    WEST = "西"
    NORTH = "北"
    EAST = "东"


class DealMode(Enum):
    FREE = "自由发牌"
    GAME = "南北进局"
    SLAM = "南北满贯"


POSITION_ORDER = [Position.SOUTH, Position.WEST, Position.NORTH, Position.EAST]


@dataclass
class Hand:
    spades: str = ""
    hearts: str = ""
    diamonds: str = ""
    clubs: str = ""
    
    @property
    def hcp(self) -> int:
        hcp_values = {'A': 4, 'K': 3, 'Q': 2, 'J': 1}
        total = 0
        for suit in [self.spades, self.hearts, self.diamonds, self.clubs]:
            for card in suit:
                total += hcp_values.get(card, 0)
        return total
    
    @property
    def distribution(self) -> str:
        return f"S{len(self.spades)}-H{len(self.hearts)}-D{len(self.diamonds)}-C{len(self.clubs)}"
    
    def to_display_string(self) -> str:
        suits = []
        suits.append(f"♠{self.spades if self.spades else '-'}")
        suits.append(f"♥{self.hearts if self.hearts else '-'}")
        suits.append(f"♦{self.diamonds if self.diamonds else '-'}")
        suits.append(f"♣{self.clubs if self.clubs else '-'}")
        return " ".join(suits)
    
    def to_simple_string(self) -> str:
        spades = self.spades if self.spades else "-"
        hearts = self.hearts if self.hearts else "-"
        diamonds = self.diamonds if self.diamonds else "-"
        clubs = self.clubs if self.clubs else "-"
        return f"{spades} {hearts} {diamonds} {clubs}"


class BridgeDealer:
    SUITS = ["♠", "♥", "♦", "♣"]
    RANK_ORDER = ["A", "K", "Q", "J", "T", "9", "8", "7", "6", "5", "4", "3", "2"]
    
    def __init__(self, deal_mode: DealMode = DealMode.FREE):
        self.deck = []
        self.hands: Dict[Position, Hand] = {}
        self.deal_mode = deal_mode
        self._generate_deck()
    
    def _generate_deck(self):
        self.deck = [(suit, rank) for suit in self.SUITS for rank in self.RANK_ORDER]
    
    def _fisher_yates_shuffle(self, rounds: int = 7):
        for _ in range(rounds):
            for i in range(len(self.deck) - 1, 0, -1):
                j = random.randint(0, i)
                self.deck[i], self.deck[j] = self.deck[j], self.deck[i]
    
    def _deal_cards(self):
        players = POSITION_ORDER
        temp_hands = {p: defaultdict(list) for p in players}
        counters = {p: 0 for p in players}
        
        for i, (suit, rank) in enumerate(self.deck):
            target = players[i % 4]
            temp_hands[target][suit].append(rank)
            counters[target] += 1
        
        for position in players:
            hand = Hand()
            hand.spades = "".join(sorted(temp_hands[position]["♠"], key=lambda x: self.RANK_ORDER.index(x)))
            hand.hearts = "".join(sorted(temp_hands[position]["♥"], key=lambda x: self.RANK_ORDER.index(x)))
            hand.diamonds = "".join(sorted(temp_hands[position]["♦"], key=lambda x: self.RANK_ORDER.index(x)))
            hand.clubs = "".join(sorted(temp_hands[position]["♣"], key=lambda x: self.RANK_ORDER.index(x)))
            self.hands[position] = hand
    
    def _get_ns_hcp(self) -> int:
        return self.hands[Position.SOUTH].hcp + self.hands[Position.NORTH].hcp
    
    def _swap_hands(self, pos1: Position, pos2: Position):
        self.hands[pos1], self.hands[pos2] = self.hands[pos2], self.hands[pos1]
    
    def _adjust_for_game(self):
        max_attempts = 1000
        attempts = 0
        
        while attempts < max_attempts:
            ns_hcp = self._get_ns_hcp()
            if 22 <= ns_hcp <= 30:
                return
            self._fisher_yates_shuffle()
            self._deal_cards()
            attempts += 1
    
    def _adjust_for_slam(self):
        max_attempts = 1000
        attempts = 0
        
        while attempts < max_attempts:
            ns_hcp = self._get_ns_hcp()
            if ns_hcp >= 28:
                return
            self._fisher_yates_shuffle()
            self._deal_cards()
            attempts += 1
    
    def deal(self) -> Dict[Position, Hand]:
        self._fisher_yates_shuffle()
        self._deal_cards()
        
        if self.deal_mode == DealMode.GAME:
            self._adjust_for_game()
        elif self.deal_mode == DealMode.SLAM:
            self._adjust_for_slam()
        else:
            if random.random() < 0.7:
                positions = list(self.hands.keys())
                hcps = [self.hands[p].hcp for p in positions]
                max_hcp_idx = hcps.index(max(hcps))
                max_hcp_pos = positions[max_hcp_idx]
                
                ns_positions = [Position.SOUTH, Position.NORTH]
                target_pos = random.choice(ns_positions)
                
                if max_hcp_pos not in ns_positions:
                    self._swap_hands(max_hcp_pos, target_pos)
        
        return self.hands


def parse_hand_string(hand_str: str) -> Hand:
    hand_str = hand_str.replace("♠", " ").replace("♥", " ").replace("♦", " ").replace("♣", " ")
    parts = hand_str.split()
    
    while len(parts) < 4:
        parts.append("")
    
    def clean_suit(s: str) -> str:
        if s == "-" or s == "":
            return ""
        return s
    
    return Hand(
        spades=clean_suit(parts[0]),
        hearts=clean_suit(parts[1]),
        diamonds=clean_suit(parts[2]),
        clubs=clean_suit(parts[3])
    )


def parse_deal_input(input_text: str) -> Dict[Position, Hand]:
    # 按行分割，不过滤空行（保留位置信息：第1行=南，第2行=西，第3行=北，第4行=东）
    raw_lines = input_text.split("\n")
    lines = [l.strip() for l in raw_lines]
    # 只取前4行
    lines = lines[:4]

    result = {}
    positions = [Position.SOUTH, Position.WEST, Position.NORTH, Position.EAST]
    for i, pos in enumerate(positions):
        if i < len(lines) and lines[i]:
            result[pos] = parse_hand_string(lines[i])

    return result
