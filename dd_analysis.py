#!/usr/bin/env python3
"""双明手分析模块（DD Analysis）。

基于 DirectDDS（ctypes 直调 DDS C 库的 CalcDDtable），一次性计算
4 庄家 × 5 将牌 = 20 个组合的最高可成约阶数，用于"小房子"分析表。

历史：原使用 endplay Python 库的 calc_dd_table/solve_board 封装，
2026-07 改用 DirectDDS，仅保留 endplay._dds 用于定位 dds.dll 路径
（在 direct_dds._load_dll 中）。
"""

import sys
from pathlib import Path
from typing import Dict, List, Optional, Union

# 导入项目内部模块
sys.path.insert(0, str(Path(__file__).parent))
try:
    from bridge.dealer import Hand, Position, parse_hand_string
    PROJECT_IMPORTS_AVAILABLE = True
except ImportError:
    PROJECT_IMPORTS_AVAILABLE = False

# 导入 DirectDDS
try:
    from bridge.mcts.direct_dds import calc_dd_table, solve_all_boards_raw
    from bridge.mcts.dd_search import _dds_result_to_score_map
    from bridge.play_types import Card
    DDS_AVAILABLE = True
except ImportError:
    DDS_AVAILABLE = False
    print("警告: DirectDDS 模块不可用，双明手分析功能不可用")


def _hand_str_to_cards(hand_str: str) -> List[Card]:
    """'AQJ5 KQJ8 765 43' → [Card, ...] 按 S/H/D/C 顺序解析。"""
    from bridge.mcts.state_utils import hand_str_to_cards
    return hand_str_to_cards(hand_str)


def _hands_dict_to_card_hands(hands_dict: Dict[str, str]) -> Dict[str, List[Card]]:
    """{pos: hand_str} → {pos: [Card, ...]}"""
    return {pos: _hand_str_to_cards(hs) for pos, hs in hands_dict.items()}


def _normalize_hands_input(hands: Union[Dict, object]) -> Dict[str, str]:
    """将多种输入格式统一为 {pos: hand_str}。"""
    hands_dict = {}
    for key, hand in hands.items():
        pos_name = key.value if hasattr(key, "value") else key
        if hasattr(hand, "to_simple_string"):
            hand_str = hand.to_simple_string()
        else:
            hand_str = hand
        hands_dict[pos_name] = hand_str
    return hands_dict


def _dd_table_to_results(table: List[List[int]]) -> Dict:
    """DDS resTable → 项目格式 results。

    DDS resTable[denom][first]：
      denom: 0=S, 1=H, 2=D, 3=C, 4=NT（与 DDS C 库一致，NT 在最后）
      first: 0=N, 1=E, 2=S, 3=W
    项目格式：
      results[declarer][trump] = {max_level, tricks, contract}
      declarer: "北"/"东"/"南"/"西"
      trump: "S"/"H"/"D"/"C"/"NT"
    """
    declarer_order = ["北", "东", "南", "西"]
    denom_to_trump = {0: "S", 1: "H", 2: "D", 3: "C", 4: "NT"}

    results = {}
    for i, declarer in enumerate(declarer_order):
        results[declarer] = {}
        for denom, trump in denom_to_trump.items():
            tricks = table[denom][i]
            max_level = 0
            for level in range(7, 0, -1):
                if tricks >= 6 + level:
                    max_level = level
                    break
            results[declarer][trump] = {
                "max_level": max_level,
                "tricks": tricks,
                "contract": f"{max_level}{trump}" if max_level > 0 else "无法完成"
            }
    return results


def analyze_all_contracts(hands: Union[Dict, object], hcp_dict: Dict = None) -> Dict:
    """计算双明手表：4 庄家 × 5 将牌的最高可成约阶数。

    使用 DirectDDS（ctypes 直调 DDS C 库的 CalcDDtable）。

    Args:
        hands: 手牌字典，键为位置（"南"/"西"/"北"/"东"），值为 Hand 对象或手牌字符串
        hcp_dict: 可选的大牌点力字典

    Returns:
        {
            "success": True/False,
            "results": {pos: {trump: {max_level, tricks, contract}}, ...},
            "hcp": hcp_dict,
            "formatted_output": str,
        }
    """
    if not DDS_AVAILABLE:
        return {
            "success": False,
            "error": "DirectDDS 模块不可用"
        }

    try:
        hands_dict = _normalize_hands_input(hands)
        card_hands = _hands_dict_to_card_hands(hands_dict)

        if any(not cards for cards in card_hands.values()):
            return {"success": False, "error": "手牌不完整"}

        table = calc_dd_table(card_hands)
        if table is None:
            return {"success": False, "error": "DDS CalcDDtable 失败"}

        results = _dd_table_to_results(table)
        return {
            "success": True,
            "table": table,
            "results": results,
            "hcp": hcp_dict,
            "formatted_output": format_dd_results(results, hcp_dict)
        }
    except Exception as e:
        return {
            "success": False,
            "error": f"分析过程出错: {str(e)}",
            "traceback": str(sys.exc_info())
        }


def format_dd_results(results: Dict, hcp_dict: Dict = None) -> str:
    """格式化双明手分析结果为表格字符串。"""
    lines = []
    lines.append("\n" + "=" * 60)
    lines.append("双明手分析结果 - 最高可完成定约")
    lines.append("=" * 60)

    declarer_order = ["北", "东", "南", "西"]
    trump_order = ["S", "H", "D", "C", "NT"]

    table_data = {}
    for trump in trump_order:
        table_data[trump] = {}
        for declarer in declarer_order:
            if declarer in results and trump in results[declarer]:
                info = results[declarer][trump]
                level = info["max_level"]
                if level > 0:
                    table_data[trump][declarer] = f"{level}{trump}"
                else:
                    table_data[trump][declarer] = "-"
            else:
                table_data[trump][declarer] = "-"

    COLUMN_WIDTH = 6

    def pad_chinese(text, width):
        display_width = sum(2 if ord(c) > 127 else 1 for c in text)
        return text + " " * (width - display_width)

    header_line = "".join(pad_chinese(d, COLUMN_WIDTH) for d in declarer_order)
    lines.append(header_line)
    lines.append(("-" * COLUMN_WIDTH) * len(declarer_order))

    for trump in trump_order:
        row_line = "".join(pad_chinese(table_data[trump].get(d, "-"), COLUMN_WIDTH)
                           for d in declarer_order)
        lines.append(row_line)

    lines.append("=" * 60)
    return "\n".join(lines)


def main():
    """测试主函数"""
    if not DDS_AVAILABLE:
        print("请确保 DirectDDS 模块可用")
        return

    example_hands = {
        "南": "AQJ5 KQJ8 765 43",
        "西": "K87 765 AKJ9 765",
        "北": "T9432 A32 T82 98",
        "东": "6 T94 Q43 AKQJT2"
    }

    print("测试 DirectDDS 集成")
    print("=" * 60)
    print("\n示例牌局:")
    for pos, hand in example_hands.items():
        print(f"  {pos}: {hand}")

    print("\n" + "=" * 60)
    print("开始批量双明手分析...")

    result = analyze_all_contracts(example_hands)

    if result["success"]:
        print(result["formatted_output"])
    else:
        print(f"分析失败: {result.get('error')}")


if __name__ == "__main__":
    main()
