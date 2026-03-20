import re
from typing import Dict, List, Tuple, Optional

from bridge.dealer import Position, Hand


POSITION_ORDER = [Position.SOUTH, Position.WEST, Position.NORTH, Position.EAST]
POSITION_NAMES = {"南": "South", "西": "West", "北": "North", "东": "East"}
CHINESE_TO_POSITION = {"南": Position.SOUTH, "西": Position.WEST, "北": Position.NORTH, "东": Position.EAST}


def display_width(s: str) -> int:
    width = 0
    for c in s:
        if '\u4e00' <= c <= '\u9fff':
            width += 2
        else:
            width += 1
    return width


def pad_to_width(s: str, width: int) -> str:
    current_width = display_width(s)
    if current_width >= width:
        return s
    return s + ' ' * (width - current_width)


def parse_bidding_for_table(bidding_str: str, dealer: Position) -> List[List[Tuple[str, str]]]:
    if not bidding_str:
        return []
    
    bidding_str = bidding_str.replace("（", "(").replace("）", ")")
    bidding_str = bidding_str.replace("—", "-").replace("－", "-")
    
    parts = re.split(r'[-—－]', bidding_str)
    bids_with_pos = []
    
    for part in parts:
        part = part.strip()
        if not part:
            continue
        match = re.search(r'\(([^)]+)\)\s*(\S+)', part)
        if match:
            position = match.group(1)
            bid = match.group(2).upper()
            if bid == "P":
                bid = "pass"
            bids_with_pos.append((position, bid))
    
    return bids_with_pos


def determine_contract_and_declarer(bids: List[Tuple[str, str]]) -> Tuple[str, str, str]:
    if not bids:
        return "pass", "南", "西"
    
    final_bid = None
    final_bid_pos = None
    contract_suit = None
    declarer_pos = None
    
    suit_bids = {}
    
    for pos, bid in bids:
        if bid.lower() == "pass" or bid in ["X", "XX"]:
            continue
        
        match = re.match(r'(\d)([CDHS]|NT)', bid, re.IGNORECASE)
        if match:
            level = match.group(1)
            suit = match.group(2).upper()
            final_bid = f"{level}{suit}"
            final_bid_pos = pos
            
            if suit != "NT":
                if suit not in suit_bids:
                    suit_bids[suit] = []
                suit_bids[suit].append(pos)
    
    if final_bid is None:
        last_non_pass = None
        for pos, bid in reversed(bids):
            if bid.lower() != "pass":
                last_non_pass = (pos, bid)
                break
        if last_non_pass:
            return last_non_pass[1], last_non_pass[0], get_next_position(last_non_pass[0])
        return "pass", "南", "西"
    
    if final_bid.endswith("NT"):
        declarer_pos = final_bid_pos
        for pos, bid in reversed(bids):
            if bid.upper() == final_bid:
                partner = get_partner(pos)
                for p, b in reversed(bids):
                    if b.upper() == final_bid and p != pos:
                        declarer_pos = p
                        break
                break
    else:
        contract_suit = final_bid[-1]
        declarer_pos = None
        
        for pos, bid in bids:
            match = re.match(r'(\d)([CDHS])', bid, re.IGNORECASE)
            if match:
                suit = match.group(2).upper()
                if suit == contract_suit:
                    if declarer_pos is None:
                        declarer_pos = pos
                    else:
                        if is_partner(pos, declarer_pos):
                            pass
                        else:
                            pass
        
        if declarer_pos is None:
            declarer_pos = final_bid_pos
        else:
            first_in_partnership = None
            for pos, bid in bids:
                match = re.match(r'(\d)([CDHS])', bid, re.IGNORECASE)
                if match:
                    suit = match.group(2).upper()
                    if suit == contract_suit:
                        if first_in_partnership is None:
                            first_in_partnership = pos
                        elif is_partner(pos, first_in_partnership):
                            declarer_pos = first_in_partnership
                            break
    
    on_lead = get_next_position(declarer_pos)
    
    return final_bid, declarer_pos, on_lead


def get_partner(pos: str) -> str:
    partners = {"南": "北", "北": "南", "东": "西", "西": "东"}
    return partners.get(pos, "")


