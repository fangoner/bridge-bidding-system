import sys, json
from pathlib import Path
sys.path.insert(0, r"d:\Bridge Card\Bidding System\scripts")
import xr_build_all as A
import xr_build_tree as B

DATA = Path(r"d:\Bridge Card\Bidding System\scripts\xr_data")

def full_setup():
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
    parsed = {tid: B.parse_table(tb) for tid, tb in tables.items()}
    parsed, dropped = B.dedup_ownership(parsed)
    for tid in B.MANUAL_TABLES:
        parsed[tid] = list(B.MANUAL_TABLES[tid])
    order = sorted(tables, key=lambda t: (int(t.split("-")[0]), int(t.split("-")[1])))
    for tid in order:
        for e in parsed.get(tid, []):
            B.derive_bids_from_links(e, tid)
        B.fix_entry_bids(tid, parsed.get(tid, []))
    return tables, parsed, order

if __name__ == "__main__":
    tables, parsed, order = full_setup()
    tids = sys.argv[1:] if len(sys.argv) > 1 else ["7-6"]
    for tid in tids:
        print(f"===== 表{tid}  seq={B.TABLE_SEQ.get(tid,'?')} =====")
        for e in parsed.get(tid, []):
            print(f"  bids={e['bids']} pts={e['points']!r} raw={e['raw']!r} links={e['links']} y={e.get('y')} page={e.get('page')}")
            print(f"      desc={e['desc'][:80]}")