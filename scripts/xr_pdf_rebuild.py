import json
import re
import sys
from pathlib import Path

import fitz

BASE = Path(__file__).resolve().parent.parent
PDF = BASE / "书籍" / "新睿桥牌二盖一体系.pdf"
OUT_DIR = BASE / "scripts" / "xr_data" / "pdf_tables"
OUT_DIR.mkdir(parents=True, exist_ok=True)

SUIT_FIX = {"今": "♠", "会": "♠", "令": "♦", "曾": "♥", "萼": "♥", "¥": "♥", "＊": "♣", "*": "♣", "+": "♣"}

FOOTER_PAT = re.compile(r"^(新睿桥牌二盖一体系|XR-TCO|•?\d+•?)$")
TABLE_TITLE_PAT = re.compile(r"^表\s*(\d+)[-—－一](\d+)")
FULLWIDTH = str.maketrans("０１２３４５６７８９", "0123456789")
SUIT_CHARS = "♣♦♥♠ntNT"


def fix_text(s: str) -> str:
    for k, v in SUIT_FIX.items():
        s = s.replace(k, v)
    return s


def normalize_words(page):
    words = page.get_text("words")
    if page.number % 2 == 1:
        w, h = page.rect.width, page.rect.height
        fixed = []
        for x0, y0, x1, y1, word, block, line, word_no in words:
            fixed.append((w - x1, h - y1, w - x0, h - y0, word, block, line, word_no))
        words = fixed
    return words


def group_rows(words, y_from: float = 0.0, tol: float = 12.0):
    rows = {}
    for x0, y0, x1, y1, w, *_ in words:
        if y1 <= y_from + 2:
            continue
        placed = False
        for ry in rows:
            if abs(ry - y0) < tol:
                rows[ry].append((x0, fix_text(w)))
                placed = True
                break
        if not placed:
            rows[y0] = [(x0, fix_text(w))]
    return rows


def split_cols(rows, gap: float = 90.0):
    ordered = []
    for ry in sorted(rows):
        cells = sorted(rows[ry], key=lambda t: t[0])
        cols = []
        cur = []
        for x, w in cells:
            if cur and x - cur[-1][0] > gap:
                cols.append("".join(t[1] for t in cur))
                cur = []
            cur.append((x, w))
        if cur:
            cols.append("".join(t[1] for t in cur))
        ordered.append((round(ry), cols))
    return ordered


def extract_rows(page, y_from: float = 0.0, gap: float = 90.0, tol: float = 12.0):
    return split_cols(group_rows(normalize_words(page), y_from, tol), gap)


def row_text(cols):
    return " ".join(c for c in cols if c)


def is_footer(cols):
    return bool(FOOTER_PAT.match(row_text(cols).strip()))


def parse_table_title(text, valid_ids):
    text = text.translate(FULLWIDTH).replace(" ", "")
    m = TABLE_TITLE_PAT.match(text)
    if not m:
        return None
    ch = m.group(1)
    rest_digits = m.group(2)
    rest = text[m.end():]
    candidates = []
    for take in range(len(rest_digits), 0, -1):
        tid = f"{ch}-{rest_digits[:take]}"
        if valid_ids and tid not in valid_ids:
            continue
        tail = rest_digits[take:] + rest
        if tail and tail[0] in SUIT_CHARS:
            continue
        candidates.append((tid, tail))
    if not candidates:
        tid = f"{ch}-{rest_digits}"
        if valid_ids and tid not in valid_ids:
            return None
        return tid, rest
    return candidates[0]


def has_header_below(doc, pno, y, rows_cache):
    def check(rows, y_from, y_to):
        for ry, cols in rows:
            if y_from < ry <= y_to:
                joined = row_text(cols).replace(" ", "")
                if "牌点" in joined or "说明" in joined or "再叫" in joined:
                    return True
        return False

    rows = rows_cache.get(pno)
    if rows is None:
        rows = extract_rows(doc[pno])
        rows_cache[pno] = rows
    if check(rows, y, y + 200):
        return True
    if pno + 1 < len(doc):
        nxt = rows_cache.get(pno + 1)
        if nxt is None:
            nxt = extract_rows(doc[pno + 1])
            rows_cache[pno + 1] = nxt
        return check(nxt, 0, 300)
    return False


def find_titles(doc, chapter_prefixes, valid_ids=None, page_range=None):
    titles = []
    rows_cache = {}
    for pno in range(len(doc)):
        if page_range and not (page_range[0] <= pno + 1 <= page_range[1]):
            continue
        page = doc[pno]
        rows_cache[pno] = extract_rows(page)
        for ry, cols in rows_cache[pno]:
            text = row_text(cols)
            parsed = parse_table_title(text, valid_ids)
            if not parsed:
                continue
            tid, tail = parsed
            if not any(tid.startswith(p + "-") for p in chapter_prefixes):
                continue
            if not has_header_below(doc, pno, ry, rows_cache):
                continue
            titles.append({"table_id": tid, "page": pno + 1, "y": ry, "text": text.replace(" ", ""), "tail": tail})
    if any(p in chapter_prefixes for p in ("2",)):
        have = {t["table_id"] for t in titles}
        for mid in MANUAL_TITLES:
            if mid["table_id"] not in have:
                titles.append(mid)
        titles.sort(key=lambda t: (t["page"], t["y"]))
    return titles


