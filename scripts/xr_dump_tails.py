import json
from pathlib import Path

BASE = Path(__file__).resolve().parent.parent
PDF_DIR = BASE / "scripts" / "xr_data" / "pdf_tables"
files = sorted([f for f in PDF_DIR.glob("tables_ch*.json")])
for f in files:
    data = json.loads(f.read_text(encoding="utf-8"))
    print(f"=== {f.name} ({len(data)}) ===")
    for tb in data:
        print(f"  {tb['table_id']} p{tb['page']} rows={len(tb['rows'])} tail={tb['tail']!r} title={tb['title'][:40]!r}")