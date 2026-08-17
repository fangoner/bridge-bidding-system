import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import xr_build_tree as B
import xr_build_all as A

DATA = Path(__file__).resolve().parent / "xr_data"
PDF = DATA / "pdf_tables"

tables = A.load_tables()
seq = json.loads((DATA / "tables_seq.json").read_text(encoding="utf-8"))
seq.update(A.MANUAL_SEQ)
filtered = {}
for ch, prefixes in A.CH_TOPIC.items():
    for tid in list(seq):
        if not tid.startswith(f"{ch}-"):
            continue
        if seq[tid].startswith(prefixes):
            filtered[tid] = seq[tid]
B.TABLE_SEQ.update(filtered)

def classify(tid, tb):
    title = tb.get("title", "")
    if "争叫" in title or "第二位置" in title or "第四位置" in title:
        return "防守争叫"
    if "首攻" in title or "信号" in title:
        return "首攻/信号"
    if "问A" in title or "问K" in title or "格伯" in title or "罗马" in title or "问将牌" in title or "问边花" in title:
        return "满贯问叫"
    if re.search(r"[（(][^）)]*[）)]", title):
        return "敌方干扰后续"
    if "迈克尔斯" in title or "特殊2NT" in title or "兰迪" in title or "德鲁里" in title:
        return "敌方干扰后续"
    return "无干扰后续(疑缺口)"

FALLBACK = [t for f in sorted(PDF.glob("tables_ch*.json")) for t in json.loads(f.read_text(encoding="utf-8")) if t["table_id"] not in B.TABLE_SEQ]

OPENING_PREFIX = {}
for ch, prefixes in A.CH_TOPIC.items():
    for p in prefixes:
        OPENING_PREFIX[p] = ch

def extract_seq_from_tail(tail):
    s = B.clean_text(tail)
    s = B.CLUB_OCR.sub("\u2663", s)
    s = s.replace("\u2014", "-").replace("\uff0d", "-").replace("－", "-").replace("一", "-")
    s = re.sub(r"^[-~~～·.:;\uff1b，,、\s]+", "", s)
    s = re.sub(r"(后续|都是进局逼叫|说明.*|争叫|。|．|！).*$", "", s)
    # 提取连续 bid token
    toks = []
    for part in s.split("-"):
        part = part.strip()
        b = B.parse_bid_token(part)
        if not b:
            return None
        toks.append(b)
    if not toks:
        return None
    return "-".join(toks)

rows = []
for t in sorted(FALLBACK, key=lambda x: (int(x["table_id"].split("-")[0]), int(re.match(r"\d+", x["table_id"].split("-")[1]).group()))):
    if classify(t["table_id"], t) != "无干扰后续(疑缺口)":
        continue
    tid = t["table_id"]
    tail = t.get("tail", "")
    got = extract_seq_from_tail(tail)
    ch = tid.split("-")[0]
    first = got.split("-")[0] if got else None
    ok = got is not None and first and OPENING_PREFIX.get(first) == ch
    rows.append((tid, got, ok, t.get("title", ""), tail))

print(f"共 {len(rows)} 个无干扰后续表")
n_ok = sum(1 for r in rows if r[2])
print(f"标题可解析且首叫匹配本章 = {n_ok}\n")
for tid, got, ok, title, tail in rows:
    print(f"{tid} | seq={got!r} | {'OK' if ok else '??'} | tail={tail!r}")