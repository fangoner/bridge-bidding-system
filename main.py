#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
桥牌叫牌练习系统 - 命令行版本
"""

import sys
import os
from pathlib import Path
from typing import Dict, List, Optional, Tuple
from enum import Enum

sys.path.insert(0, str(Path(__file__).parent))

from bridge.dealer import BridgeDealer, Hand, Position, POSITION_ORDER, parse_deal_input, parse_hand_string, DealMode
from bridge.bidding import (
    extract_retrieval_keyword, 
    get_partner_position, 
    get_position_name,
    get_next_position,
    parse_bidding_sequence,
    parse_bidding_sequence_with_positions
)
from bridge.deep_finesse import analyze_with_deep_finesse, parse_contract_info, format_analysis_result, parse_df_deal, df_format_to_hand
from bridge.output_format import generate_graphic_output, generate_compact_output, generate_deep_finesse_output, generate_all_outputs
from bridge.bidding_service import BiddingService
from knowledge.loader import JFLoader, JFRetriever
from llm.prompts import BIDDING_SYSTEM_PROMPT, BIDDING_FALLBACK_PROMPT, HUMAN_BID_PROMPT
from llm.deepseek_client import DeepSeekClient
from llm.doubao_client import DoubaoVisionClient
from config import JF_CONVENTION_FILE, DEFAULT_DEAL_SYSTEM, SHOW_FULL_LLM_OUTPUT, OUTPUT_MODE_GRAPHIC, OUTPUT_MODE_COMPACT, OUTPUT_MODE_DEEP_FINESSE, OUTPUT_MODE_ALL, DEFAULT_OUTPUT_MODE, MAIN_PROMPT_TEMPERATURE, FALLBACK_PROMPT_TEMPERATURE
from utils.history import HistoryManager

# 导入双明手分析模块
try:
    from dd_analysis import analyze_all_contracts, format_dd_results
    DD_ANALYSIS_AVAILABLE = True
except ImportError:
    DD_ANALYSIS_AVAILABLE = False
    print("注意: dd_analysis 模块导入失败，批量双明手分析功能不可用")


class GameMode(Enum):
    PAIR = "双人叫牌"
    FOUR = "四人叫牌"


class BiddingGame:
    def __init__(self):
        self.hands: Dict[Position, Hand] = {}
        self.bidding_sequence: str = ""
        self.bid_meanings: str = ""
        self.dealer: Position = Position.SOUTH
        self.mode: GameMode = GameMode.PAIR
        self.human_position: Optional[Position] = None
        self.deal_system: str = DEFAULT_DEAL_SYSTEM
        self.output_mode: str = DEFAULT_OUTPUT_MODE
        self.df_format_output: str = ""
        self.model: str = "deepseek-v4-flash"
        
        self.jf_loader = JFLoader(JF_CONVENTION_FILE)
        self.jf_segments = self.jf_loader.load()
        self.jf_retriever = JFRetriever(self.jf_segments)
        
        self.llm_client = DeepSeekClient(model=self.model)
        self.vision_client = DoubaoVisionClient()
        self.history_manager = HistoryManager()

        self.bidding_service = BiddingService(self.llm_client, self.jf_retriever)
        
        self.current_bidder: Position = Position.SOUTH
        self.consecutive_passes: int = 0
        self.last_real_bid: str = ""
        self.use_fallback: bool = False
        self.bid_count: int = 0
        self.deal_mode: DealMode = DealMode.FREE
        self.passed_partnership: Optional[str] = None
    
    def deal(self):
        dealer = BridgeDealer(self.deal_mode)
        self.hands = dealer.deal()
        self.reset_bidding()
    
    def set_deal_mode(self, mode: DealMode):
        self.deal_mode = mode
    
    def reset_bidding(self):
        self.bidding_sequence = ""
        self.bid_meanings = ""
        self.consecutive_passes = 0
        self.last_real_bid = ""
        self.current_bidder = self.dealer
        self.use_fallback = False
        self.bid_count = 0
        self.passed_partnership = None
        self.bidding_service.reset()
    
    def set_dealer(self, dealer_name: str):
        dealer_map = {"南": Position.SOUTH, "西": Position.WEST, "北": Position.NORTH, "东": Position.EAST}
        self.dealer = dealer_map.get(dealer_name, Position.SOUTH)
    
    def set_mode(self, mode_str: str):
        if "双人" in mode_str:
            self.mode = GameMode.PAIR
        else:
            self.mode = GameMode.FOUR
    
    def set_human_position(self, position_name: str):
        if position_name == "无":
            self.human_position = None
        else:
            pos_map = {"南": Position.SOUTH, "西": Position.WEST, "北": Position.NORTH, "东": Position.EAST}
            self.human_position = pos_map.get(position_name)
    
    def set_deal_system(self, deal_system: str):
        self.deal_system = deal_system
    
    def get_active_positions(self) -> List[Position]:
        if self.mode == GameMode.FOUR:
            return list(POSITION_ORDER)
        else:
            dealer_name = get_position_name(self.dealer)
            if dealer_name in ["南", "北"]:
                return [Position.SOUTH, Position.NORTH]
            else:
                return [Position.EAST, Position.WEST]
    
    def is_active_position(self, pos: Position) -> bool:
        return pos in self.get_active_positions()
    
    def is_human_turn(self) -> bool:
        return self.human_position == self.current_bidder and self.is_active_position(self.current_bidder)
    
    def display_hands(self, show_all: bool = True):
        print("\n" + "=" * 60, flush=True)
        print("牌局分布", flush=True)
        print("=" * 60, flush=True)
        
        display_order = [Position.NORTH, Position.WEST, Position.SOUTH, Position.EAST]
        
        for position in display_order:
            hand = self.hands.get(position)
            if hand:
                pos_name = get_position_name(position)
                hcp = hand.hcp
                dist = hand.distribution
                display = hand.to_display_string()
                
                markers = []
                if position == self.dealer:
                    markers.append("发牌人")
                if position == self.human_position:
                    markers.append("人类")
                if not self.is_active_position(position):
                    markers.append("不参与")
                
                marker_str = f" [{', '.join(markers)}]" if markers else ""
                
                if show_all or self.is_active_position(position) or position == self.human_position:
                    print(f"\n{pos_name}{marker_str}: {display}", flush=True)
                    print(f"   HCP: {hcp}, 分布: {dist}", flush=True)
        
        print("\n" + "=" * 60, flush=True)
    
    def _get_bidding_str_for_keyword(self) -> str:
        bidding_str = self.bidding_sequence
        if self.mode == GameMode.PAIR and bidding_str:
            import re
            pos_order = ["南", "西", "北", "东"]
            last_pos_match = re.findall(r'\(([^)]+)\)', bidding_str)
            if last_pos_match:
                last_pos = last_pos_match[-1]
                current_bidder_name = get_position_name(self.current_bidder) if hasattr(self, 'current_bidder') else "北"
                last_idx = pos_order.index(last_pos) if last_pos in pos_order else 0
                current_idx = pos_order.index(current_bidder_name) if current_bidder_name in pos_order else 2
                while True:
                    last_idx = (last_idx + 1) % 4
                    if pos_order[last_idx] == current_bidder_name:
                        break
                    bidding_str += f"({pos_order[last_idx]})pass-"
        return bidding_str
    
    def ai_bid(self) -> Dict:
        current = self.current_bidder
        hand = self.hands[current]
        player_name = get_position_name(current)
        
        bidding_str_for_keyword = self._get_bidding_str_for_keyword()
        
        self.bidding_service.set_bid_meanings(self.bid_meanings)
        
        result = self.bidding_service.ai_bid(
            hand=hand,
            position=player_name,
            bidding_sequence=bidding_str_for_keyword,
            deal_system=self.deal_system,
            verbose=True
        )
        
        self.use_fallback = self.bidding_service.use_fallback
        
        return result
    
    def human_bid(self, user_input: str) -> Dict:
        player_name = get_position_name(self.current_bidder)
        
        result = self.bidding_service.human_bid(
            user_input=user_input,
            position=player_name,
            bidding_sequence=self.bidding_sequence,
            deal_system=self.deal_system,
            verbose=True
        )
        
        return result
    
    def process_bid(self, bid_result: Dict) -> str:
        bid_raw = bid_result.get("选定叫品", "pass").strip()
        
        bid = self._extract_bid(bid_raw)
        
        if bid == "p":
            bid = "pass"
        
        current = self.current_bidder
        player_name = get_position_name(current)
        self.bidding_sequence += f"({player_name}){bid}-"
        
        self.bid_count += 1
        
        if bid == "pass":
            self.consecutive_passes += 1
        else:
            self.consecutive_passes = 0
            self.last_real_bid = bid
        
        meaning = bid_result.get("叫品含义", "") or bid_result.get("叫品含义及后续建议", "")
        constraint = (bid_result.get("叫品约束", "") or "").strip()
        if meaning:
            current = self.current_bidder
            player_name = get_position_name(current)
            line = f"\n({player_name}){meaning}"
            if constraint:
                line += f"[约束:{constraint}]"
            self.bid_meanings += line
        
        return bid
    
    def _extract_bid(self, text: str) -> str:
        import re
        text = text.strip()
        
        patterns = [
            r'\b(pass)\b',
            r'\b(\d[CDHS])\b',
            r'\b(\dNT)\b',
            r'\b(X)\b',
            r'\b(XX)\b',
        ]
        
        for pattern in patterns:
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                bid = match.group(1).upper()
                if bid == "PASS":
                    return "pass"
                return bid
        
        if "pass" in text.lower():
            return "pass"
        
        return text.lower()
    
    def _extract_bidding_sequence(self, text: str) -> str:
        import re
        
        pattern = r'\([^)]+\)(?:pass|\d(?:C|D|H|S|NT)|X|XX)-'
        matches = re.findall(pattern, text, re.IGNORECASE)
        
        if matches:
            return ''.join(matches)
        
        return ""
    
    def advance_to_next_active_bidder(self):
        for _ in range(4):
            next_pos = get_next_position(self.current_bidder)
            pos_map = {"南": Position.SOUTH, "西": Position.WEST, "北": Position.NORTH, "东": Position.EAST}
            self.current_bidder = pos_map.get(next_pos, Position.SOUTH)
            
            if not self.is_active_position(self.current_bidder):
                if self.mode == GameMode.PAIR:
                    inactive_name = get_position_name(self.current_bidder)
                    self.bidding_sequence += f"({inactive_name})pass-"
            else:
                return
    
    def is_bidding_complete(self) -> bool:
        if not self.bidding_sequence:
            return False
        
        has_opening = self.last_real_bid != ""
        
        if self.mode == GameMode.PAIR:
            if has_opening and self.consecutive_passes >= 1:
                return True
            if self.consecutive_passes >= 2:
                return True
            return False
        else:
            if has_opening and self.consecutive_passes >= 3:
                return True
            if self.consecutive_passes >= 4:
                return True
            return False
    
    def check_partner_consecutive_pass(self, current_pos: Position, bid: str):
        """检查搭档两人是否相继pass（四人模式）"""
        if self.mode != GameMode.FOUR:
            return
        
        if bid.lower() != 'pass' or self.passed_partnership:
            return
        
        if not self.last_real_bid:
            return
        
        partnerships = {
            Position.SOUTH: Position.NORTH,
            Position.NORTH: Position.SOUTH,
            Position.EAST: Position.WEST,
            Position.WEST: Position.EAST
        }
        partnership_names = {
            Position.SOUTH: '南北',
            Position.NORTH: '南北',
            Position.EAST: '东西',
            Position.WEST: '东西'
        }
        
        partner = partnerships.get(current_pos)
        if not partner:
            return
        
        bids_list = self.bidding_sequence.rstrip('-').split('-') if self.bidding_sequence else []
        
        if len(bids_list) < 3:
            return
        
        partner_pass_idx = -1
        for i in range(len(bids_list) - 2, -1, -1):
            bid_item = bids_list[i]
            if f"({get_position_name(partner)})" in bid_item and "pass" in bid_item.lower():
                partner_pass_idx = i
                break
        
        if partner_pass_idx == -1:
            return
        
        bids_between = bids_list[partner_pass_idx + 1:-1]
        if len(bids_between) == 1:
            middle_bid = bids_between[0]
            middle_is_opponent = True
            for pos_name, pos in [("南", Position.SOUTH), ("西", Position.WEST), ("北", Position.NORTH), ("东", Position.EAST)]:
                if f"({pos_name})" in middle_bid:
                    if partnerships.get(pos) == partner:
                        middle_is_opponent = False
                    break
            
            if middle_is_opponent:
                self.passed_partnership = partnership_names[current_pos]
                print(f"  [提示] {get_position_name(current_pos)}和{get_position_name(partner)}相继pass，后续不再参与叫牌")
    
    def is_in_passed_partnership(self, pos: Position) -> bool:
        """检查位置是否属于已pass的搭档"""
        if not self.passed_partnership:
            return False
        
        partnership_positions = {
            '南北': [Position.SOUTH, Position.NORTH],
            '东西': [Position.EAST, Position.WEST]
        }
        
        return pos in partnership_positions.get(self.passed_partnership, [])
    
    def run_bidding_loop(self):
        if not self.hands:
            print("请先发牌或输入牌局")
            return
        
        self.display_hands(show_all=True)
        
        print(f"\n开始叫牌 - 模式: {self.mode.value}")
        print(f"发牌人: {get_position_name(self.dealer)}")
        active = [get_position_name(p) for p in self.get_active_positions()]
        print(f"参与叫牌: {', '.join(active)}")
        if self.human_position:
            print(f"人类位置: {get_position_name(self.human_position)}")
        else:
            print("人类位置: 无（观察模式）")
        
        print("\n" + "-" * 60)
        
        self.reset_bidding()
        self.current_bidder = self.dealer
        
        while not self.is_active_position(self.current_bidder):
            inactive_name = get_position_name(self.current_bidder)
            self.bidding_sequence += f"({inactive_name})pass-"
            next_pos = get_next_position(self.current_bidder)
            pos_map = {"南": Position.SOUTH, "西": Position.WEST, "北": Position.NORTH, "东": Position.EAST}
            self.current_bidder = pos_map.get(next_pos, Position.SOUTH)
        
        while not self.is_bidding_complete():
            current = self.current_bidder
            player_name = get_position_name(current)
            hand = self.hands[current]
            
            if self.is_in_passed_partnership(current):
                print(f"\n{player_name}自动pass（搭档已相继pass）")
                self.bidding_sequence += f"({player_name})pass-"
                self.bid_meanings += f"\n({player_name})搭档已相继pass，不再参与叫牌"
                self.consecutive_passes += 1
                self.advance_to_next_active_bidder()
                continue
            
            if self.is_human_turn():
                print(f"\n{'='*40}")
                print(f"轮到你叫牌 ({player_name})")
                print(f"{'='*40}")
                print(f"你的手牌: {hand.to_display_string()}")
                print(f"HCP: {hand.hcp}, 分布: {hand.distribution}")
                print(f"当前叫牌序列: {self.bidding_sequence if self.bidding_sequence else '空'}")
                
                user_input = input("\n请输入叫牌 (如 1C, pass, X, 2NT 等, 输入q退出): ").strip()
                
                if user_input.lower() in ["q", "quit", "exit"]:
                    print("退出叫牌")
                    break
                
                bid_result = self.human_bid(user_input)
                
                if "error" in bid_result:
                    print(f"处理出错: {bid_result['error']}")
                    continue
                
                bid = self.process_bid(bid_result)
                print(f"\n你的叫牌: {bid}")
                
                if bid_result.get("叫品含义及后续建议"):
                    print(f"叫品含义: {bid_result['叫品含义及后续建议'][:200]}...")
                
                self.check_partner_consecutive_pass(current, bid)
            else:
                print(f"\n{player_name}正在思考...")
                
                bid_result = self.ai_bid()
                
                if "error" in bid_result:
                    print(f"AI思考出错: {bid_result['error']}")
                    bid_result = {"选定叫品": "pass"}
                
                bid = self.process_bid(bid_result)
                
                print(f"{player_name}叫: {bid}")
                
                if SHOW_FULL_LLM_OUTPUT:
                    print("\n--- LLM完整输出 ---")
                    for key, value in bid_result.items():
                        if key not in ["error", "raw_response"]:
                            print(f"{key}: {value}")
                    print("--- 输出结束 ---\n")
                else:
                    if bid_result.get("手牌分析"):
                        analysis = bid_result['手牌分析']
                        if len(analysis) > 100:
                            analysis = analysis[:100] + "..."
                        print(f"  分析: {analysis}")
                
                self.check_partner_consecutive_pass(current, bid)
            
            self.advance_to_next_active_bidder()
        
        self.bidding_sequence = self.bidding_sequence.rstrip("-")
        
        print("\n" + "=" * 60, flush=True)
        print("叫牌结束!", flush=True)
        print(f"最终叫牌序列: {self.bidding_sequence}", flush=True)
        print("=" * 60, flush=True)
        
        self.display_final_result()
        self._auto_save_history()
    
    def _auto_save_history(self):
        try:
            if not self.hands:
                return
                
            hands_dict = {
                "北": self.hands[Position.NORTH].to_display_string(),
                "西": self.hands[Position.WEST].to_display_string(),
                "南": self.hands[Position.SOUTH].to_display_string(),
                "东": self.hands[Position.EAST].to_display_string()
            }
            
            final_contract = self._get_final_contract()
            
            mode_value = self.mode.value if self.mode else "pair"
            
            bid_meaning_str = ""
            if self.bid_meanings:
                import re
                bid_meaning_str = self.bid_meanings
                bid_meaning_str = re.sub(r'1\.\s*\*{0,2}叫品含义\*{0,2}[：:]\s*', '', bid_meaning_str)
                bid_meaning_str = re.sub(r'\n?2\.\s*\*{0,2}后续建议\*{0,2}[：:].*?(?=\n\(|$)', '', bid_meaning_str, flags=re.DOTALL)
                bid_meaning_str = re.sub(r'\n\s*\n', '\n', bid_meaning_str).strip()
            
            record = self.history_manager.add_record(
                hands=hands_dict,
                bidding_sequence=self.bidding_sequence,
                final_contract=final_contract,
                declarer=get_position_name(self.dealer),
                mode=mode_value,
                human_position=get_position_name(self.human_position) if self.human_position else None,
                bid_meaning=bid_meaning_str,
                note=""
            )
            print(f"\n已自动保存! 记录ID: {record.id}", flush=True)
        except Exception as e:
            import traceback
            print(f"自动保存失败: {e}", flush=True)
            traceback.print_exc()
    
    def _ask_save_history(self):
        print("\n是否保存此牌局到历史记录？", flush=True)
        save = input("(y/n): ").strip().lower()
        if save == 'y':
            note = input("请输入备注（可选，直接回车跳过）: ").strip()
            
            try:
                if not self.hands:
                    print("保存失败: 手牌数据为空", flush=True)
                    return
                
                hands_dict = {
                    "北": self.hands[Position.NORTH].to_display_string(),
                    "西": self.hands[Position.WEST].to_display_string(),
                    "南": self.hands[Position.SOUTH].to_display_string(),
                    "东": self.hands[Position.EAST].to_display_string()
                }
                
                final_contract = self._get_final_contract()
                
                mode_value = self.mode.value if self.mode else "pair"
                
                bid_meaning_str = ""
                if self.bid_meanings:
                    import re
                    bid_meaning_str = self.bid_meanings
                    bid_meaning_str = re.sub(r'1\.\s*\*{0,2}叫品含义\*{0,2}[：:]\s*', '', bid_meaning_str)
                    bid_meaning_str = re.sub(r'\n?2\.\s*\*{0,2}后续建议\*{0,2}[：:].*?(?=\n\(|$)', '', bid_meaning_str, flags=re.DOTALL)
                    bid_meaning_str = re.sub(r'\n\s*\n', '\n', bid_meaning_str).strip()
                
                record = self.history_manager.add_record(
                    hands=hands_dict,
                    bidding_sequence=self.bidding_sequence,
                    final_contract=final_contract,
                    declarer=get_position_name(self.dealer),
                    mode=mode_value,
                    human_position=get_position_name(self.human_position) if self.human_position else None,
                    bid_meaning=bid_meaning_str,
                    note=note
                )
                print(f"已保存! 记录ID: {record.id}", flush=True)
            except Exception as e:
                import traceback
                print(f"保存失败: {e}", flush=True)
                traceback.print_exc()
    
    def _get_final_contract(self) -> str:
        if not self.bidding_sequence:
            return "Pass Out"
        
        bids = parse_bidding_sequence_with_positions(self.bidding_sequence)
        if not bids:
            return "Pass Out"
        
        last_bid = "pass"
        for pos, bid in reversed(bids):
            if bid.lower() not in ["pass", "p", "x", "xx"]:
                last_bid = bid
                break
        
        if last_bid.lower() in ["pass", "p"]:
            return "Pass Out"
        return last_bid
    
    def display_final_result(self):
        print("\n正在生成格式化输出...", flush=True)
        
        try:
            graphic, compact, df_format = generate_all_outputs(
                hands=self.hands,
                bidding_str=self.bidding_sequence,
                dealer=self.dealer,
                mode=self.mode.value,
                human_position=self.human_position
            )
            
            self.df_format_output = df_format
            
            if self.output_mode == OUTPUT_MODE_ALL:
                print("\n" + "=" * 60, flush=True)
                print("【图形化布局】", flush=True)
                print(graphic, flush=True)
                if self.bid_meanings:
                    import re
                    display_meanings = self.bid_meanings
                    display_meanings = re.sub(r'1\.\s*\*{0,2}叫品含义\*{0,2}[：:]\s*', '', display_meanings)
                    display_meanings = re.sub(r'\n?2\.\s*\*{0,2}后续建议\*{0,2}[：:].*?(?=\n\(|$)', '', display_meanings, flags=re.DOTALL)
                    display_meanings = re.sub(r'\n\s*\n', '\n', display_meanings).strip()
                    print("\n【叫牌含义】", flush=True)
                    print(display_meanings, flush=True)
                print("\n【紧凑型布局】", flush=True)
                print(compact, flush=True)
                print("\n【Deep Finesse格式】", flush=True)
                print(df_format, flush=True)
                print("=" * 60, flush=True)
            elif self.output_mode == OUTPUT_MODE_GRAPHIC:
                print("\n" + "=" * 60, flush=True)
                print(graphic, flush=True)
                if self.bid_meanings:
                    import re
                    display_meanings = self.bid_meanings
                    display_meanings = re.sub(r'1\.\s*\*{0,2}叫品含义\*{0,2}[：:]\s*', '', display_meanings)
                    display_meanings = re.sub(r'\n?2\.\s*\*{0,2}后续建议\*{0,2}[：:].*?(?=\n\(|$)', '', display_meanings, flags=re.DOTALL)
                    display_meanings = re.sub(r'\n\s*\n', '\n', display_meanings).strip()
                    print("\n【叫牌含义】", flush=True)
                    print(display_meanings, flush=True)
                print("=" * 60, flush=True)
            elif self.output_mode == OUTPUT_MODE_COMPACT:
                print("\n" + "=" * 60, flush=True)
                print(compact, flush=True)
                print("=" * 60, flush=True)
            elif self.output_mode == OUTPUT_MODE_DEEP_FINESSE:
                print("\n" + "=" * 60, flush=True)
                print(df_format, flush=True)
                print("=" * 60, flush=True)
            else:
                print("\n" + "=" * 60, flush=True)
                print(graphic, flush=True)
                print("=" * 60, flush=True)
                
        except Exception as e:
            print(f"生成格式化输出失败: {e}", flush=True)
            import traceback
            traceback.print_exc()


def print_menu():
    print("\n" + "=" * 60, flush=True)
    print("桥牌叫牌练习系统", flush=True)
    print("=" * 60, flush=True)
    print("1. 发牌/输入牌局", flush=True)
    print("2. 设置", flush=True)
    print("3. 显示当前牌局", flush=True)
    print("4. 开始叫牌", flush=True)
    print("5. 定约分析", flush=True)
    print("6. 记录/查看历史记录", flush=True)
    print("7. 测试叫牌序列关键词和预处理", flush=True)
    print("8. 重新加载约定片段", flush=True)
    print("0. 退出", flush=True)
    print("=" * 60, flush=True)


def select_deal_and_start(game: BiddingGame):
    print("\n发牌方式:")
    print("1. 自动发牌")
    print("2. 输入自定义牌局")
    print("3. 从图片读取牌局")
    print("0. 返回")
    choice = input("请选择: ").strip()
    
    if choice == "1":
        print("\n发牌模式:")
        print("1. 自由发牌")
        print("2. 进局实力")
        print("3. 满贯实力")
        mode_choice = input("请选择发牌模式: ").strip()
        
        if mode_choice == "2":
            game.set_deal_mode(DealMode.GAME)
        elif mode_choice == "3":
            game.set_deal_mode(DealMode.SLAM)
        else:
            game.set_deal_mode(DealMode.FREE)
        
        game.deal()
        game.display_hands()
    elif choice == "2":
        input_custom_deal(game)
    elif choice == "3":
        read_cards_from_image(game)
    elif choice == "0":
        return


def view_history(game: BiddingGame):
    records = game.history_manager.get_all_records()
    result_message = []
    
    while True:
        # 先显示记录清单
        print("\n" + "=" * 60, flush=True)
        print("历史记录管理", flush=True)
        print("=" * 60, flush=True)
        
        if records:
            print("\n记录清单:", flush=True)
            for i, record in enumerate(records[:20], 1):
                print(game.history_manager.format_record_summary(record, i), flush=True)
            
            if len(records) > 20:
                print(f"\n... 共 {len(records)} 条记录，仅显示前 20 条", flush=True)
        else:
            print("\n暂无历史记录", flush=True)
        
        # 如果有操作结果，显示在记录清单后面
        if result_message:
            print("\n" + "-" * 60, flush=True)
            print("操作结果", flush=True)
            print("-" * 60, flush=True)
            for msg in result_message:
                print(msg, flush=True)
            print("-" * 60, flush=True)
            result_message = []  # 清空结果
        
        # 显示操作选项
        print("\n操作选项:", flush=True)
        print("  编号    - 查看详情（如输入 1）", flush=True)
        print("  d+编号  - 删除记录（如 d1）", flush=True)
        print("  l+编号  - 加载牌局（如 l1）", flush=True)
        print("  e+编号  - 编辑注释（如 e1）", flush=True)
        print("  n       - 显示有注释的记录", flush=True)
        print("  h       - 隐藏有注释的记录（只显示无注释）", flush=True)
        print("  k+关键词 - 搜索注释（如 k 满贯）", flush=True)
        print("  b       - 批量删除无注释的记录", flush=True)
        print("  s       - 保存当前牌局", flush=True)
        print("  c       - 清空所有记录", flush=True)
        print("  0       - 返回", flush=True)
        
        choice = input("\n请选择：").strip().lower()
        
        if choice == "0":
            return
        elif choice == "n":
            noted_records = [r for r in records if r.note]
            if noted_records:
                result_message.append("\n有注释的记录:")
                for i, record in enumerate(noted_records[:20], 1):
                    orig_idx = records.index(record) + 1
                    result_message.append(f"  [{orig_idx}] {record.timestamp} | {record.final_contract} | {record.note[:30]}{'...' if len(record.note) > 30 else ''}")
                if len(noted_records) > 20:
                    result_message.append(f"\n... 共 {len(noted_records)} 条有注释的记录，仅显示前 20 条")
            else:
                result_message.append("\n没有带注释的记录")
        elif choice == "h":
            no_note_records = [r for r in records if not r.note]
            if no_note_records:
                result_message.append("\n无注释的记录:")
                for i, record in enumerate(no_note_records[:20], 1):
                    orig_idx = records.index(record) + 1
                    result_message.append(f"  [{orig_idx}] {record.timestamp} | {record.final_contract} | {record.bidding_sequence[:30]}{'...' if len(record.bidding_sequence) > 30 else ''}")
                if len(no_note_records) > 20:
                    result_message.append(f"\n... 共 {len(no_note_records)} 条无注释的记录，仅显示前 20 条")
            else:
                result_message.append("\n所有记录都有注释")
        elif choice == "b":
            no_note_records = [r for r in records if not r.note]
            if not no_note_records:
                result_message.append("\n所有记录都有注释，无需删除")
            else:
                result_message.append(f"\n找到 {len(no_note_records)} 条无注释的记录:")
                for i, record in enumerate(no_note_records[:10], 1):
                    orig_idx = records.index(record) + 1
                    result_message.append(f"  [{orig_idx}] {record.timestamp} | {record.final_contract}")
                if len(no_note_records) > 10:
                    result_message.append(f"  ... 共 {len(no_note_records)} 条")
                confirm = input(f"\n确认批量删除这 {len(no_note_records)} 条无注释的记录？(y/n): ").strip().lower()
                if confirm == 'y':
                    deleted_count = 0
                    for record in no_note_records:
                        if game.history_manager.delete_record(record.id):
                            deleted_count += 1
                    records = game.history_manager.get_all_records()
                    result_message.append(f"\n已删除 {deleted_count} 条无注释的记录")
                else:
                    result_message.append("已取消")
        elif choice.startswith('k'):
            if not records:
                result_message.append("暂无历史记录")
            else:
                keyword = choice[1:].strip()
                if not keyword:
                    result_message.append("请输入关键词，格式：k+关键词（如 k 满贯）")
                else:
                    matched_records = [r for r in records if r.note and keyword in r.note]
                    if matched_records:
                        result_message.append(f"\n包含关键词'{keyword}'的记录:")
                        for i, record in enumerate(matched_records[:20], 1):
                            orig_idx = records.index(record) + 1
                            note_preview = record.note
                            if keyword in note_preview:
                                idx = note_preview.find(keyword)
                                start = max(0, idx - 10)
                                end = min(len(note_preview), idx + len(keyword) + 20)
                                note_preview = ('...' if start > 0 else '') + note_preview[start:end] + ('...' if end < len(note_preview) else '')
                            result_message.append(f"  [{orig_idx}] {record.timestamp} | {record.final_contract} | {note_preview}")
                        if len(matched_records) > 20:
                            result_message.append(f"\n... 共 {len(matched_records)} 条匹配记录，仅显示前 20 条")
                    else:
                        result_message.append(f"\n没有找到包含关键词'{keyword}'的注释")
        elif choice == "s":
            if game.hands:
                game._ask_save_history()
            else:
                result_message.append("当前没有牌局，请先发牌或输入牌局")
        elif choice == "c":
            if not records:
                result_message.append("暂无历史记录")
            else:
                confirm = input("确认清空所有历史记录？(y/n): ").strip().lower()
                if confirm == 'y':
                    game.history_manager.clear_all()
                    records = []
                    result_message.append("已清空所有历史记录")
        elif choice.startswith('d'):
            if not records:
                result_message.append("暂无历史记录")
            else:
                try:
                    idx = int(choice[1:]) - 1
                    if 0 <= idx < len(records):
                        record = records[idx]
                        confirm = input(f"确认删除记录 [{idx+1}]？(y/n): ").strip().lower()
                        if confirm == 'y':
                            if game.history_manager.delete_record(record.id):
                                records = game.history_manager.get_all_records()
                                result_message.append(f"已删除记录 [{idx+1}]")
                            else:
                                result_message.append("删除失败")
                        else:
                            result_message.append("已取消")
                    else:
                        result_message.append("无效的记录编号")
                except ValueError:
                    result_message.append("无效输入，格式应为 d+编号（如 d1）")
        elif choice.startswith('e'):
            if not records:
                result_message.append("暂无历史记录")
            else:
                try:
                    idx = int(choice[1:]) - 1
                    if 0 <= idx < len(records):
                        record = records[idx]
                        result_message.append(f"\n当前注释：{record.note if record.note else '(无)'}")
                        new_note = input("请输入新注释（直接回车保持不变）: ").strip()
                        if new_note:
                            if game.history_manager.update_note(record.id, new_note):
                                records = game.history_manager.get_all_records()
                                result_message.append(f"已更新记录 [{idx+1}] 的注释")
                            else:
                                result_message.append("更新失败")
                        else:
                            result_message.append("已取消")
                    else:
                        result_message.append("无效的记录编号")
                except ValueError:
                    result_message.append("无效输入，格式应为 e+编号（如 e1）")
        elif choice.startswith('l'):
            if not records:
                result_message.append("暂无历史记录")
            else:
                try:
                    idx = int(choice[1:]) - 1
                    if 0 <= idx < len(records):
                        record = records[idx]
                        hands = {}
                        for pos_name, hand_str in record.hands.items():
                            pos_map = {"北": Position.NORTH, "西": Position.WEST, "南": Position.SOUTH, "东": Position.EAST}
                            if pos_name in pos_map:
                                hands[pos_map[pos_name]] = parse_hand_string(hand_str.replace("♠", " ").replace("♥", " ").replace("♦", " ").replace("♣", " "))
                        
                        if len(hands) == 4:
                            game.hands = hands
                            game.reset_bidding()
                            game.bidding_sequence = record.bidding_sequence
                            # 恢复叫牌设置
                            if record.mode:
                                game.mode = GameMode(record.mode) if record.mode in ["双人叫牌", "四人叫牌"] else GameMode.PAIR
                            if record.human_position:
                                pos_map = {"北": Position.NORTH, "西": Position.WEST, "南": Position.SOUTH, "东": Position.EAST}
                                game.human_position = pos_map.get(record.human_position)
                            # 恢复发牌人位置
                            if record.declarer:
                                pos_map = {"北": Position.NORTH, "西": Position.WEST, "南": Position.SOUTH, "东": Position.EAST}
                                game.dealer = pos_map.get(record.declarer, Position.SOUTH)
                            result_message.append(f"\n已加载牌局 [{idx+1}]")
                            result_message.append(f"叫牌序列：{record.bidding_sequence}")
                            if record.mode:
                                result_message.append(f"叫牌模式：{record.mode}")
                            if record.human_position:
                                result_message.append(f"人类玩家：{record.human_position}")
                            if record.bid_meaning:
                                import re
                                bid_meaning_display = record.bid_meaning
                                bid_meaning_display = re.sub(r'1\.\s*\*{0,2}叫品含义\*{0,2}[：:]\s*', '', bid_meaning_display)
                                bid_meaning_display = re.sub(r'\n?2\.\s*\*{0,2}后续建议\*{0,2}[：:].*?(?=\n\(|$)', '', bid_meaning_display, flags=re.DOTALL)
                                bid_meaning_display = re.sub(r'\n\s*\n', '\n', bid_meaning_display).strip()
                                result_message.append("\n叫牌历史:")
                                result_message.append(bid_meaning_display)
                        else:
                            result_message.append("牌局加载失败")
                    else:
                        result_message.append("无效的记录编号")
                except ValueError:
                    result_message.append("无效输入，格式应为 l+编号（如 l1）")
        elif choice.isdigit():
            if not records:
                result_message.append("暂无历史记录")
            else:
                try:
                    idx = int(choice) - 1
                    if 0 <= idx < len(records):
                        record = records[idx]
                        result_message.append("\n" + game.history_manager.format_record_detail(record))
                    else:
                        result_message.append("无效的记录编号")
                except ValueError:
                    result_message.append("无效输入")
        else:
            result_message.append("无效选择，请重试")

def reload_jf_segments(game: BiddingGame):
    try:
        game.jf_segments = game.jf_loader.load()
        game.jf_retriever = JFRetriever(game.jf_segments)
        print(f"约定片段已重新加载，共 {len(game.jf_segments)} 条")
    except Exception as e:
        print(f"加载失败: {e}")

def test_bidding_sequence(game: BiddingGame):
    from knowledge.loader import JFLoader, preprocess_jf_content
    from bridge.bidding import extract_retrieval_keyword
    import json
    
    while True:
        print("\n" + "=" * 60, flush=True)
        print("测试叫牌序列关键词和预处理", flush=True)
        print("=" * 60, flush=True)
        print("输入叫牌序列（格式如：(南)1D-(西)pass-(北)1S-(东)pass-）", flush=True)
        print("输入 'q' 返回", flush=True)
        
        bidding_sequence = input("\n请输入叫牌序列: ").strip()
        
        if bidding_sequence.lower() == 'q':
            return
        
        if not bidding_sequence:
            print("输入不能为空", flush=True)
            continue
        
        print(f"\n{'=' * 60}", flush=True)
        print(f"叫牌序列: {bidding_sequence}", flush=True)
        print('=' * 60, flush=True)
        
        keyword = extract_retrieval_keyword(bidding_sequence)
        print(f"\nextract_retrieval_keyword提取的关键词: {keyword}", flush=True)
        
        found = False
        for i, segment in enumerate(game.jf_segments, 1):
            keywords = segment.get('keywords', [])
            content = segment.get('content', '')
            
            for k in keywords:
                if k == keyword:
                    print(f"\n{'=' * 60}", flush=True)
                    print(f"找到匹配的段落 {i}", flush=True)
                    print(f"关键词: {keywords}", flush=True)
                    print('=' * 60, flush=True)
                    print(f"内容:\n{content}", flush=True)
                    
                    result = preprocess_jf_content(content, bidding_sequence, partner_name="北", keyword=keyword)
                    
                    print(f"\n{'=' * 60}", flush=True)
                    print(f"【预处理结果】", flush=True)
                    print(f"队友叫品: {result['partner_bid']}", flush=True)
                    print(f"是否结构性约定: {result['is_structural_convention']}", flush=True)
                    print(f"后续叫品数量: {len(result['subsequent_bids'])}", flush=True)
                    
                    print(f"\n【后续叫品】", flush=True)
                    if result['subsequent_bids']:
                        for j, bid_info in enumerate(result['subsequent_bids'], 1):
                            print(f"{j}. 【{bid_info['bid']}】{bid_info['line'][:100]}{'...' if len(bid_info['line']) > 100 else ''}", flush=True)
                    else:
                        print("无后续叫品", flush=True)
                    
                    print(f"\n{'=' * 60}", flush=True)
                    print(f"【完整JSON】", flush=True)
                    print(json.dumps(result, ensure_ascii=False, indent=2), flush=True)
                    
                    found = True
                    break
            
            if found:
                break
        
        if not found:
            print(f"\n未找到关键词 '{keyword}' 对应的JF约定段落", flush=True)


def select_settings(game: BiddingGame):
    while True:
        print("\n设置选项:")
        print("1. 叫牌模式（双人/四人）")
        print("2. 发牌人位置")
        print("3. 人类叫牌位置")
        print("4. 二阶开叫方案")
        print("5. LLM输出详细模式")
        print("6. 最终输出格式")
        print("7. AI设置")
        print("0. 返回")
        choice = input("请选择: ").strip()
        
        if choice == "1":
            select_mode(game)
        elif choice == "2":
            select_dealer(game)
        elif choice == "3":
            select_human_position(game)
        elif choice == "4":
            select_deal_system(game)
        elif choice == "5":
            global SHOW_FULL_LLM_OUTPUT
            SHOW_FULL_LLM_OUTPUT = not SHOW_FULL_LLM_OUTPUT
            status = "开启" if SHOW_FULL_LLM_OUTPUT else "关闭"
            print(f"LLM输出详细模式已{status}")
        elif choice == "6":
            select_output_mode(game)
        elif choice == "7":
            select_ai_settings(game)
        elif choice == "0":
            return


def select_mode(game: BiddingGame):
    print("\n选择叫牌模式:")
    print("1. 双人叫牌（搭档双方参与，另一方自动pass）")
    print("2. 四人叫牌（四家都参与叫牌）")
    choice = input("请选择 (1/2): ").strip()
    if choice == "1":
        game.set_mode("双人叫牌")
        print("已设置为双人叫牌模式")
        print("提示: 发牌人位置决定哪对搭档参与叫牌")
        print("  - 发牌人为南或北 → 南北方叫牌")
        print("  - 发牌人为东或西 → 东西方叫牌")
    elif choice == "2":
        game.set_mode("四人叫牌")
        print("已设置为四人叫牌模式")


def select_dealer(game: BiddingGame):
    print("\n选择发牌人位置:")
    print("1. 南")
    print("2. 西")
    print("3. 北")
    print("4. 东")
    choice = input("请选择 (1/2/3/4): ").strip()
    dealer_map = {"1": "南", "2": "西", "3": "北", "4": "东"}
    if choice in dealer_map:
        game.set_dealer(dealer_map[choice])
        print(f"发牌人已设置为: {dealer_map[choice]}")


def select_human_position(game: BiddingGame):
    print("\n选择人类叫牌位置:")
    print("0. 无（AI自动叫牌，观察模式）")
    print("1. 南")
    print("2. 西")
    print("3. 北")
    print("4. 东")
    choice = input("请选择 (0/1/2/3/4): ").strip()
    pos_map = {"0": "无", "1": "南", "2": "西", "3": "北", "4": "东"}
    if choice in pos_map:
        game.set_human_position(pos_map[choice])
        print(f"人类叫牌位置已设置为: {pos_map[choice]}")


def select_deal_system(game: BiddingGame):
    print("\n选择二阶开叫方案:")
    print("1. 2D：多功能，2H/S：麦德伯格，2NT：双低花")
    print("2. 2D/2H/2S：自然阻击")
    choice = input("请选择 (1/2): ").strip()
    system_map = {
        "1": "2D：多功能，2H/S：麦德伯格，2NT：双低花",
        "2": "自然阻击"
    }
    if choice in system_map:
        game.set_deal_system(system_map[choice])
        print(f"二阶开叫方案已设置为: {system_map[choice]}")


def input_custom_deal(game: BiddingGame):
    print("\n请输入牌局（支持两种格式）：")
    print("格式1 - 标准格式（按南西北东顺序，每行一家）：")
    print("K85 AT863 Q42 63")
    print("J73 72 8763 T954")
    print("QT94 5 KJT AQJ72")
    print("A62 KQJ94 A95 K8")
    print("\n格式2 - Deep Finesse格式：")
    print("Deal: 1                                - AK865 K76 KJ962")
    print("Contract: 5D-South     QT9754 94 95 A53                  AKJ3 QJ732 T4 T7")
    print("OnLead: East                    862 T AQJ832 Q84")
    print("Lead: SA")
    print("\n输入完成后按回车两次结束:")
    
    lines = []
    while True:
        line = input()
        if not line.strip():
            break
        lines.append(line)
    
    input_text = "\n".join(lines)
    
    if any(line.strip().startswith("Deal:") for line in lines):
        df_result = parse_df_deal(input_text)
        if df_result.get("north") or df_result.get("south"):
            hands = {}
            
            if df_result.get("north"):
                hands[Position.NORTH] = parse_hand_string(df_format_to_hand(df_result["north"]))
            if df_result.get("west"):
                hands[Position.WEST] = parse_hand_string(df_format_to_hand(df_result["west"]))
            if df_result.get("east"):
                hands[Position.EAST] = parse_hand_string(df_format_to_hand(df_result["east"]))
            if df_result.get("south"):
                hands[Position.SOUTH] = parse_hand_string(df_format_to_hand(df_result["south"]))
            
            if len(hands) == 4:
                game.hands = hands
                game.reset_bidding()
                print("牌局已加载（Deep Finesse格式）")
                game.display_hands()
            else:
                print(f"牌局解析不完整，缺少 {4 - len(hands)} 家手牌")
        else:
            print("Deep Finesse格式解析失败，请检查格式")
    elif len(lines) == 4:
        hands = parse_deal_input(input_text)
        if hands:
            game.hands = hands
            game.reset_bidding()
            print("牌局已加载")
            game.display_hands()
        else:
            print("牌局解析失败，请检查格式")
    else:
        print(f"需要输入4行标准格式或Deep Finesse格式，当前输入了{len(lines)}行")


def convert_10_to_T(hand_str: str) -> str:
    import re
    result = re.sub(r'([♠♥♦♣])10', r'\1T', hand_str)
    result = re.sub(r'([♠♥♦♣SsHhDdCc])10', r'\1T', result)
    result = result.replace('10', 'T')
    return result


def validate_hands(hands: Dict[Position, Hand]) -> List[str]:
    errors = []
    
    all_cards = []
    suit_counts = {'S': 0, 'H': 0, 'D': 0, 'C': 0}
    
    for pos, hand in hands.items():
        for suit_name, suit_cards in [('S', hand.spades), ('H', hand.hearts), ('D', hand.diamonds), ('C', hand.clubs)]:
            for card in suit_cards:
                all_cards.append(f"{suit_name}{card}")
                suit_counts[suit_name] += 1
    
    if len(all_cards) != 52:
        errors.append(f"牌张总数错误: 应为52张，实际{len(all_cards)}张")
    
    card_set = set(all_cards)
    if len(card_set) != len(all_cards):
        duplicates = [c for c in card_set if all_cards.count(c) > 1]
        errors.append(f"存在重复牌张: {duplicates}")
    
    expected_suit_count = 13
    for suit, count in suit_counts.items():
        if count != expected_suit_count:
            suit_names = {'S': '黑桃', 'H': '红心', 'D': '方块', 'C': '梅花'}
            errors.append(f"{suit_names[suit]}牌张数错误: 应为13张，实际{count}张")
    
    return errors


def read_cards_from_image(game: BiddingGame):
    print("\n从图片读取牌局")
    print("请输入图片文件路径（支持 jpg/png/gif/webp 格式）:")
    
    image_path = input().strip()
    
    if not image_path:
        print("未输入路径，已取消")
        return
    
    image_path = image_path.strip('"\'')
    
    if not os.path.exists(image_path):
        print(f"文件不存在: {image_path}")
        return
    
    print("正在识别图片...")
    
    result = game.vision_client.read_cards_from_image(image_path)
    
    if "error" in result:
        print(f"识别失败: {result['error']}")
        if "raw_response" in result:
            print(f"原始响应: {result['raw_response']}")
        return
    
    print("\n识别结果:")
    print(f"南家: {result.get('南家手牌', 'N/A')}")
    print(f"西家: {result.get('西家手牌', 'N/A')}")
    print(f"北家: {result.get('北家手牌', 'N/A')}")
    print(f"东家: {result.get('东家手牌', 'N/A')}")
    
    bidding = result.get("叫牌序列")
    if bidding and bidding != "null":
        if isinstance(bidding, list):
            formatted_bids = []
            for item in bidding:
                if ":" in item:
                    pos, bid = item.split(":", 1)
                    formatted_bids.append(f"（{pos}）{bid}")
                else:
                    formatted_bids.append(item)
            print(f"\n叫牌序列: {'-'.join(formatted_bids)}-")
        else:
            print(f"\n叫牌序列: {bidding}")
    
    contract = result.get("当前定约")
    if contract and contract != "null":
        print(f"当前定约: {contract}")
    
    page_type = result.get("页面类型", "未知")
    print(f"页面类型: {page_type}")
    
    confirm = input("\n确认使用此牌局？(y/n): ").strip().lower()
    if confirm == 'y':
        hands_text = "\n".join([
            convert_10_to_T(result.get('南家手牌', '')),
            convert_10_to_T(result.get('西家手牌', '')),
            convert_10_to_T(result.get('北家手牌', '')),
            convert_10_to_T(result.get('东家手牌', ''))
        ])
        
        hands = parse_deal_input(hands_text)
        if hands:
            errors = validate_hands(hands)
            if errors:
                print("\n⚠️ 牌张校验错误:")
                for err in errors:
                    print(f"  - {err}")
            
            game.hands = hands
            game.reset_bidding()
            print("牌局已加载")
            game.display_hands()
        else:
            print("牌局解析失败，请检查识别结果")
    else:
        print("已取消")


def select_output_mode(game: BiddingGame):
    print("\n选择最终输出格式:")
    print("1. 图形化布局")
    print("2. 紧凑型布局")
    print("3. Deep Finesse格式")
    print("4. 全部输出（默认）")
    choice = input("请选择 (1/2/3/4): ").strip()
    mode_map = {
        "1": OUTPUT_MODE_GRAPHIC,
        "2": OUTPUT_MODE_COMPACT,
        "3": OUTPUT_MODE_DEEP_FINESSE,
        "4": "all"
    }
    if choice in mode_map:
        game.output_mode = mode_map[choice]
        mode_names = {
            OUTPUT_MODE_GRAPHIC: "图形化布局",
            OUTPUT_MODE_COMPACT: "紧凑型布局",
            OUTPUT_MODE_DEEP_FINESSE: "Deep Finesse格式",
            "all": "全部"
        }
        print(f"输出格式已设置为: {mode_names[mode_map[choice]]}")


def select_model(game: BiddingGame):
    print("\n选择AI模型:")
    print("1. DeepSeek Chat (快速)")
    print("2. DeepSeek Reasoner (推理)")
    choice = input("请选择 (1/2): ").strip()
    if choice == "1":
        game.model = "deepseek-v4-flash"
        game.llm_client.model = "deepseek-v4-flash"
        print("AI模型已设置为: DeepSeek V4-Flash")
    elif choice == "2":
        game.model = "deepseek-v4-pro"
        game.llm_client.model = "deepseek-v4-pro"
        print("AI模型已设置为: DeepSeek V4-Pro")


def select_ai_settings(game: BiddingGame):
    while True:
        print("\nAI设置:")
        print("1. AI模型")
        print("2. 主提示词AI温度")
        print("3. 备用提示词AI温度")
        print("0. 返回")
        choice = input("请选择: ").strip()
        
        if choice == "1":
            select_model(game)
        elif choice == "2":
            select_main_prompt_temperature(game)
        elif choice == "3":
            select_fallback_prompt_temperature(game)
        elif choice == "0":
            return


def select_main_prompt_temperature(game: BiddingGame):
    global MAIN_PROMPT_TEMPERATURE
    print(f"\n当前主提示词AI温度: {MAIN_PROMPT_TEMPERATURE}")
    print("温度说明:")
    print("  - 较低值（0.0-0.3）: 输出更确定、更一致，适合需要精确答案的任务")
    print("  - 中等值（0.4-0.7）: 平衡确定性和创造性，适合大多数任务")
    print("  - 较高值（0.8-1.0）: 输出更有创造性、更多样化，适合需要创意的任务")
    print("\n推荐值: 0.2（叫牌需要精确性）")
    
    while True:
        temp_input = input(f"请输入新温度值 (0.0-1.0，当前: {MAIN_PROMPT_TEMPERATURE}): ").strip()
        try:
            temp = float(temp_input)
            if 0.0 <= temp <= 1.0:
                MAIN_PROMPT_TEMPERATURE = temp
                print(f"主提示词AI温度已设置为: {MAIN_PROMPT_TEMPERATURE}")
                break
            else:
                print("温度值必须在0.0到1.0之间")
        except ValueError:
            print("请输入有效的数字")


def select_fallback_prompt_temperature(game: BiddingGame):
    global FALLBACK_PROMPT_TEMPERATURE
    print(f"\n当前备用提示词AI温度: {FALLBACK_PROMPT_TEMPERATURE}")
    print("温度说明:")
    print("  - 较低值（0.0-0.3）: 输出更确定、更一致，适合需要精确答案的任务")
    print("  - 中等值（0.4-0.7）: 平衡确定性和创造性，适合大多数任务")
    print("  - 较高值（0.8-1.0）: 输出更有创造性、更多样化，适合需要创意的任务")
    print("\n推荐值: 0.5（备用提示词需要一定的灵活性）")
    
    while True:
        temp_input = input(f"请输入新温度值 (0.0-1.0，当前: {FALLBACK_PROMPT_TEMPERATURE}): ").strip()
        try:
            temp = float(temp_input)
            if 0.0 <= temp <= 1.0:
                FALLBACK_PROMPT_TEMPERATURE = temp
                print(f"备用提示词AI温度已设置为: {FALLBACK_PROMPT_TEMPERATURE}")
                break
            else:
                print("温度值必须在0.0到1.0之间")
        except ValueError:
            print("请输入有效的数字")


def _validate_lead_card(onlead_hand: str, lead: str) -> bool:
    if not lead or not onlead_hand:
        return True
    
    lead = lead.upper().replace("10", "T")
    lead_suit = None
    lead_rank = None
    
    if lead.startswith("S"):
        lead_suit, lead_rank = "S", lead[1:]
    elif lead.startswith("H"):
        lead_suit, lead_rank = "H", lead[1:]
    elif lead.startswith("D"):
        lead_suit, lead_rank = "D", lead[1:]
    elif lead.startswith("C"):
        lead_suit, lead_rank = "C", lead[1:]
    elif lead.startswith("♠"):
        lead_suit, lead_rank = "S", lead[1:]
    elif lead.startswith("♥"):
        lead_suit, lead_rank = "H", lead[1:]
    elif lead.startswith("♦"):
        lead_suit, lead_rank = "D", lead[1:]
    elif lead.startswith("♣"):
        lead_suit, lead_rank = "C", lead[1:]
    else:
        return True
    
    onlead_hand = onlead_hand.upper().replace("10", "T")
    
    suits = onlead_hand.split()
    suit_idx = {"S": 0, "H": 1, "D": 2, "C": 3}
    
    if lead_suit in suit_idx:
        target_suit = suits[suit_idx[lead_suit]] if len(suits) > suit_idx[lead_suit] else ""
        if lead_rank in target_suit or lead_rank.replace("T", "10") in target_suit:
            return True
    
    return False


def _analyze_with_fallback(game: BiddingGame):
    hands_dict = {}
    for pos in Position:
        pos_name = get_position_name(pos)
        hands_dict[pos_name] = game.hands[pos].to_display_string()
    
    contract, declarer = parse_contract_info(game.bidding_sequence)
    
    declarer_to_pos = {"南": Position.SOUTH, "西": Position.WEST, "北": Position.NORTH, "东": Position.EAST}
    declarer_pos = declarer_to_pos.get(declarer, Position.SOUTH)
    
    position_order = [Position.SOUTH, Position.WEST, Position.NORTH, Position.EAST]
    declarer_idx = position_order.index(declarer_pos)
    onlead_idx = (declarer_idx + 1) % 4
    onlead_pos = position_order[onlead_idx]
    onlead_name = {"南": "South", "西": "West", "北": "North", "东": "East"}[get_position_name(onlead_pos)]
    
    print(f"\n识别到的定约: {contract}")
    print(f"庄家: {declarer}")
    print(f"首攻方: {onlead_name}")
    print("\n正在调用 Deep Finesse 分析...", flush=True)
    
    result = analyze_with_deep_finesse(hands_dict, contract, declarer, onlead_name)
    print(format_analysis_result(result), flush=True)


def contract_analysis_menu(game: BiddingGame):
    print("\n" + "=" * 60)
    print("定约分析")
    print("=" * 60)
    print("1. 分析定约可行性（Deep Finesse）")
    print("2. 批量双明手分析（endplay）")
    print("0. 返回")
    print("=" * 60)
    
    choice = input("请选择: ").strip()
    
    if choice == "1":
        analyze_contract(game)
    elif choice == "2":
        batch_double_dummy_analysis(game)
    elif choice == "0":
        return
    else:
        print("无效选择")


def analyze_contract(game: BiddingGame):
    print("\n分析定约可行性")
    print("1. 使用当前牌局和叫牌序列分析")
    print("2. 输入Deep Finesse格式牌局分析")
    choice = input("请选择 (1/2): ").strip()
    
    if choice == "1":
        if not game.hands:
            print("尚未发牌，请先发牌或输入牌局")
            return
        
        if not game.bidding_sequence:
            print("尚未进行叫牌，无法分析定约")
            return
        
        if game.df_format_output:
            print("\n使用叫牌结果中的 Deep Finesse 格式:")
            print(game.df_format_output)
            
            df_deal = parse_df_deal(game.df_format_output)
            
            if df_deal["north"] and df_deal["south"]:
                print(f"\n解析结果:")
                print(f"定约: {df_deal['contract']}")
                print(f"庄家: {df_deal['declarer']}")
                print(f"首攻方: {df_deal['onlead']}")
                print(f"首攻: {df_deal['lead']}")
                
                hands_dict = {
                    "北": df_format_to_hand(df_deal['north']),
                    "西": df_format_to_hand(df_deal['west']) if df_deal['west'] else "",
                    "南": df_format_to_hand(df_deal['south']),
                    "东": df_format_to_hand(df_deal['east']) if df_deal['east'] else ""
                }
                
                onlead_pos_map = {"SOUTH": "南", "WEST": "西", "NORTH": "北", "EAST": "东"}
                onlead_pos_cn = onlead_pos_map.get(df_deal['onlead'], "西")
                onlead_hand = hands_dict.get(onlead_pos_cn, "")
                
                if df_deal['lead'] and not _validate_lead_card(onlead_hand, df_deal['lead']):
                    print(f"\n⚠️ 警告: 首攻牌 {df_deal['lead']} 不在 {df_deal['onlead']} 的手牌中!")
                    print(f"{df_deal['onlead']} 手牌: {onlead_hand}")
                    print("首攻牌将被忽略")
                    df_deal['lead'] = None
                
                print("\n正在调用 Deep Finesse 分析...", flush=True)
                result = analyze_with_deep_finesse(
                    hands_dict, 
                    df_deal['contract'], 
                    df_deal['declarer'], 
                    df_deal['onlead'], 
                    df_deal['lead']
                )
                print(format_analysis_result(result), flush=True)
            else:
                print("解析 Deep Finesse 格式失败，使用备用方法")
                _analyze_with_fallback(game)
        else:
            print("未找到 Deep Finesse 格式输出，使用备用方法")
            _analyze_with_fallback(game)
    
    elif choice == "2":
        print("\n请输入Deep Finesse格式牌局（输入空行结束）:")
        print("示例格式:")
        print("Deal: 1                               AJ2 A32 K32 KQ32")
        print("Contract: 6D-South   Q543 QT84 T4 T76                  KT987 K7 95 J984")
        print("OnLead: West                          6 J965 AQJ876 A5")
        print("Lead: ")
        
        lines = []
        print("(输入完成后，按回车键结束)")
        while True:
            try:
                line = input()
                if not line.strip():
                    break
                lines.append(line)
            except EOFError:
                break
        
        if not lines:
            print("未输入任何内容")
            return
        
        print(f"收到 {len(lines)} 行输入", flush=True)
        df_text = "\n".join(lines)
        df_deal = parse_df_deal(df_text)
        print("解析完成", flush=True)
        
        if not df_deal["north"] or not df_deal["south"]:
            print("解析失败，请检查输入格式")
            return
        
        print(f"\n解析结果:")
        print(f"北家: {df_deal['north']}")
        print(f"西家: {df_deal['west']}")
        print(f"南家: {df_deal['south']}")
        print(f"东家: {df_deal['east']}")
        print(f"定约: {df_deal['contract']}")
        print(f"庄家: {df_deal['declarer']}")
        print(f"首攻方: {df_deal['onlead']}")
        print(f"首攻: {df_deal['lead']}")
        
        hands_dict = {
            "北": df_format_to_hand(df_deal['north']),
            "西": df_format_to_hand(df_deal['west']) if df_deal['west'] else "",
            "南": df_format_to_hand(df_deal['south']),
            "东": df_format_to_hand(df_deal['east']) if df_deal['east'] else ""
        }
        
        contract = df_deal['contract'] or "3NT"
        declarer = df_deal['declarer']
        onlead = df_deal['onlead']
        lead = df_deal['lead']
        
        print("\n正在调用 Deep Finesse 分析...", flush=True)
        result = analyze_with_deep_finesse(hands_dict, contract, declarer, onlead, lead)
        print(format_analysis_result(result), flush=True)
    
    else:
        print("无效选择")


def batch_double_dummy_analysis(game):
    """
    批量双明手分析 - 显示每个玩家在每门花色上坐庄的最高可完成定约
    """
    print("\n" + "=" * 60)
    print("批量双明手分析（DD）")
    print("=" * 60)

    if not DD_ANALYSIS_AVAILABLE:
        print("双明手分析模块不可用")
        print("请确保 dd_analysis.py 文件存在且 DirectDDS 可用")
        return

    if not game.hands:
        print("尚未发牌，请先发牌或输入牌局")
        return

    hands_dict = {}
    hcp_dict = {}
    for position, hand in game.hands.items():
        pos_name = position.value
        hands_dict[pos_name] = hand.to_simple_string()
        hcp_dict[pos_name] = hand.hcp

    print("当前牌局:")
    for pos, hand_str in hands_dict.items():
        print(f"  {pos}: {hand_str}")

    print("\n正在计算双明手分析...")

    try:
        result = analyze_all_contracts(hands_dict, hcp_dict)

        if result.get("success"):
            print(result.get("formatted_output", "分析完成，但未找到格式化输出"))
        else:
            print(f"分析失败: {result.get('error', '未知错误')}")
            if "traceback" in result:
                print(f"错误详情: {result['traceback']}")

    except Exception as e:
        print(f"分析过程中出现异常: {str(e)}")
        import traceback
        traceback.print_exc()


def main():
    global SHOW_FULL_LLM_OUTPUT
    print("正在初始化...", flush=True)
    game = BiddingGame()
    print("初始化完成!", flush=True)
    
    if not game.llm_client.is_configured():
        print("=" * 60, flush=True)
        print("警告: DeepSeek API Key 未配置", flush=True)
        print("=" * 60, flush=True)
        print("请设置环境变量 DEEPSEEK_API_KEY", flush=True)
        print("例如: set DEEPSEEK_API_KEY=your_api_key", flush=True)
        print(flush=True)
    
    while True:
        print_menu()
        choice = input("请选择: ").strip()
        
        if choice == "0":
            print("再见!")
            break
        elif choice == "1":
            select_deal_and_start(game)
        elif choice == "2":
            select_settings(game)
        elif choice == "3":
            if game.hands:
                game.display_hands()
            else:
                print("尚未发牌")
        elif choice == "4":
            if game.hands:
                game.run_bidding_loop()
            else:
                print("尚未发牌，请先发牌或输入牌局")
        elif choice == "5":
            contract_analysis_menu(game)
        elif choice == "6":
            view_history(game)
        elif choice == "7":
            test_bidding_sequence(game)
        elif choice == "8":
            reload_jf_segments(game)
        else:
            print("无效选择，请重试")


if __name__ == "__main__":
    main()
