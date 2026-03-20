import json
import os
from datetime import datetime
from typing import Dict, List, Optional
from pathlib import Path
from dataclasses import dataclass, asdict
from enum import Enum

from bridge.dealer import Position, parse_hand_string
from bridge.output_format import generate_graphic_output


HISTORY_FILE = Path(__file__).parent.parent / "bidding_history.json"


@dataclass
class BiddingRecord:
    id: str
    timestamp: str
    hands: Dict[str, str]
    bidding_sequence: str
    final_contract: str
    declarer: str
    mode: str
    human_position: Optional[str]
    bid_meaning: str = ""
    note: str = ""
    
    def to_dict(self) -> Dict:
        return asdict(self)
    
    @classmethod
    def from_dict(cls, data: Dict) -> "BiddingRecord":
        return cls(**data)


class HistoryManager:
    def __init__(self):
        self.records: List[BiddingRecord] = []
        self._load()
    
    def _load(self):
        if HISTORY_FILE.exists():
            try:
                with open(HISTORY_FILE, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    self.records = [BiddingRecord.from_dict(r) for r in data]
            except (json.JSONDecodeError, KeyError):
                self.records = []
    
    def _save(self):
        try:
            with open(HISTORY_FILE, "w", encoding="utf-8") as f:
                json.dump([r.to_dict() for r in self.records], f, ensure_ascii=False, indent=2)
        except Exception as e:
            print(f"保存历史记录失败: {e}")
            raise
    
    def add_record(
        self,
        hands: Dict[str, str],
        bidding_sequence: str,
        final_contract: str,
        declarer: str,
        mode: str,
        human_position: Optional[str] = None,
        bid_meaning: str = "",
        note: str = ""
    ) -> BiddingRecord:
        record_id = datetime.now().strftime("%Y%m%d%H%M%S")
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        
        record = BiddingRecord(
            id=record_id,
            timestamp=timestamp,
            hands=hands,
            bidding_sequence=bidding_sequence,
            final_contract=final_contract,
            declarer=declarer,
            mode=mode,
            human_position=human_position,
            bid_meaning=bid_meaning,
            note=note
        )
        
        self.records.insert(0, record)
        self._save()
        return record
    
    def get_all_records(self) -> List[BiddingRecord]:
        return self.records
    
    def get_record(self, record_id: str) -> Optional[BiddingRecord]:
        for record in self.records:
            if record.id == record_id:
                return record
        return None
    
    def delete_record(self, record_id: str) -> bool:
        for i, record in enumerate(self.records):
            if record.id == record_id:
                self.records.pop(i)
                self._save()
                return True
        return False
    
    def update_note(self, record_id: str, note: str) -> bool:
        record = self.get_record(record_id)
        if record:
            record.note = note
            self._save()
            return True
        return False
    
    def clear_all(self):
        self.records = []
        self._save()
    
    def format_record_summary(self, record: BiddingRecord, index: int) -> str:
        note_str = f" - {record.note}" if record.note else ""
        return f"[{index}] {record.timestamp} | {record.final_contract} | {record.bidding_sequence[:40]}{'...' if len(record.bidding_sequence) > 40 else ''}{note_str}"
    
    def format_record_detail(self, record: BiddingRecord) -> str:
        try:
            hands = {}
            for pos_name, hand_str in record.hands.items():
                pos_map = {"北": Position.NORTH, "西": Position.WEST, "南": Position.SOUTH, "东": Position.EAST}
                if pos_name in pos_map:
                    hands[pos_map[pos_name]] = parse_hand_string(hand_str.replace("♠", " ").replace("♥", " ").replace("♦", " ").replace("♣", " "))
            
            if len(hands) == 4:
                dealer_map = {"北": Position.NORTH, "西": Position.WEST, "南": Position.SOUTH, "东": Position.EAST}
                dealer = dealer_map.get(record.declarer, Position.NORTH)
                
                graphic = generate_graphic_output(
                    hands=hands,
                    bidding_str=record.bidding_sequence,
                    dealer=dealer,
                    mode=record.mode,
                    human_position=None,
                    bid_meaning=record.bid_meaning
                )
                
                lines = [
                    "=" * 60,
                    f"历史记录 ID: {record.id}",
                    f"时间: {record.timestamp}",
                    "=" * 60,
                    "",
                    graphic,
                    "",
                ]
                if record.note:
                    lines.append(f"备注: {record.note}")
                lines.append("=" * 60)
                return "\n".join(lines)
        except Exception as e:
            pass
        
        lines = [
            "=" * 60,
            f"历史记录 ID: {record.id}",
            f"时间: {record.timestamp}",
            "=" * 60,
            "",
            "牌局分布:",
            f"  北: {record.hands.get('北', 'N/A')}",
            f"  西: {record.hands.get('西', 'N/A')}",
            f"  南: {record.hands.get('南', 'N/A')}",
            f"  东: {record.hands.get('东', 'N/A')}",
            "",
            f"叫牌模式: {record.mode}",
            f"庄家: {record.declarer}",
            f"人类位置: {record.human_position or '无'}",
            "",
            f"最终定约: {record.final_contract}",
            "",
            "叫牌序列:",
            f"  {record.bidding_sequence}",
            "",
        ]
        if record.bid_meaning:
            lines.append("叫牌历史:")
            lines.append(f"  {record.bid_meaning}")
            lines.append("")
        if record.note:
            lines.append(f"备注: {record.note}")
        lines.append("=" * 60)
        return "\n".join(lines)
