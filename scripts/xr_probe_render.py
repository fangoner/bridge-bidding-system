import json
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

from xr_build_all import load_tables
tables = load_tables()
parsed = {tid: B.parse_table(tb) for tid, tb in tables.items()}
parsed, _ = B.dedup_ownership(parsed)

for tid in sorted(CAND, key=lambda t: (int(t.split("-")[0]), int(t.split("-")[1]))):
    B.TABLE_SEQ[tid] = CAND[tid]
    for pp in parsed:
        for e in parsed[pp]:
            B.derive_bids_from_links(e, pp)
    for pp in sorted(parsed):
        B.fix_entry_bids(pp, parsed.get(pp, []))
    last = B.last_bid_of_seq(B.TABLE_SEQ[tid])
    nodes = B.build_tree_node(tid, tables, set(), parsed)
    lines = []
    B.render_tree_nodes(nodes, 0, lines)
    bad = [l for l in lines if l.strip().startswith("├") and last and (lambda b: b != "pass" and b not in ("X","XX") and B.bid_rank(b)<B.bid_rank(last))(l.lstrip('├│----').split("：")[0].split("/")[0])]
    print(f"\n===== {tid} [{CAND[tid]}] last={last} 非法行={len(bad)} =====")
    for l in lines[:14]:
        print("   " + l)