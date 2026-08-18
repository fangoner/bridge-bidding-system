import json
import re
from pathlib import Path

DATA = Path(__file__).resolve().parent / "xr_data"
OUT = DATA / "md_tables.json"
SRC = Path(__file__).resolve().parent.parent / "书籍" / "新睿自然.md"


SUIT_MAP = {"♣": "C", "♧": "C", "♦": "D", "♢": "D", "♥": "H", "♡": "H", "♠": "S", "♤": "S"}


def parse_bid_token(tok):
    """将单个叫品token规范化为CDSH/NT大写形式，无法识别返回None。"""
    t = tok.strip()
    if re.match(r"^[1-7]NT$", t, re.I):
        return f"{t[0]}NT".upper()
    m = re.match(r"^([1-7])([♣♧♦♢♥♡♠♤])$", t)
    if m:
        suit = SUIT_MAP[m.group(2)]
        return f"{m.group(1)}{suit}"
    return None


def parse_bid_cell(raw):
    """将叫品单元格解析为叫品列表。

    支持形式：
      - 完整叫品：1♣、1NT、pass、X、XX
      - 共享阶数：1♣/♦ -> [1C,1D]，3♣/♦/♥/♠ -> [3C,3D,3H,3S]
    叫品按 _bid_rank 递增校验，非递增则截断。
    """
    if not raw:
        return []
    raw = raw.replace("*", "").replace("＊", "").strip()
    parts = re.split(r"[/／、]+", raw)
    out, prev = [], None
    carry_level = None
    for part in parts:
        part = part.strip()
        if not part:
            continue
        m = re.match(r"^([1-7])NT$", part, re.I)
        if m:
            b = f"{m.group(1)}NT"
            if prev is not None and _bid_rank(b) <= _bid_rank(prev):
                break
            out.append(b)
            prev, carry_level = b, int(m.group(1))
            continue
        m = re.match(r"^([1-7])([♣♧♦♢♥♡♠♤])$", part)
        if m:
            b = f"{m.group(1)}{SUIT_MAP[m.group(2)]}"
            if prev is not None and _bid_rank(b) <= _bid_rank(prev):
                break
            out.append(b)
            prev, carry_level = b, int(m.group(1))
            continue
        sm = re.match(r"^([♣♧♦♢♥♡♠♤])$", part)
        if sm and carry_level:
            b = f"{carry_level}{SUIT_MAP[sm.group(1)]}"
            if prev is not None and _bid_rank(b) <= _bid_rank(prev):
                break
            out.append(b)
            prev = b
            continue
        npart = part.replace("×", "x").replace("Ｘ", "x").replace("ｘ", "x").lower()
        if npart in ("pass", "x", "xx"):
            out.append(npart)
            prev = npart
            continue
        break
    return out

TITLE_RE = re.compile(r'^\*\*表(\d+)-(\d+)\s*(.*?)\*\*$')
SECTION_RE = re.compile(r'^\*\*[^*]+\*\*$')
SEP_RE = re.compile(r'^:?-{2,}:?$')
HEADER_FIRST = {"应叫", "开叫人再叫", "应叫人再叫", "开叫", "开叫人答叫", "应叫人答叫"}
HEADER_ALL = {"应叫", "开叫人再叫", "应叫人再叫", "开叫", "开叫人答叫", "应叫人答叫",
              "牌点", "说明", "点力范围", "再叫制式"}
INTERF_RE = re.compile(r"[（(].{0,12}[）)]")


def split_cells(line):
    line = line.strip()
    if not (line.startswith("|") and line.endswith("|")):
        return None
    return [c.strip() for c in line.strip().strip("|").split("|")]


def is_separator(cells):
    return bool(cells) and all(SEP_RE.match(c.strip()) for c in cells if c.strip())


def is_header(cells):
    if not cells:
        return False
    return cells[0] in HEADER_FIRST or all(c in HEADER_ALL for c in cells if c)


def parse_tables(text):
    tables, active = {}, None
    for raw in text.splitlines():
        line = raw.rstrip()
        m = TITLE_RE.match(line)
        if m:
            tid = f"{m.group(1)}-{m.group(2)}"
            title = m.group(3).strip()
            if active:
                tables.setdefault(active["tid"], active)
            if tid in tables:
                # 同 tid 续表（跨页"续表"）：合并行，保留更完整标题
                prev = tables[tid]
                if title and "续表" not in title and "续" not in title:
                    prev["title"] = title
                active = prev
            else:
                active = {"tid": tid, "title": title, "rows": [], "header": None}
            continue
        if active is None:
            continue
        cells = split_cells(line)
        if cells is None:
            if SECTION_RE.match(line):
                tables.setdefault(active["tid"], active)
                active = None
            continue
        if is_separator(cells):
            continue
        if active["header"] is None:
            if is_header(cells):
                active["header"] = cells
                continue
        if is_header(cells):
            continue
        active["rows"].append(cells)
    if active:
        tables.setdefault(active["tid"], active)
    return tables


