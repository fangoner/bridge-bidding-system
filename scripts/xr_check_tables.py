import json
import sys
from pathlib import Path

BASE = Path(__file__).resolve().parent.parent
path = BASE / "scripts" / "xr_data" / "pdf_tables" / "tables_ch2.json"
data = json.loads(path.read_text(encoding="utf-8"))
ids = sys.argv[1].split(",") if len(sys.argv) > 1 else ["2-1"]
limit = int(sys.argv[2]) if len(sys.argv) > 2 else 30
for tid in ids:
    matches = [t for t in data if t["table_id"] == tid]
    if not matches:
        print(f"=== {tid} NOT FOUND")
        continue
    tb = matches[0]
    print(f"=== {tid} {tb['title']} p{tb['page']} rows={len(tb['rows'])}")
    for r in tb["rows"][:limit]:
        print(" ", r["y"], " | ".join(r["cols"]))