MANUAL_TITLES = [
    {"table_id": "2-11", "page": 44, "y": 2073, "text": "表2-11", "tail": ""},
    {"table_id": "2-23", "page": 47, "y": 867, "text": "表2-23", "tail": ""},
]


def extract_words(page, y_from: float = 0.0):
    words = []
    h = page.rect.height
    for x0, y0, x1, y1, w, *_ in normalize_words(page):
        if y1 <= y_from + 2:
            continue
        if y0 > h - 300:
            continue
        if w.startswith("XR-TCO") or w == "新睿桥牌二盖一体系":
            continue
        words.append({"x": round(x0), "y": round(y0), "x1": round(x1), "w": fix_text(w)})
    return words


def batch_extract(doc, titles, gap, valid_ids):
    tables = []
    header_cache = {}
    for idx, t in enumerate(titles):
        table_id = t["table_id"]
        rows_out = []
        words_out = []
        pno = t["page"] - 1
        y_from = t["y"] + 15
        while pno < len(doc):
            rows = extract_rows(doc[pno], y_from, gap)
            words_out.extend({"page": pno + 1, **wd} for wd in extract_words(doc[pno], y_from))
            stopped = False
            for ry, cols in rows:
                if is_footer(cols):
                    continue
                if pno == t["page"] - 1 and ry <= t["y"] + 2:
                    continue
                text = row_text(cols)
                if re.match(r"^第[一二三四五六七八九十]+章", text.replace(" ", "")):
                    stopped = True
                    break
                parsed = parse_table_title(text, None)
                if parsed and has_header_below(doc, pno, ry, header_cache):
                    stopped = True
                    break
                rows_out.append({"y": ry, "cols": cols, "page": pno + 1})
            if stopped:
                break
            nxt = titles[idx + 1] if idx + 1 < len(titles) else None
            if nxt and nxt["page"] == pno + 1:
                break
            if pno + 1 >= len(doc):
                break
            pno += 1
            y_from = 0.0
        tables.append({"table_id": table_id, "title": t["text"], "page": t["page"], "tail": t["tail"],
                       "rows": rows_out, "words": words_out})
    return tables


def build_valid_ids(chapter):
    top = {"1": 6, "2": 80, "3": 80, "10": 70}
    n = top.get(chapter, 99)
    return {f"{chapter}-{i}" for i in range(1, n + 1)}


def main():
    doc = fitz.open(PDF)
    args = sys.argv[1:]
    if args and args[0] == "--page":
        for p in [int(x) for x in args[1].split(",")]:
            gap = float(args[2]) if len(args) > 2 else 90.0
            rows = extract_rows(doc[p - 1], gap=gap)
            print(f"--- pdf p{p} ---")
            for ry, cols in rows:
                print(ry, " | ".join(cols))
    elif args and args[0] == "--scan":
        prefixes = args[1].split(",") if len(args) > 1 else ["2"]
        prange = None
        if len(args) > 2:
            a, b = args[2].split("-")
            prange = (int(a), int(b))
        vid = set()
        for p in prefixes:
            vid |= build_valid_ids(p)
        titles = find_titles(doc, prefixes, vid, prange)
        for t in titles:
            print(t["page"], t["y"], t["table_id"], t["text"][:70])
    elif args and args[0] == "--batch":
        prefixes = args[1].split(",") if len(args) > 1 else ["2"]
        gap = float(args[2]) if len(args) > 2 else 60.0
        prange = None
        if len(args) > 3:
            a, b = args[3].split("-")
            prange = (int(a), int(b))
        vid = set()
        for p in prefixes:
            vid |= build_valid_ids(p)
        titles = find_titles(doc, prefixes, vid, prange)
        tables = batch_extract(doc, titles, gap, vid)
        out = OUT_DIR / f"tables_ch{'_'.join(prefixes)}.json"
        out.write_text(json.dumps(tables, ensure_ascii=False, indent=1), encoding="utf-8")
        print(f"saved {len(tables)} tables -> {out}")
        for tb in tables:
            print(tb["table_id"], f"p{tb['page']}", f"rows={len(tb['rows'])}")
    else:
        tid = args[0]
        hint = args[1] if len(args) > 1 else ""
        gap = float(args[2]) if len(args) > 2 else 90.0
        ch, num = tid.split("-")
        variants = [f"表{ch}-{num}", f"表 {ch}-{num}"]
        for pno in range(len(doc)):
            text = doc[pno].get_text()
            if not any(v in text for v in variants):
                continue
            if hint and hint not in text.replace(" ", ""):
                continue
            locs = doc[pno].search_for(variants[0]) or doc[pno].search_for(variants[1])
            title_y = locs[0].y1 if locs else 0
            rows = extract_rows(doc[pno], title_y, gap)
            print(f"--- 表{tid} ({hint}) pdf p{pno + 1} ---")
            for ry, cols in rows:
                print(ry, " | ".join(cols))


if __name__ == "__main__":
    main()