def is_partner(pos1: str, pos2: str) -> bool:
    return get_partner(pos1) == pos2


def get_next_position(pos: str) -> str:
    order = ["南", "西", "北", "东"]
    idx = order.index(pos) if pos in order else 0
    return order[(idx + 1) % 4]


def get_position_index(pos: str) -> int:
    order = ["南", "西", "北", "东"]
    return order.index(pos) if pos in order else 0


def generate_graphic_output(
    hands: Dict[Position, 'Hand'],
    bidding_str: str,
    dealer: Position,
    mode: str = "四人叫牌",
    human_position: Optional[Position] = None,
    bid_meaning: str = ""
) -> str:
    lines = []
    
    COL1_WIDTH = 10
    COL2_WIDTH = 15
    COL3_WIDTH = 10
    
    def format_hand_display(hand: 'Hand', position: Position) -> List[str]:
        result = []
        pos_name = position.value
        hcp = hand.hcp
        result.append(f"  {pos_name} ({hcp})")
        result.append(f"  ♠ {hand.spades if hand.spades else '-'}")
        result.append(f"  ♥ {hand.hearts if hand.hearts else '-'}")
        result.append(f"  ♦ {hand.diamonds if hand.diamonds else '-'}")
        result.append(f"  ♣ {hand.clubs if hand.clubs else '-'}")
        return result
    
    north_lines = format_hand_display(hands[Position.NORTH], Position.NORTH)
    south_lines = format_hand_display(hands[Position.SOUTH], Position.SOUTH)
    west_lines = format_hand_display(hands[Position.WEST], Position.WEST)
    east_lines = format_hand_display(hands[Position.EAST], Position.EAST)
    
    max_north_width = max(display_width(line) for line in north_lines)
    max_south_width = max(display_width(line) for line in south_lines)
    
    # 动态计算东西方向的最大宽度，确保竖线对齐
    max_west_width = max(display_width(line) for line in west_lines)
    max_east_width = max(display_width(line) for line in east_lines)
    COL1_WIDTH = max(COL1_WIDTH, max_west_width)
    COL3_WIDTH = max(COL3_WIDTH, max_east_width)
    
    for line in north_lines:
        lines.append(" " * COL1_WIDTH + " " + line)
    
    border = " " * COL1_WIDTH + "+" + "-" * (COL2_WIDTH - 2) + "+"
    lines.append(border)
    
    west_parts = west_lines
    east_parts = east_lines
    max_side_lines = max(len(west_parts), len(east_parts))
    
    for i in range(max_side_lines):
        west_line = west_parts[i] if i < len(west_parts) else ""
        east_line = east_parts[i] if i < len(east_parts) else ""
        col1 = pad_to_width(west_line, COL1_WIDTH)
        col3 = pad_to_width(east_line, COL3_WIDTH)
        lines.append(f"{col1}|{' ' * (COL2_WIDTH - 2)}|{col3}")
    
    lines.append(border)
    
    for line in south_lines:
        lines.append(" " * COL1_WIDTH + " " + line)
    
    lines.append("")
    
    bids_with_pos = parse_bidding_for_table(bidding_str, dealer)
    
    if bids_with_pos:
        header = "South    " + "West     " + "North    " + "East     "
        lines.append(header)
        lines.append("-" * 36)
        
        position_order = ["南", "西", "北", "东"]
        dealer_idx = position_order.index(dealer.value) if dealer.value in position_order else 0
        
        table = []
        current_row = [None, None, None, None]
        current_col = dealer_idx
        
        for pos, bid in bids_with_pos:
            current_row[current_col] = bid
            current_col += 1
            
            if current_col >= 4:
                table.append(current_row)
                current_row = [None, None, None, None]
                current_col = 0
        
        if any(cell is not None for cell in current_row):
            table.append(current_row)
        
        for row in table:
            row_parts = []
            for cell in row:
                if cell is None:
                    row_parts.append("         ")
                else:
                    row_parts.append(f"{cell:<9}")
            lines.append("".join(row_parts))
    
    lines.append("")
    
    if bid_meaning:
        lines.append("=" * 60)
        lines.append("叫牌历史:")
        lines.append(bid_meaning)
        lines.append("=" * 60)
    
    return "\n".join(lines)


