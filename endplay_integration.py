#!/usr/bin/env python3
"""使用 endplay 库进行批量双明手分析"""

import sys
from pathlib import Path
from typing import Dict, List, Optional, Tuple, Union
import itertools

# 尝试导入 endplay
try:
    from endplay import Deal
    from endplay.dds import calc_dd_table, solve_board
    from endplay.types import Denom, Player
    ENDPLAY_AVAILABLE = True
except ImportError:
    ENDPLAY_AVAILABLE = False
    print("警告: endplay 库未安装，部分功能不可用")
    print("安装命令: pip install endplay")

# 导入项目内部模块
sys.path.insert(0, str(Path(__file__).parent))
try:
    from bridge.dealer import Hand, Position, parse_hand_string
    PROJECT_IMPORTS_AVAILABLE = True
except ImportError:
    PROJECT_IMPORTS_AVAILABLE = False
    print("警告: 无法导入项目内部模块")


def convert_hand_to_pbn(hands_dict: Dict[str, str]) -> str:
    """
    将手牌字典转换为 PBN 格式字符串

    Args:
        hands_dict: 手牌字典，键为"南"、"西"、"北"、"东"，值为手牌字符串
                   例如: "AQJ5 KQJ8 765 43"

    Returns:
        PBN 格式字符串，例如: "N:QJ6.K652.J85.T98 732.JT87.QT6.QJ4 K5.Q93.AK942.A76 AT984.A4.73.K532"
    """
    # PBN 格式: 先指定发牌人，然后是四个手牌，用空格分隔
    # 每个手牌用点号分隔花色: S.H.D.C
    # 我们需要将中文位置转换为英文位置
    position_map = {"北": "N", "东": "E", "南": "S", "西": "W"}

    # 假设北家是发牌人（PBN格式要求指定发牌人）
    dealer = "N"

    # 构建四个手牌的PBN字符串
    pbn_parts = []

    # 按北、东、南、西的顺序（PBN标准顺序）
    for pos_en in ["N", "E", "S", "W"]:
        # 找到对应的中文位置
        pos_cn = None
        for cn, en in position_map.items():
            if en == pos_en:
                pos_cn = cn
                break

        if pos_cn in hands_dict:
            hand_str = hands_dict[pos_cn]
            # 手牌格式: "AQJ5 KQJ8 765 43" -> 需要转换为 "AQJ5.KQJ8.765.43"
            # 先去除多余空格
            hand_str = hand_str.strip()

            # 尝试分割成4个花色
            suits = hand_str.split()

            # 处理空花色情况：如果少于4个部分，补全为空字符串
            while len(suits) < 4:
                suits.append("")

            # 如果多于4个部分，取前4个（应该不会出现）
            if len(suits) > 4:
                suits = suits[:4]

            # 将"-"替换为空字符串（endplay不接受"-"）
            suits = ["" if suit == "-" else suit for suit in suits]

            pbn_hand = ".".join(suits)
            pbn_parts.append(pbn_hand)
        else:
            raise ValueError(f"缺少位置 {pos_cn} 的手牌")

    # 组合成完整的PBN字符串
    pbn_str = f"{dealer}:{' '.join(pbn_parts)}"
    return pbn_str


def convert_project_hand_to_endplay(hands: Dict) -> Deal:
    """
    将项目手牌格式转换为 endplay Deal 对象

    Args:
        hands: 项目手牌字典，键为 Position 枚举或字符串

    Returns:
        endplay Deal 对象
    """
    if not ENDPLAY_AVAILABLE:
        raise ImportError("endplay 库未安装")

    # 将手牌转换为字符串字典
    hands_dict = {}

    for key, hand in hands.items():
        if isinstance(key, Position):
            pos_name = key.value  # "南"、"西"、"北"、"东"
        else:
            pos_name = key

        if isinstance(hand, Hand):
            # Hand 对象转换为字符串（使用修复后的 to_simple_string）
            hand_str = hand.to_simple_string()
        elif isinstance(hand, str):
            hand_str = hand
        else:
            raise TypeError(f"不支持的手牌类型: {type(hand)}")

        hands_dict[pos_name] = hand_str

    # 转换为 PBN 格式
    pbn_str = convert_hand_to_pbn(hands_dict)

    # 创建 Deal 对象
    try:
        deal = Deal(pbn_str)
        return deal
    except Exception as e:
        raise ValueError(f"无法创建 Deal 对象: {e}\nPBN字符串: {pbn_str}")


