import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import xr_build_tree as B

DATA = Path(__file__).resolve().parent / "xr_data"
PDF = DATA / "pdf_tables"

CAND = {
    "4-26": "1H-2D", "4-42": "1H-3NT",
    "5-22": "1S-2D", "5-26": "1S-2H",
    "7-11": "2C-2NT", "7-12": "2C-2NT", "7-15": "2C-2S",
    "7-16": "2C-3C", "7-17": "2C-3D",
    "8-11": "2NT-3D", "8-17": "2NT-3H",
    "9-11": "2S-3D",
}

tables = {}
for f in sorted(PDF.glob("tables_ch*.json")):
    for t in json.loads(f.read_text(encoding="utf-8")):
        tables[t["table_id"]] = t

for tid, cand_seq in CAND.items():
    tb = tables.get(tid)
    if not tb:
        print(f"{tid} MISSING")
        continue
    B.TABLE_SEQ[tid] = cand_seq
    entries = B.parse_table(tb)
    B.derive_bids_from_links(entries[0], tid) if False else None
    for e in entries:
        B.derive_bids_from_links(e, tid)
    B.fix_entry_bids(tid, entries)
    last = B.last_bid_of_seq(cand_seq)
    bids = [b for e in entries for b in e["bids"]][:12]
    above = [b for b in [be for e in entries for be in e["bids"]] if B.bid_rank(b) >= 0]
    bad = [b for b in above if B.bid_rank(b) <= B.bid_rank(last)]
    print(f"{tid} seq={cand_seq!r} last={last!r} n_entries={len(entries)} bids={bids} 低于末叫: {bad}")