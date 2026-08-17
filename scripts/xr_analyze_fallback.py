import sys, json, re
from pathlib import Path
sys.path.insert(0, r"d:\Bridge Card\Bidding System\scripts")
import xr_build_all as A
import xr_build_tree as B

DATA = Path(r"d:\Bridge Card\Bidding System\scripts\xr_data")
tables = A.load_tables()
seq = json.loads((DATA / "tables_seq.json").read_text(encoding="utf-8"))
seq.update(A.MANUAL_SEQ)
filtered = {}
for ch, prefixes in A.CH_TOPIC.items():
    for tid in list(seq):
        if not tid.startswith(ch + "-"):
            continue
        s = seq[tid]
        if s.startswith(prefixes):
            filtered[tid] = s
B.TABLE_SEQ.update(filtered)

# 兜底表 = 不在 TABLE_SEQ 且不在 OPENING_TOTAL_TABLES 的表
fallback = []
suppressed_fallback = []
for tid in sorted(tables, key=lambda t: (int(t.split("-")[0]), int(t.split("-")[1]))):
    if tid in B.TABLE_SEQ:
        continue
    if tid in A.OPENING_TOTAL_TABLES:
        continue
    fallback.append(tid)

# 分类
INTER = re.compile(r"\([^)]*\)|迈克尔斯|特殊2NT|兰迪|德鲁里|问A|问K|问将牌|问边花|格伯|罗马|首攻|信号|争叫")
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

cat = {}
by_tid = {}
for tid in fallback:
    tb = tables[tid]
    c = classify(tid, tb)
    cat[c] = cat.get(c, 0) + 1
    by_tid[tid] = c

total_entries = 0
for tid in fallback:
    for e in B.parse_table(tables[tid]):
        if e["bids"] or e["desc"]:
            total_entries += 1

print("=== 兜底表总数:", len(fallback), "===")
print("=== 兜底可读条目(entry)总数:", total_entries, "===")
for c, n in sorted(cat.items(), key=lambda x: -x[1]):
    print(f"  {c}: {n}")

print("\n=== 无干扰后续(疑缺口) 明细 ===")
for tid in sorted(fallback, key=lambda t: (int(t.split("-")[0]), int(t.split("-")[1]))):
    if by_tid[tid] == "无干扰后续(疑缺口)":
        print(f"  {tid}\t{tables[tid].get('title','')[:40]}")