BID_RUN_SEP = "-－—一/／"
RANK_ORDER = {"C": 0, "D": 1, "H": 2, "S": 3, "NT": 4}


def _bid_rank(b):
    m = re.match(r"^([1-7])(C|D|H|S|NT)$", b)
    if not m:
        return -1
    return (int(m.group(1)) - 1) * 5 + RANK_ORDER[m.group(2)]


def push_enemy(cands, bids):
    """把敌方括号内的一个或多个叫品展开到候选 seq（每个叫品一个分支）。
    过滤 pass（与运行时 XrSeq.build 一致：剔除）。"""
    bids = [b for b in bids if b != "pass"]
    if not bids:
        return
    if len(bids) == 1:
        b = bids[0]
        cands[:] = [(c + f"({b})" if c else f"({b})") for c in cands]
    else:
        cands[:] = [(c + f"({b})" if c else f"({b})") for c in cands for b in bids]


def _last_own(c):
    """取 seq 中最后一个我方实质叫品（排除敌括号段），用于我方叫品的递增校验。"""
    for seg in reversed(c.split("-")):
        if seg and not seg.startswith("("):
            return seg
    return ""


def push_own(cands, bids):
    """把我方当前玩家的多个可选叫品（如 1♥/♠、2♥/♠、3♣/♦）笛卡尔展开到候选 seq，
    用 - 连接（与运行时 XrSeq.build 我方叫品一致）。X/XX/pass 不做递增校验。"""
    new = []
    for c in cands:
        lo = _last_own(c)
        for b in bids:
            if b == "pass":
                continue
            if b not in ("X", "XX") and lo and _bid_rank(b) <= _bid_rank(lo):
                continue
            new.append(c + ("-" + b if c else b))
    if new:
        cands[:] = new


def title_seq(title, parse_fn):
    """从标题开头提取连续叫品，返回候选 seq 列表（敌方多叫品笛卡尔展开），无则 None。

    敌方叫品以括号（全角或半角）包围，归一化为半角 (1D) 纳入 seq。
    敌方括号内可含多个叫品（`、`/`/`分隔或共享阶数），展开为多 seq；如
    "1NT-(2♣/♦/♥/♠) 后续" -> ["1NT-(2C)", "1NT-(2D)", "1NT-(2H)", "1NT-(2S)"]。
    约定名说明（如"迈克尔斯/特殊2NT/兰迪"）被剥离；迈克尔斯扣叫映射为 2阶+我方开叫花色。
    """
    cands = [""]
    rest = title
    while True:
        rest = re.sub(r"^[\s\-－—一/／]+", "", rest)
        m_opp = re.match(r"^[（(]([^）)]*)[）)]", rest)
        if m_opp:
            _inner = m_opp.group(1).strip().replace("×", "x").replace("Ｘ", "x").replace("ｘ", "x")
            rest = rest[m_opp.end():]
            if "迈克尔斯" in _inner and cands and cands[0] and not cands[0].startswith("("):
                _osuit = cands[0].split("-")[0][-1]
                if _osuit in "CDSH":
                    push_enemy(cands, [f"2{_osuit}"])
                    continue
            _t = re.split(r"[：:]", _inner, maxsplit=1)[0].strip()
            if _t.lower() == "pass":
                # pass 与运行时 XrSeq.build 一致：剔除，不出现在 seq 中
                continue
            if _t.upper() in ("X", "XX"):
                push_enemy(cands, [_t.upper()])
                continue
            _bids = parse_bid_cell(_t)
            if _bids:
                push_enemy(cands, _bids)
            continue
        mX = re.match(r"^[×ＸｘxX]{1,2}", rest)
        if mX:
            _xx = "XX" if len(mX.group(0)) > 1 else "X"
            push_own(cands, [_xx])
            rest = rest[mX.end():]
            continue
        m_run = re.match(r"^[1-7](?:[♣♦♥♠]|NT)(?:[/／、][♣♦♥♠0-9NT]+)*", rest)
        if not m_run:
            break
        _bids = parse_bid_cell(m_run.group(0))
        if not _bids:
            break
        push_own(cands, _bids)
        rest = rest[m_run.end():]
    cleaned = [c for c in cands if c]
    return cleaned if cleaned else None


