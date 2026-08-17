import json
import sys
from pathlib import Path

import fitz

BASE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(Path(__file__).resolve().parent))
import xr_pdf_rebuild as P

PDF = BASE / "书籍" / "新睿桥牌二盖一体系.pdf"
OUT_DIR = BASE / "scripts" / "xr_data" / "pdf_tables"

BACKFILL = [
    {"table_id": "4-1", "page": 120, "y_from": 593, "y_to": 2970,
     "title": "表4-1 1♥开叫后续", "tail": "1♥开叫后续"},
    {"table_id": "4-2", "page": 121, "y_from": 439, "y_to": 1230,
     "title": "表4-2 第三四家开叫1♥后，应叫与一二家开叫的不同", "tail": "第三四家开叫1♥后，应叫与一二家开叫的不同"},
    {"table_id": "7-1", "page": 202, "y_from": 1865, "y_to": 2850,
     "title": "表7-1 2♣开叫后续", "tail": "2♣开叫后续"},
]


def extract_words_range(page, y_from, y_to):
    words = []
    h = page.rect.height
    for x0, y0, x1, y1, w, *_ in P.normalize_words(page):
        if y1 <= y_from + 2 or y0 >= y_to:
            continue
        if y0 > h - 300:
            continue
        if w.startswith("XR-TCO") or w == "新睿桥牌二盖一体系":
            continue
        words.append({"x": round(x0), "y": round(y0), "x1": round(x1), "w": P.fix_text(w)})
    return words


def main():
    doc = fitz.open(PDF)
    for fb in BACKFILL:
        page = doc[fb["page"] - 1]
        words = extract_words_range(page, fb["y_from"], fb["y_to"])
        tb = {
            "table_id": fb["table_id"],
            "title": fb["title"],
            "page": fb["page"],
            "tail": fb["tail"],
            "rows": [],
            "words": [{"page": fb["page"], **wd} for wd in words],
        }
        ch = fb["table_id"].split("-")[0]
        out = OUT_DIR / ("tables_ch7_8.json" if ch == "7" else f"tables_ch{ch}.json")
        data = json.loads(out.read_text(encoding="utf-8"))
        data = [t for t in data if t["table_id"] != fb["table_id"]]
        data.append(tb)
        data.sort(key=lambda t: int(t["table_id"].split("-")[1]))
        out.write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")
        print(f"backfilled {fb['table_id']} p{fb['page']} words={len(words)} -> {out.name}")


if __name__ == "__main__":
    main()