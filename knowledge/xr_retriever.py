"""新睿二盖一体系检索器（与 JF 完全隔离）。

数据源：scripts/xr_data/md_tables.json（由 scripts/xr_md_parse.py 生成）。
按 seq 精确查表导航：seq = 当前玩家之前所有实质叫品，敌方叫品用半角括号包裹。
表的 entries 即当前玩家的备选叫品（与 JFRetriever.subsequent_bids 同契约）。

不与 JFLoader / extract_retrieval_keyword / prompt 注入旧逻辑发生任何接触。
"""
from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Dict, List, Optional, Tuple

XR_DATA_PATH = Path(__file__).resolve().parent.parent / "scripts" / "xr_data" / "md_tables.json"

# 位置到阵营：当前玩家所在阵营 = 我方，另一方 = 敌方
_NS = {"南", "北", "S", "N", "SOUTH", "NORTH"}
_EW = {"东", "西", "E", "W", "EAST", "WEST"}

# 开叫（不含括号的首个叫品）→ 章节
_OPENING_CHAPTER = {
    "1C": 2, "1D": 3, "1H": 4, "1S": 5, "1NT": 6,
    "2C": 7, "2NT": 8, "2D": 9, "2H": 9, "2S": 9,
}
_DEFENSE_CHAPTER = 11  # 敌方开叫的防守叫牌


def position_side(position: str) -> str:
    p = str(position or "").strip().upper()
    if p in _EW:
        return "EW"
    return "NS"


def _tid_key(tid: str) -> Tuple[int, int]:
    m = re.match(r"(\d+)-(\d+)", tid)
    if m:
        return (int(m.group(1)), int(m.group(2)))
    return (9999, 0)


def _normalize_bid(bid: str) -> str:
    b = bid.strip().upper()
    if b in ("P", "PASS"):
        return "pass"
    return b


class XrSeq:
    """从实际叫牌序列推导带括号敌我 seq。seq 只保留实质叫品，pass 剔除，
    敌方叫品加半角括号以匹配新睿受干扰表/防守表。"""

    @staticmethod
    def build(bidding_sequence: str, current_position: str) -> str:
        if not bidding_sequence:
            return ""
        my_side = position_side(current_position)
        parts = re.split(r"[-—－]", bidding_sequence)
        toks: List[str] = []
        for part in parts:
            part = part.strip()
            if not part:
                continue
            m = re.search(r"\(([^)]+)\)\s*(\S+)", part)
            if not m:
                continue
            pos = m.group(1).strip()
            bid = _normalize_bid(m.group(2))
            if bid == "pass":
                continue
            if bid in ("X", "XX"):
                scope = XrSeq
                t = f"({'X' if bid == 'X' else 'XX'})" if position_side(pos) != my_side else bid
                scope = t
                toks.append(scope)
                continue
            if re.match(r"^[1-7](?:C|D|H|S|NT)$", bid) is None:
                continue
            tok = f"({bid})" if position_side(pos) != my_side else bid
            toks.append(tok)
        return "-".join(toks)


def _canon(seq: str) -> str:
    """归一化 seq：删除敌括号前的连字符（运行时 1NT-(2C) 与索引 1NT(2C) 对齐）。"""
    if not seq:
        return seq
    return re.sub(r"-([（(])", r"\1", seq)


class XrRetriever:
    def __init__(self, tables: Optional[Dict] = None, path: Optional[Path] = None):
        self.tables = tables if tables is not None else self._load(path)
        self.seq_index: Dict[str, List[Tuple[str, Dict]]] = {}
        self._build_index()
        self._openings_by_seq: Dict[str, str] = {}
        self._build_openings()

    @staticmethod
    def _load(path: Optional[Path]) -> Dict:
        p = Path(path) if path else Path(XR_DATA_PATH)
        return json.loads(p.read_text(encoding="utf-8"))

    def _build_index(self):
        for tid, tb in self.tables.items():
            seqs = tb.get("seq")
            if not seqs:
                continue
            if isinstance(seqs, str):
                seqs = [seqs]
            for seq in seqs:
                seq = _canon(seq)
                if seq:
                    self.seq_index.setdefault(seq, []).append((tid, tb))
        for seq in self.seq_index:
            self.seq_index[seq].sort(key=lambda x: _tid_key(x[0]))

    def _build_openings(self):
        # 根开叫表：seq 为单叫品（无括号）且属于该开叫章节，条目为应叫方案
        for seq, cands in self.seq_index.items():
            if "-" in seq or "(" in seq:
                continue
            chapter = _OPENING_CHAPTER.get(seq)
            if not chapter:
                continue
            for tid, tb in cands:
                if _tid_key(tid)[0] != chapter:
                    continue
                if any(e.get("bids") for e in tb.get("entries", [])):
                    self._openings_by_seq[seq] = tid
                    break

    def list_seq(self, seq: str) -> List[Tuple[str, Dict]]:
        return list(self.seq_index.get(_canon(seq), []))

    def _best_table(self, seq: str) -> Optional[Tuple[str, Dict]]:
        seq = _canon(seq)
        cands = self.seq_index.get(seq)
        if not cands:
            return None
        if len(cands) == 1:
            return cands[0]
        # 歧义消解：优先匹配开叫章节，否则取最小表 id
        first = seq.split("-")[0]
        if first.startswith("("):
            for tid, tb in cands:
                if _tid_key(tid)[0] == _DEFENSE_CHAPTER:
                    return (tid, tb)
        elif first in _OPENING_CHAPTER:
            chapter = _OPENING_CHAPTER[first]
            for tid, tb in cands:
                if _tid_key(tid)[0] == chapter:
                    return (tid, tb)
        return cands[0]

    def retrieve_entries(self, seq: str) -> List[Dict]:
        hit = self._best_table(seq)
        if not hit:
            return []
        return hit[1].get("entries", [])

    def retrieve_with_preprocess(self, seq: str, bidding_sequence: str, partner_name: str) -> Dict:
        result = {
            "original_content": "",
            "partner_bid": None,
            "subsequent_bids": [],
            "is_structural_convention": False,
        }
        hit = self._best_table(seq)
        if not hit:
            return result
        tid, tb = hit
        subsequent = []
        for ent in tb.get("entries", []):
            bids = ent.get("bids", [])
            for b in bids:
                if not b:
                    continue
                line = ent.get("desc", "")
                pt = ent.get("points", "")
                text_parts = []
                if pt:
                    text_parts.append(f"{pt}点")
                if line:
                    text_parts.append(line)
                subsequent.append({"bid": _normalize_bid(b), "line": "，".join(text_parts), "indent": 0})
        if not subsequent:
            return result
        # 去重保留首现
        seen = set()
        uniq = []
        for sb in subsequent:
            if sb["bid"] in seen:
                continue
            seen.add(sb["bid"])
            uniq.append(sb)
        last = seq.split("-")[-1]
        result["original_content"] = tb.get("title", "")
        result["partner_bid"] = last.lstrip("(").rstrip(")") if last else None
        result["subsequent_bids"] = uniq
        result["is_structural_convention"] = True
        return result