def analyze_all_contracts_endplay(hands: Union[Dict, Deal], hcp_dict: Dict = None) -> Dict:
    """
    使用 endplay 分析所有玩家和将牌组合的最高可完成定约

    Args:
        hands: 手牌字典或 endplay Deal 对象
        hcp_dict: 可选的大牌点力字典，键为位置名称

    Returns:
        包含分析结果的字典
    """
    if not ENDPLAY_AVAILABLE:
        return {
            "success": False,
            "error": "endplay 库未安装，请运行: pip install endplay"
        }

    try:
        # 确保我们有 Deal 对象
        if isinstance(hands, Deal):
            deal = hands
        else:
            deal = convert_project_hand_to_endplay(hands)

        print("正在计算双明手表...")

        # 计算双明手表
        table = calc_dd_table(deal)
        table_list = table.to_list()

        print("双明手表计算完成")

        # 定义顺序映射
        declarer_order = ["北", "东", "南", "西"]
        trump_order = ["NT", "S", "H", "D", "C"]

        results = {}

        for i, declarer in enumerate(declarer_order):
            results[declarer] = {}
            for j, trump in enumerate(trump_order):
                tricks = table_list[j][i]

                max_level = 0
                for level in range(7, 0, -1):
                    required_tricks = 6 + level
                    if tricks >= required_tricks:
                        max_level = level
                        break

                results[declarer][trump] = {
                    "max_level": max_level,
                    "tricks": tricks,
                    "contract": f"{max_level}{trump}" if max_level > 0 else "无法完成"
                }

        return {
            "success": True,
            "deal": deal,
            "table": table_list,
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
    """
    格式化双明手分析结果

    Args:
        results: 分析结果字典
        hcp_dict: 可选的大牌点力字典

    Returns:
        格式化后的字符串
    """
    lines = []
    lines.append("\n" + "=" * 60)
    lines.append("双明手分析结果 - 最高可完成定约")
    lines.append("=" * 60)

    trump_display = {
        "C": "C",
        "D": "D",
        "H": "H",
        "S": "S",
        "NT": "NT"
    }

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
                    if trump == "NT":
                        table_data[trump][declarer] = f"{level}NT"
                    else:
                        table_data[trump][declarer] = f"{level}{trump}"
                else:
                    table_data[trump][declarer] = "-"
            else:
                table_data[trump][declarer] = "-"

    COLUMN_WIDTH = 6

    def pad_chinese(text, width):
        display_width = sum(2 if ord(c) > 127 else 1 for c in text)
        return text + " " * (width - display_width)

    header_line = ""
    for declarer in declarer_order:
        header_line += pad_chinese(declarer, COLUMN_WIDTH)
    lines.append(header_line)

    separator = ("-" * COLUMN_WIDTH) * len(declarer_order)
    lines.append(separator)

    for trump in trump_order:
        row_line = ""
        for declarer in declarer_order:
            content = table_data[trump].get(declarer, "-")
            row_line += pad_chinese(content, COLUMN_WIDTH)
        lines.append(row_line)

    lines.append("=" * 60)
    return "\n".join(lines)


def analyze_specific_contract(hands: Union[Dict, Deal], declarer: str, trump: str, level: int) -> Dict:
    """
    分析特定定约能否完成

    Args:
        hands: 手牌字典或 Deal 对象
        declarer: 庄家位置 ("南"、"西"、"北"、"东")
        trump: 将牌花色 ("C"、"D"、"H"、"S"、"NT")
        level: 定约阶数 (1-7)

    Returns:
        分析结果字典
    """
    if not ENDPLAY_AVAILABLE:
        return {"success": False, "error": "endplay 未安装"}

    try:
        # 确保有 Deal 对象
        if isinstance(hands, Deal):
            deal = hands
        else:
            deal = convert_project_hand_to_endplay(hands)

        # 转换参数为 endplay 类型
        from endplay.types import Denom, Player

        declarer_map = {"北": Player.north, "东": Player.east, "南": Player.south, "西": Player.west}
        trump_map = {"C": Denom.clubs, "D": Denom.diamonds, "H": Denom.hearts, "S": Denom.spades, "NT": Denom.nt}

        if declarer not in declarer_map:
            raise ValueError(f"无效的庄家位置: {declarer}")
        if trump not in trump_map:
            raise ValueError(f"无效的将牌花色: {trump}")

        # 使用 solve_board 函数分析特定定约
        # solve_board 已从 endplay.dds 导入

        result = solve_board(deal, trump_map[trump], declarer_map[declarer])

        # 解析结果
        required_tricks = 6 + level
        can_make = result.tricks >= required_tricks

        return {
            "success": True,
            "declarer": declarer,
            "trump": trump,
            "level": level,
            "contract": f"{level}{trump}",
            "tricks": result.tricks,
            "can_make": can_make,
            "overtricks": result.tricks - required_tricks if can_make else 0,
            "undertricks": required_tricks - result.tricks if not can_make else 0
        }

    except Exception as e:
        return {
            "success": False,
            "error": f"分析特定定约失败: {str(e)}"
        }


def main():
    """测试主函数"""
    if not ENDPLAY_AVAILABLE:
        print("请先安装 endplay: pip install endplay")
        return

    # 创建一个示例牌局
    example_hands = {
        "南": "AQJ5 KQJ8 765 43",
        "西": "K87 765 AKJ9 765",
        "北": "T9432 A32 T82 98",
        "东": "6 T94 Q43 AKQJT2"
    }

    print("测试 endplay 集成")
    print("=" * 60)
    print("\n示例牌局:")
    for pos, hand in example_hands.items():
        print(f"  {pos}: {hand}")

    print("\n" + "=" * 60)
    print("开始批量双明手分析...")

    result = analyze_all_contracts_endplay(example_hands)

    if result["success"]:
        print(result["formatted_output"])

        # 显示原始表格数据（如果可用）
        if "table" in result:
            print("\n原始双明手表数据:")
            table = result["table"]
            try:
                # 尝试以表格形式显示
                print("行: 庄家 (北、东、南、西)")
                print("列: 将牌 (NT、S、H、D、C)")
                for i in range(min(4, len(table))):
                    row = table[i]
                    row_str = " ".join(f"{tricks:2d}" for tricks in row[:5])
                    print(f"  行{i}: {row_str}")
            except:
                print(f"  表格数据结构: {type(table)}")
    else:
        print(f"分析失败: {result.get('error')}")
        if "traceback" in result:
            print(f"错误详情: {result['traceback']}")


if __name__ == "__main__":
    main()