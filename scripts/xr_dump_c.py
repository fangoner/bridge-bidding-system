import sys, json
sys.path.insert(0, r"d:\Bridge Card\Bidding System\scripts")
import xr_build_all as A
import xr_build_tree as B

DATA = r"d:\Bridge Card\Bidding System\scripts\xr_data"

tables = A.load_tables()
seq = json.loads(open(DATA + "/tables_seq.json", encoding="utf-8").read())
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
parsed, _ = B.dedup_ownership(parsed)
for tid in B.MANUAL_TABLES:
    parsed[tid] = list(B.MANUAL_TABLES[tid])
order = sorted(tables, key=lambda t: (int(t.split("-")[0]), int(t.split("-")[1])))
for tid in order:
    for e in parsed.get(tid, []):
        B.derive_bids_from_links(e, tid)
    B.fix_entry_bids(tid, parsed.get(tid, []))

import re
MERGE_PAT = re.compile(r"(逼局不逼叫|不逼叫逼局|逼局邀请|邀请逼局|逼局止叫|邀请不逼叫|不逼叫邀请|逼局逼局|止叫逼局|逼局5张|5张以上♥，邀请6|，邀请5|，逼局5张)")
for tid in order:
    if tid.split("-")[0] not in A.CH_TOPIC:
        continue
    sq = B.TABLE_SEQ.get(tid, "?")
    for e in parsed.get(tid, []):
        if e["bids"] and not e["points"]:
            print(f'{tid}\tseq={sq}\t{"".join(e["bids"])}\t{e["desc"][:60]}')