def generate_compact_output(hands: Dict[Position, 'Hand']) -> str:
    lines = []
    for pos in POSITION_ORDER:
        hand = hands[pos]
        spades = hand.spades if hand.spades else "-"
        hearts = hand.hearts if hand.hearts else "-"
        diamonds = hand.diamonds if hand.diamonds else "-"
        clubs = hand.clubs if hand.clubs else "-"
        lines.append(f"{spades} {hearts} {diamonds} {clubs}")
    return "\n".join(lines)


def generate_deep_finesse_output(
    hands: Dict[Position, 'Hand'],
    bidding_str: str,
    dealer: Position,
    lead_card: Optional[str] = None
) -> str:
    lines = []
    
    bids_with_pos = parse_bidding_for_table(bidding_str, dealer)
    contract, declarer, on_lead = determine_contract_and_declarer(bids_with_pos)
    
    north_hand = hands[Position.NORTH]
    west_hand = hands[Position.WEST]
    south_hand = hands[Position.SOUTH]
    east_hand = hands[Position.EAST]
    
    north_str = f"{north_hand.spades if north_hand.spades else '-'} {north_hand.hearts if north_hand.hearts else '-'} {north_hand.diamonds if north_hand.diamonds else '-'} {north_hand.clubs if north_hand.clubs else '-'}"
    west_str = f"{west_hand.spades if west_hand.spades else '-'} {west_hand.hearts if west_hand.hearts else '-'} {west_hand.diamonds if west_hand.diamonds else '-'} {west_hand.clubs if west_hand.clubs else '-'}"
    south_str = f"{south_hand.spades if south_hand.spades else '-'} {south_hand.hearts if south_hand.hearts else '-'} {south_hand.diamonds if south_hand.diamonds else '-'} {south_hand.clubs if south_hand.clubs else '-'}"
    east_str = f"{east_hand.spades if east_hand.spades else '-'} {east_hand.hearts if east_hand.hearts else '-'} {east_hand.diamonds if east_hand.diamonds else '-'} {east_hand.clubs if east_hand.clubs else '-'}"
    
    declarer_en = POSITION_NAMES.get(declarer, "South")
    on_lead_en = POSITION_NAMES.get(on_lead, "East")
    
    contract_display = contract
    if contract == "pass":
        contract_display = "pass"
    
    lines.append(f"Deal: 1                      {north_str}")
    lines.append(f"Contract: {contract_display}-{declarer_en}     {west_str}    {east_str}")
    lines.append(f"OnLead: {on_lead_en}                 {south_str}")
    
    if lead_card:
        lines.append(f"Lead: {lead_card}")
    else:
        on_lead_hand = None
        if on_lead == "南":
            on_lead_hand = south_hand
        elif on_lead == "西":
            on_lead_hand = west_hand
        elif on_lead == "北":
            on_lead_hand = north_hand
        elif on_lead == "东":
            on_lead_hand = east_hand
        
        if on_lead_hand:
            if on_lead_hand.spades:
                lead = "S" + on_lead_hand.spades[0]
            elif on_lead_hand.hearts:
                lead = "H" + on_lead_hand.hearts[0]
            elif on_lead_hand.diamonds:
                lead = "D" + on_lead_hand.diamonds[0]
            elif on_lead_hand.clubs:
                lead = "C" + on_lead_hand.clubs[0]
            else:
                lead = ""
            if lead:
                lines.append(f"Lead: {lead}")
    
    return "\n".join(lines)


def generate_all_outputs(
    hands: Dict[Position, 'Hand'],
    bidding_str: str,
    dealer: Position,
    mode: str = "四人叫牌",
    human_position: Optional[Position] = None,
    lead_card: Optional[str] = None,
    bid_meaning: str = ""
) -> Tuple[str, str, str]:
    graphic = generate_graphic_output(hands, bidding_str, dealer, mode, human_position, bid_meaning)
    compact = generate_compact_output(hands)
    df_format = generate_deep_finesse_output(hands, bidding_str, dealer, lead_card)
    
    return graphic, compact, df_format
