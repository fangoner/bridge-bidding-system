import subprocess
import tempfile
import os
import re
from pathlib import Path
from typing import Dict, Optional, Tuple
from config import DEEP_FINESSE_CLI_PATH, DEEP_FINESSE_PATH


def hand_to_df_format(cards: str) -> str:
    cards = cards.upper()
    cards = cards.replace("10", "T")
    cards = re.sub(r'[♠♥♦♣SHDC]', '', cards)
    suits = cards.split()
    result = []
    for suit in suits:
        if suit == "-":
            result.append("-")
        elif suit:
            result.append(suit)
    while len(result) < 4:
        result.append("-")
    return " ".join(result[:4])


def df_format_to_hand(df_hand: str) -> str:
    suits = df_hand.strip().split()
    result = []
    for suit in suits:
        if suit == "-":
            result.append("-")
        else:
            result.append(suit.replace("T", "10"))
    return " ".join(result)


def parse_df_deal(df_text: str) -> Dict:
    result = {
        "north": None,
        "east": None,
        "south": None,
        "west": None,
        "contract": None,
        "declarer": "南",
        "onlead": None,
        "lead": None
    }
    
    lines = df_text.strip().split('\n')
    
    for line in lines:
        line_stripped = line.strip()
        
        if line_stripped.startswith("Deal:"):
            match = re.search(r'Deal:\s*\d+\s+(.+)', line_stripped)
            if match:
                result["north"] = match.group(1).strip()
        
        elif line_stripped.startswith("Contract:"):
            match = re.search(r'Contract:\s*(\S+)', line_stripped)
            if match:
                contract_full = match.group(1).upper()
                contract = contract_full
                for suffix in ["-SOUTH", "-NORTH", "-EAST", "-WEST"]:
                    if contract.endswith(suffix):
                        contract = contract[:-len(suffix)]
                        result["declarer"] = suffix[1:]
                        break
                if contract.endswith("N") and not contract.endswith("NT"):
                    contract = contract + "T"
                result["contract"] = contract
            
            rest = line_stripped[9:].strip()
            rest = re.sub(r'^\S+\s+', '', rest)
            
            parts = re.split(r'\s{2,}', rest)
            if len(parts) >= 1:
                result["west"] = parts[0].strip()
            if len(parts) >= 2:
                result["east"] = parts[1].strip()
        
        elif line_stripped.startswith("OnLead:"):
            match = re.search(r'OnLead:\s*(\S+)\s+(.+)', line_stripped)
            if match:
                result["onlead"] = match.group(1).upper()
                result["south"] = match.group(2).strip()
            else:
                match = re.search(r'OnLead:\s*\S+\s+(.+)', line_stripped)
                if match:
                    result["south"] = match.group(1).strip()
        
        elif line_stripped.startswith("Lead:"):
            match = re.search(r'Lead:\s*(\S+)', line_stripped)
            if match:
                result["lead"] = match.group(1).upper()
    
    return result


def rotate_hands_for_declarer(hands: Dict, declarer: str) -> Dict:
    position_order = ["南", "西", "北", "东"]
    df_positions = ["S", "W", "N", "E"]
    
    declarer_map = {"SOUTH": "南", "WEST": "西", "NORTH": "北", "EAST": "东",
                    "南": "南", "西": "西", "北": "北", "东": "东"}
    declarer_cn = declarer_map.get(declarer.upper(), "南")
    
    declarer_idx = position_order.index(declarer_cn)
    
    rotated = {}
    for i, pos in enumerate(position_order):
        new_idx = (i - declarer_idx) % 4
        rotated[df_positions[new_idx]] = hands[pos]
    
    return rotated


def create_df_input(hands: Dict, contract: str, declarer: str, onlead: str = None, lead: str = None) -> str:
    north = hand_to_df_format(hands["北"])
    west = hand_to_df_format(hands["西"])
    east = hand_to_df_format(hands["东"])
    south = hand_to_df_format(hands["南"])
    
    contract_df = contract.upper()
    
    declarer_map = {"南": "South", "西": "West", "北": "North", "东": "East",
                    "SOUTH": "South", "WEST": "West", "NORTH": "North", "EAST": "East"}
    declarer_en = declarer_map.get(declarer.upper(), "South")
    
    contract_df = f"{contract_df}-{declarer_en}"
    
    onlead_en = "West"
    if onlead:
        onlead_en = declarer_map.get(onlead.upper(), "West")
    
    lead_str = f"Lead: {lead}" if lead else "Lead: "
    
    lines = [
        f"Deal: 1                                         {north}",
        f"Contract: {contract_df}   {west}   {east}",
        f"OnLead: {onlead_en}                              {south}",
        lead_str,
        "Result: ?",
    ]
    
    return "\n".join(lines)


