import re
from typing import Optional, List, Tuple
from enum import Enum


class BidType(Enum):
    PASS = "pass"
    DOUBLE = "X"
    REDOUBLE = "XX"
    SUIT = "suit"
    NT = "NT"


def parse_bidding_sequence(bidding_str: str) -> List[str]:
    if not bidding_str:
        return []
    
    bidding_str = bidding_str.replace("（", "(").replace("）", ")")
    bidding_str = bidding_str.replace("(", "").replace(")", "")
    bidding_str = bidding_str.replace("—", "-").replace("－", "-")
    
    parts = re.split(r'[-—－]', bidding_str)
    bids = []
    
    for part in parts:
        bid_match = re.search(r'\(?\s*([1-7][CDHSN]T?|X{1,2}|pass|p)\s*\)?', part, re.IGNORECASE)
        if bid_match:
            bid = bid_match.group(1).upper()
            if bid == "P":
                bid = "pass"
            bids.append(bid)
    
    return bids


def parse_bidding_sequence_with_positions(bidding_str: str) -> List[Tuple[str, str]]:
    """解析叫牌序列，返回(位置, 叫品)的列表"""
    if not bidding_str:
        return []
    
    bidding_str = bidding_str.replace("（", "(").replace("）", ")")
    bidding_str = bidding_str.replace("—", "-").replace("－", "-")
    
    parts = re.split(r'[-—－]', bidding_str)
    result = []
    
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
            result.append((position, bid))
    
    return result


def get_position_order(position: str) -> int:
    """获取叫牌顺序（南=0, 西=1, 北=2, 东=3）"""
    order = {"南": 0, "西": 1, "北": 2, "东": 3}
    return order.get(position, -1)


def get_next_position_name(position: str) -> str:
    """获取下一个叫牌位置"""
    order = ["南", "西", "北", "东"]
    idx = get_position_order(position)
    if idx >= 0:
        return order[(idx + 1) % 4]
    return ""


def is_partner(pos1: str, pos2: str) -> bool:
    """判断两个位置是否是搭档"""
    partners = {
        "南": "北", "北": "南",
        "东": "西", "西": "东"
    }
    return partners.get(pos1) == pos2


def is_right_hand_opponent(current_pos: str, last_bid_pos: str) -> bool:
    """判断current_pos是否是last_bid_pos的右手敌方"""
    order = ["南", "西", "北", "东"]
    current_idx = get_position_order(current_pos)
    last_idx = get_position_order(last_bid_pos)
    if current_idx < 0 or last_idx < 0:
        return False
    return current_idx == (last_idx + 1) % 4


def is_left_hand_opponent(current_pos: str, last_bid_pos: str) -> bool:
    """判断current_pos是否是last_bid_pos的左手敌方"""
    order = ["南", "西", "北", "东"]
    current_idx = get_position_order(current_pos)
    last_idx = get_position_order(last_bid_pos)
    if current_idx < 0 or last_idx < 0:
        return False
    return current_idx == (last_idx + 3) % 4