def parse_points(s):
    s = s.replace("～", "~").replace("—", "-").replace("－", "-")
    s = s.replace("≥", ">=").replace("＜", "<").replace("≤", "<=")
    tiers = [t.strip() for t in s.split("<br>") if t.strip()]
    return "/".join(tiers) if tiers else ""


def extract_links(desc):
    links = []
    for mm in re.finditer(r"表\s*(\d+)-(\d+)((?:[\/／]\d+)*)", desc):
        ch, base = mm.group(1), mm.group(2)
        lks = [f"{ch}-{base}"]
        for extra in re.findall(r"[\/／](\d+)", mm.group(3)):
            lks.append(f"{ch}-{extra}")
        for lk in lks:
            if lk not in links:
                links.append(lk)
    return links


def clean_desc(d):
    d = re.sub(r"\s*[［\[（(]?(表\d+-\d+(?:[／/]\d+)*)[\]）)]?\s*", r"（\1）", d)
    d = d.replace("[", "").replace("]", "")
    d = d.replace("<br>", "；")
    d = re.sub(r"\s+", "", d)
    d = re.sub(r"[，,；;]{2,}", "；", d)
    d = re.sub(r"^[；;，,]+", "", d)
    return d.strip()


def row_to_entry(cells, prev_bids):
    bid, points, desc = cells[0], "", ""
    if len(cells) == 1:
        desc = cells[0]
    elif len(cells) == 2:
        c0 = cells[0]
        if re.search(r"[1-7][♣♦♥♠NT]|[/／][♣♦♥♠]|~|>=|\d点", c0):
            bid, desc = cells[0], cells[1]
        else:
            points, desc = cells[0], cells[1]
    else:
        bid, points, desc = cells[0], cells[1], cells[2]
    raw_bid = bid.replace("*", "").replace("＊", "").strip()
    if raw_bid:
        bids = parse_bid_cell(raw_bid) or []
        prev_bids = bids
    else:
        bids = list(prev_bids)
    return {"bids": bids, "points": parse_points(points),
            "desc": clean_desc(desc), "links": extract_links(desc)}, prev_bids


def class_of(tid, title, seq):
    if isinstance(seq, tuple) and seq:
        return "干扰"
    if INTERF_RE.search(title) or "争叫" in title or "迈克尔斯" in title or "特殊2NT" in title:
        return "干扰"
    if "开叫" in title and "后续" not in title:
        return "开叫"
    return "树表"


def read_text_any(path):
    raw = Path(path).read_bytes()
    if raw.startswith(b"\xff\xfe") or raw.startswith(b"\xfe\xff"):
        return raw.decode("utf-16")
    return raw.decode("utf-8-sig")


def main():
    text = read_text_any(SRC)
    tables = parse_tables(text)
    out = {}
    for tid, tb in tables.items():
        seq = title_seq(tb["title"], parse_bid_token)
        entries, prev = [], []
        for r in tb["rows"]:
            ent, prev = row_to_entry(r, prev)
            if ent["bids"] or ent["desc"] or ent["points"] or ent["links"]:
                entries.append(ent)
        out[tid] = {"title": tb["title"], "header": tb["header"], "seq": seq,
                     "entries": entries}
    OUT.write_text(json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8")
    from collections import Counter
    ch = Counter(tid.split("-")[0] for tid in out)
    print(f"表数: {len(out)}  章节: {dict(sorted(ch.items(), key=lambda k: int(k[0])))}")
    nseq = sum(1 for v in out.values() if v["seq"])
    print(f"含seq: {nseq}/{len(out)}")
    multi = {tid: v["seq"] for tid, v in out.items() if v["seq"] and v["seq"].count("-") < 1}
    print("单叫品seq(应叫总表/开叫):", sorted(multi.items(), key=lambda x: int(x[0].split('-')[0])))
    entries_cnt = sum(len(v["entries"]) for v in out.values())
    print(f"总条目: {entries_cnt}")
    # 空叫品条目统计
    nobid = [tid for tid, v in out.items() for e in v["entries"] if not e["bids"]]
    print("无叫品条目所在表(去重):", sorted(set(nobid), key=lambda x: (int(x.split('-')[0]), int(x.split('-')[1]))))


if __name__ == "__main__":
    main()