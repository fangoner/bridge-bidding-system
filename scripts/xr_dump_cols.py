import json
import sys
from pathlib import Path

BASE = Path(__file__).resolve().parent.parent
data = json.loads((BASE / "scripts" / "xr_data" / "pdf_tables" / "tables_ch2.json").read_text(encoding="utf-8"))
tid = sys.argv[1] if len(sys.argv) > 1 else "2-1"
tb = [t for t in data if t["table_id"] == tid][0]
words = sorted(tb["words"], key=lambda w: (w["y"], w["x"]))
colw = int(sys.argv[2]) if len(sys.argv) > 2 else 120
cols = {}
for w in words:
    key = w["x"] // colw
    cols.setdefault(key, []).append(w)
for key in sorted(cols):
    ws = cols[key]
    xs = [w["x"] for w in ws]
    print(f"--- col x~{key * colw}-{(key + 1) * colw} n={len(ws)} xrange={min(xs)}-{max(xs)}")
    line = " ".join(f"[{w['y']}]{w['w']}" for w in ws)
    print(line[:1500])