def extract_retrieval_keyword(bidding_str: str, deal_system: str = "2D/2H/2S：自然阻击", current_position: str = None) -> str:
    first_bid, second_bid, third_bid, fourth_bid, result = None, None, None, None, None
    
    if bidding_str is None or bidding_str == "":
        return "花色开叫"
    
    import re
    bidding_str = bidding_str.replace('（', '(').replace('）', ')')
    bidding_str = bidding_str.replace('(', '').replace(')', ')')
    bidding_str = bidding_str.replace('—', '-').replace('－', '-')
    
    parts = re.split(r'[-—－]', bidding_str)
    bids = []
    for part in parts:
        bid_match = re.search(r'\(?\s*(?:[1-7][CDHSN]T?|X{1,2}|pass|p)\s*\)?', part, re.IGNORECASE)
        if bid_match:
            bid = bid_match.group().upper()
            if bid == 'P' or bid == 'PASS':
                bid = 'pass'
            bids.append(bid)
    
    pass_time = 0
    while bids and bids[0].strip() == 'pass':
        bids.pop(0)
        pass_time += 1
    
    if len(bids) == 0:
        return "花色开叫"
    
    first_bid = bids[0] if len(bids) > 0 else None
    second_bid = bids[1] if len(bids) > 1 else None
    third_bid = bids[2] if len(bids) > 2 else None
    fourth_bid = bids[3] if len(bids) > 3 else None
    fifth_bid = bids[4] if len(bids) > 4 else None
    sixth_bid = bids[5] if len(bids) > 5 else None
    seventh_bid = bids[6] if len(bids) > 6 else None
    eighth_bid = bids[7] if len(bids) > 7 else None
    
    is_natural_overcall = "自然阻击" in deal_system
    
    if "2D：多功能，2H/S：麦德伯格，2NT：双低花" in deal_system and first_bid in ['2H', '2S', '2D', '2NT']:
        if first_bid == '2D':
            result = "2D多功能开叫"
        elif first_bid in ['2H', '2S']:
            result = "2M麦德伯格"
        elif first_bid == '2NT':
            result = "2NT双低花阻击"
    elif len(bids) == 1:
        result = "第二家争叫"
    elif len(bids) == 2:
        if second_bid == "pass":
            if pass_time in [2, 3] and first_bid == "1H":
                result = "第三四家开叫1H"
            elif pass_time in [2, 3] and first_bid == "1S":
                result = "第三四家开叫1S"
            else:
                result = f"{first_bid}开叫"
        else:
            if first_bid == '1NT':
                if second_bid == "X":
                    if is_natural_overcall:
                        result = "12.3"
                    else:
                        result = "12.3.2\t 对方加倍表示别的含义"
                elif second_bid == "2C":
                    result = "12.3.5\t 对方非自然争叫"
                elif second_bid == "2NT":
                    result = "12.3.5\t 对方非自然争叫"
                elif second_bid in ["2D", "2H", "2S"]:
                    if is_natural_overcall:
                        result = "12.3.4\t Rubensohl 约定叫"
                    else:
                        result = "12.3.5\t 对方非自然争叫"
                elif second_bid[0] in "34567":
                    result = "12.3.6\t 对方高阶争叫"
                else:
                    result = "我方开叫1NT"
            elif first_bid == '2C':
                result = "我方开叫2C"
            elif first_bid == '1C':
                if second_bid == 'X':
                    result = "12.1.1 对方加倍后"
                elif second_bid == '2C':
                    result = "对抗对方已明确的 55 双套争叫："
                elif second_bid == '2NT':
                    result = "对抗对方已明确的 55 双套争叫："
                elif second_bid[0] == '1':
                    result = "对方一阶争叫"
                elif second_bid[0] == '2':
                    result = "对方二阶争叫："
                else:
                    result = "我方开叫1低花"
            elif first_bid == '1D':
                if second_bid == 'X':
                    result = "12.1.1 对方加倍后"
                elif second_bid == '2D':
                    result = "对抗对方已明确的 55 双套争叫："
                elif second_bid == '2NT':
                    result = "对抗对方已明确的 55 双套争叫："
                elif second_bid[0] == '1':
                    result = "对方一阶争叫"
                elif second_bid[0] == '2':
                    result = "对方二阶争叫："
                else:
                    result = "我方开叫1低花"
            elif first_bid == '1H':
                if second_bid == 'X':
                    result = "12.2.1 敌方加倍"
                elif second_bid == '2NT':
                    result = "对抗对方已明确的 55 双套争叫："
                elif second_bid == '2H':
                    result = "对抗对方只已知一套的 55 双套争叫："
                elif second_bid not in ['pass']:
                    result = "12.2.2 敌方争叫花色"
                else:
                    result = "我方开叫1高花"
            elif first_bid == '1S':
                if second_bid == 'X':
                    result = "12.2.1 敌方加倍"
                elif second_bid == '2NT':
                    result = "对抗对方已明确的 55 双套争叫："
                elif second_bid == '2S':
                    result = "对抗对方只已知一套的 55 双套争叫："
                elif second_bid not in ['pass']:
                    result = "12.2.2 敌方争叫花色"
                else:
                    result = "我方开叫1高花"
            elif first_bid[0] == '1':
                result = "我方开叫1高花"
            elif first_bid[0] in '2345' and first_bid != '2NT':
                result = "我方开叫阻击"
            elif first_bid == "2NT":
                result = "2NT均型强牌"
    elif len(bids) == 3:
        if second_bid == "pass" and third_bid != "pass":
            result = "第四家争叫"
        elif second_bid == "pass" and third_bid == "pass":
            result = "平衡位置的叫牌"
        else:
            if first_bid[0] == "1" and first_bid != "1NT":
                if second_bid == 'X':
                    result = "技术性加倍以后"
                elif (second_bid.startswith('2') and second_bid[-1] == first_bid[-1]) or second_bid == '2NT':
                    result = "Michaels扣叫与两套牌争叫"
                elif second_bid.startswith('3') and second_bid[-1] == first_bid[-1]:
                    result = "跳扣叫"
                elif second_bid == "1NT" and third_bid == "pass":
                    result = "1NT争叫"
                else:
                    result = "普通争叫"
            elif first_bid[0] in '23456' and first_bid not in ['2NT', '2C']:
                result = "对抗对方阻击叫"
            elif first_bid == "1NT":
                result = "对1NT开叫"
            elif first_bid == "2NT":
                result = "JF尚未实现"
            elif first_bid == "2C":
                result = "对精确1C和自然2C开叫"
    elif len(bids) == 4:
        if second_bid == "pass" and fourth_bid == "pass":
            if pass_time in [2, 3] and first_bid == "1H":
                result = "第三四家开叫1H"
            elif pass_time in [2, 3] and first_bid == "1S":
                result = "第三四家开叫1S"
            else:
                result = f"{first_bid}-{third_bid}"
        elif first_bid in ["1C", "1D"]:
            if first_bid == "1C" and second_bid == "pass" and third_bid == "2C" and fourth_bid not in ["pass"]:
                result = "低花反加叫被干扰"
            elif first_bid == "1D" and second_bid == "pass" and third_bid == "2D" and fourth_bid not in ["pass"]:
                result = "低花反加叫被干扰"
            elif second_bid != "pass" or fourth_bid != "pass":
                result = "开叫人的再叫"
            else:
                result = f"{first_bid}-{third_bid}"
        elif first_bid in ["1H", "1S"]:
            if second_bid == "X" and third_bid == "XX":
                result = "12.2.4 关于再加倍"
            elif first_bid == "1H" and second_bid == "pass" and third_bid == "2H" and fourth_bid not in ["pass"]:
                result = "12.2.3 我方简单加叫后敌方参与"
            elif first_bid == "1S" and second_bid == "pass" and third_bid == "2S" and fourth_bid not in ["pass"]:
                result = "12.2.3 我方简单加叫后敌方参与"
            else:
                result = f"{first_bid}-{third_bid}"
        elif third_bid != "pass" and (second_bid == "pass" or fourth_bid == "pass"):
            if first_bid == "1NT" and second_bid == "pass" and third_bid in ["2C", "2D", "2H", "2S", "2NT", "3C", "3D"] and fourth_bid not in ["pass"]:
                result = "12.3.3\t Stayman/转移叫被干扰"
            else:
                result = "成局与满贯"
        else:
            result = "自然叫牌"
    elif len(bids) == 5:
        if second_bid == "1NT" and third_bid == "pass" and fourth_bid != "pass" and bids[4] == "pass":
            result = f"{second_bid}-{fourth_bid}"
        elif second_bid != "pass" and third_bid == "pass" and fourth_bid != "pass":
            result = "成局与满贯"
        else:
            result = "自然叫牌"
    elif len(bids) == 6:
        if second_bid == "pass" and fourth_bid == "pass" and sixth_bid == "pass":
            if pass_time in [2, 3] and first_bid == "1H":
                result = "第三四家开叫1H"
            elif pass_time in [2, 3] and first_bid == "1S":
                result = "第三四家开叫1S"
            else:
                result = f"{first_bid}-{third_bid}"
        else:
            result = "成局与满贯"
    elif len(bids) == 7:
        if second_bid == "1NT" and third_bid == "pass" and fourth_bid != "pass" and fifth_bid == "pass" and sixth_bid != "pass" and seventh_bid == "pass":
            result = f"{second_bid}-{fourth_bid}"
        elif second_bid != "pass" and third_bid == "pass" and fourth_bid != "pass":
            result = "成局与满贯"
        else:
            result = "自然叫牌"
    elif len(bids) == 8:
        if second_bid == "pass" and fourth_bid == "pass" and sixth_bid == "pass" and eighth_bid == "pass":
            if pass_time in [2, 3] and first_bid == "1H":
                result = "第三四家开叫1H"
            elif pass_time in [2, 3] and first_bid == "1S":
                result = "第三四家开叫1S"
            else:
                result = f"{first_bid}-{third_bid}"
        else:
            result = "成局与满贯"
    else:
        all_even_pass = True
        for i, bid in enumerate(bids):
            if i % 2 == 1 and bid != "pass":
                all_even_pass = False
                break
        if all_even_pass:
            if pass_time in [2, 3] and first_bid == "1H":
                result = "第三四家开叫1H"
            elif pass_time in [2, 3] and first_bid == "1S":
                result = "第三四家开叫1S"
            else:
                result = f"{first_bid}-{third_bid}"
        else:
            result = "成局与满贯"
    
    return result