def parse_contract_info(bidding_sequence: str) -> Tuple[str, str]:
    if not bidding_sequence:
        return "3NT", "南"
    
    bidding_str = bidding_sequence.replace("（", "(").replace("）", ")")
    parts = re.split(r'[-—－]', bidding_str)
    
    bids = []
    for part in parts:
        part = part.strip()
        match = re.search(r'\(([^)]+)\)\s*(\S+)', part)
        if match:
            position = match.group(1)
            bid = match.group(2).upper()
            if bid == "P":
                bid = "PASS"
            bids.append((position, bid))
    
    contract = None
    declarer = None
    
    for i, (pos, bid) in enumerate(bids):
        if bid not in ["PASS", "X", "XX"]:
            if re.match(r'^[1-7][CDHSN]T?$', bid):
                contract = bid
    
    if contract:
        first_bidder = None
        contract_suit = contract[-1] if contract[-1] != 'T' else contract[-2]
        
        for pos, bid in bids:
            if bid not in ["PASS", "X", "XX"]:
                if bid[-1] == contract_suit or (bid[-1] == 'T' and contract_suit == 'N'):
                    if first_bidder is None:
                        first_bidder = pos
                    declarer = pos
                    break
        
        if declarer is None:
            declarer = first_bidder if first_bidder else "南"
    
    if not contract:
        contract = "3NT"
    if not declarer:
        declarer = "南"
    
    return contract, declarer


def analyze_with_deep_finesse(hands: Dict, contract: str, declarer: str, onlead: str = None, lead: str = None) -> Dict:
    if not DEEP_FINESSE_PATH.exists():
        return {
            "success": False,
            "error": "Deep Finesse 未找到。请确保 'Deep Finesse 2014 v2' 目录存在于项目目录中。"
        }
    
    try:
        df_input = create_df_input(hands, contract, declarer, onlead, lead)
        
        last_hand_file = DEEP_FINESSE_PATH.parent / "Last Hand.txt"
        
        with open(last_hand_file, 'w', encoding='utf-8') as f:
            f.write(df_input)
        
        import subprocess
        import time
        
        process = subprocess.Popen(
            [str(DEEP_FINESSE_PATH)],
            cwd=str(DEEP_FINESSE_PATH.parent)
        )
        
        time.sleep(2)
        
        try:
            import ctypes
            user32 = ctypes.windll.user32
            
            def bring_window_to_front(pid):
                def callback(hwnd, hwnd_list):
                    if user32.IsWindowVisible(hwnd):
                        window_pid = ctypes.c_ulong()
                        user32.GetWindowThreadProcessId(hwnd, ctypes.byref(window_pid))
                        if window_pid.value == pid:
                            hwnd_list.append(hwnd)
                    return True
                
                hwnd_list = []
                user32.EnumWindows(ctypes.WINFUNCTYPE(ctypes.c_bool, ctypes.c_void_p, ctypes.c_void_p)(callback), 0)
                
                if hwnd_list:
                    hwnd = hwnd_list[0]
                    user32.ShowWindow(hwnd, 9)  # SW_RESTORE
                    user32.SetForegroundWindow(hwnd)
                    return True
                return False
            
            bring_window_to_front(process.pid)
        except Exception as e:
            print(f"置顶窗口失败: {e}")
        
        return {
            "success": True,
            "contract": contract,
            "declarer": declarer,
            "can_make": None,
            "tricks": None,
            "message": f"已启动 Deep Finesse GUI，牌局已保存到: {last_hand_file}",
            "deal_file": str(last_hand_file)
        }
            
    except Exception as e:
        return {"success": False, "error": f"分析过程出错: {str(e)}"}


def parse_df_output(output: str, contract: str, declarer: str) -> Dict:
    result = {
        "success": True,
        "contract": contract,
        "declarer": declarer,
        "can_make": None,
        "tricks": None,
        "raw_output": output
    }
    
    if "Result:" in output:
        match = re.search(r'Result:\s*(\S+)', output)
        if match:
            result_str = match.group(1)
            if result_str.lower() == "down":
                result["can_make"] = False
            elif result_str.lower() == "makes":
                result["can_make"] = True
            elif result_str.startswith("+"):
                result["can_make"] = True
                try:
                    result["tricks"] = int(result_str[1:]) + 6 + int(contract[0])
                except:
                    pass
            elif result_str.startswith("-"):
                result["can_make"] = False
                try:
                    result["tricks"] = 6 + int(contract[0]) - int(result_str[1:])
                except:
                    pass
    
    return result


def format_analysis_result(analysis: Dict) -> str:
    if not analysis.get("success"):
        return f"\n分析失败: {analysis.get('error', '未知错误')}"
    
    lines = [
        "\n" + "=" * 60,
        "Deep Finesse 双明手分析",
        "=" * 60,
        f"定约: {analysis.get('contract', '未知')}",
        f"庄家: {analysis.get('declarer', '未知')}",
    ]
    
    if analysis.get("message"):
        lines.append("")
        lines.append(analysis["message"])
        lines.append("")
        lines.append("请在 Deep Finesse 窗口中查看分析结果。")
    elif analysis.get("can_make") is not None:
        if analysis["can_make"]:
            lines.append(f"结果: 可以打成 ✓")
        else:
            lines.append(f"结果: 无法打成 ✗")
        
        if analysis.get("tricks"):
            lines.append(f"可拿墩数: {analysis['tricks']}")
    else:
        lines.append("结果: 未能解析")
    
    lines.append("=" * 60)
    
    return "\n".join(lines)
