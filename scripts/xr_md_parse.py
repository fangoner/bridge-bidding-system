import json
import re
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent))
import xr_build_tree as B

DATA = Path(__file__).resolve().parent / "xr_data"
OUT = DATA / "md_tables.json"
SRC = Path(__file__).resolve().parent.parent / "书籍" / "新睿自然.md"

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


def title_seq(title, parse_fn):
    """从标题开头提取连续叫品（可多叫），无则 None。
    叫品间以连字符/斜杠/空格连接；续接条件：下一个叫品阶数严格高于上一个
    （先叫不能高于后叫），因此"1♣-1♦ 2♥ 后续"解析为 1C-1D-2H。"""
    toks, rest = [], title
    while True:
        rest = re.sub(r"^[\s\-－—一/／]+", "", rest)
        m = re.match(r"^([1-7][♣♦♥♠]{1}|[1-7]NT)", rest)
        if not m:
            break
        b = parse_fn(m.group(1))
        if not b:
            break
        if toks and _bid_rank(b) <= _bid_rank(toks[-1]):
            break
        toks.append(b)
        rest = rest[m.end():]
    return "-".join(toks) if toks else None


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
        bids = B.parse_bid_cell(raw_bid) or []
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
        seq = title_seq(tb["title"], B.parse_bid_token)
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