def get_partner_position(position) -> str:
    partner_map = {
        "南": "北",
        "北": "南",
        "东": "西",
        "西": "东"
    }
    pos_name = position.name if hasattr(position, 'name') else str(position)
    pos_cn = {"SOUTH": "南", "NORTH": "北", "EAST": "东", "WEST": "西"}.get(pos_name, pos_name)
    return partner_map.get(pos_cn, "")


def get_position_name(position) -> str:
    if hasattr(position, 'value'):
        return position.value
    return {"SOUTH": "南", "NORTH": "北", "EAST": "东", "WEST": "西"}.get(str(position), str(position))


def get_next_position(current_position) -> str:
    order = ["南", "西", "北", "东"]
    pos_name = get_position_name(current_position)
    idx = order.index(pos_name)
    return order[(idx + 1) % 4]


def is_valid_bid(bid: str, last_bid: Optional[str] = None) -> bool:
    if bid.lower() == "pass":
        return True
    if bid in ["X", "XX"]:
        return True
    
    match = re.match(r'^([1-7])([CDHS]|NT)$', bid, re.IGNORECASE)
    if not match:
        return False
    
    if last_bid is None:
        return True
    
    if last_bid.lower() == "pass":
        return True
    
    last_match = re.match(r'^([1-7])([CDHS]|NT)$', last_bid, re.IGNORECASE)
    if not last_match:
        return True
    
    new_level = int(match.group(1))
    new_suit = match.group(2).upper()
    last_level = int(last_match.group(1))
    last_suit = last_match.group(2).upper()
    
    suit_rank = {"C": 1, "D": 2, "H": 3, "S": 4, "N": 5}
    
    if new_level > last_level:
        return True
    if new_level == last_level:
        if suit_rank.get(new_suit[0], 0) > suit_rank.get(last_suit[0], 0):
            return True
        return False
    return False
