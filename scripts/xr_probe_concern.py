import json
import re
from pathlib import Path

DATA = Path(__file__).resolve().parent / "xr_data"
PDF = DATA / "pdf_tables"

import sys
sys.path.insert(0, str(Path(__file__).resolve().parent))
import xr_build_tree as B
import xr_build_all as A

tables = A.load_tables()
seq = json.loads((DATA / "tables_seq.json").read_text(encoding="utf-8"))
seq.update(A.MANUAL_SEQ)

# filtered 逻辑与 xr_build_all.main 一致
filtered = {}
for ch, prefixes in A.CH_TOPIC.items():
    for tid in list(seq):
        if not tid.startswith(f"{ch}-"):
            continue
        s = seq[tid]
        first = s.split("-")[0]
        if s.startswith(prefixes):
            filtered[tid] = s
B.TABLE_SEQ.update(filtered)

# 找出 F 类（未入树、非重复、非主题不符-drop）
presumed = set()
for ch, prefixes in A.CH_TOPIC.items():
    for tid in list(seq):
        if not tid.startswith(f"{ch}-"):
            continue
        s = seq[tid]
        if not s.startswith(prefixes):
            presumed.add(tid)

fallback = []
for f in sorted(PDF.glob("tables_ch*.json")):
    for t in json.loads(f.read_text(encoding="utf-8")):
        tid = t["table_id"]
        if tid in B.TABLE_SEQ:
            continue
        fallback.append(t)

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

by = {}
for t in fallback:
    c = classify(t["table_id"], t)
    by.setdefault(c, []).append(t["table_id"])

for c, ids in by.items():
    print(f"{c} = {len(ids)}")

print("\n===== 无干扰后续(疑缺口) 的 title =====")
for t in fallback:
    if classify(t["table_id"], t) == "无干扰后续(疑缺口)":
        print(f"{t['table_id']} | seq={seq.get(t['table_id'],'-')!r} | title={t.get('title','')!r} | tail={t.get('tail','')!r}")