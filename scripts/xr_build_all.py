import json
import re
from pathlib import Path

import xr_build_tree as B

DATA = Path(__file__).resolve().parent.parent / "scripts" / "xr_data"
PDF = DATA / "pdf_tables"
OUT_MD = DATA / "新睿实战_二盖一体系.md"
OUT_JSON = DATA / "tables_built.json"

OPENINGS = [
    (["1C"], "2-1", "2-2", "1C开叫"),
    (["1D"], "3-1", "3-2", "1D开叫"),
    (["1H"], "4-1", "4-2", "1H开叫"),
    (["1S"], "5-1", "5-2", "1S开叫"),
    (["1NT"], "6-1", None, "1NT开叫"),
    (["2C"], "7-1", None, "2C开叫"),
    (["2NT"], "8-1", None, "2NT开叫"),
    (["2D", "2H", "2S"], "9-1", None, "2D/2H/2S开叫"),
]

CH_TOPIC = {
    "2": ("1C",), "3": ("1D",), "4": ("1H",), "5": ("1S",),
    "6": ("1NT",), "7": ("2C",), "8": ("2NT",),
    "9": ("2D", "2H", "2S", "3C", "3D", "3H", "3S", "3NT",
          "4C", "4D", "4H", "4S", "4NT", "5C", "5D", "5H", "5S", "5NT"),
}

MANUAL_SEQ = {
    "3-1": "1D", "5-1": "1S", "6-1": "1NT", "8-1": "2NT",
    "4-1": "1H", "4-2": "1H-3rd", "7-1": "2C",
    # E类续写表 seq 修正（OCR 索引被截为两叫，据原文/上下文补全，避免与真根表 seq 重复）
    "3-12": "1D-1S-2S",
    "3-26": "1D-2C",
    "3-42": "1D-3D",
    "3-51": "1D-1S-2NT",
    "3-52": "1D-1S-2NT-3C",
    "3-54": "1D-1H-3C",
    "3-57": "1D-1H-3D",
    "3-59": "1D-1S-3D",
    "4-6": "1H-1S-2H",
    "5-20": "1S-2D-2NT",
    "5-39": "1S-3S-4D",
    # 1NT/2NT 约定叫分支：6-9/6-21/8-18 为应叫人续写表（OCR 截断为 2 叫，与真根表重复）
    "6-9": "1NT-2C-2D",
    "6-21": "1NT-2H-2S",
    "8-2": "2NT-3C",
    "8-18": "2NT-3C-3D",
    # 无干扰后续表 F类：标题可自动解析（OCR 尾部标题含可靠叫牌序列）→ 补 seq 挂主树
    "4-26": "1H-2D",
    "4-42": "1H-3NT",
    "5-22": "1S-2D",
    "5-26": "1S-2H",
    "7-11": "2C-2NT",
    "7-12": "2C-2NT",
    "7-15": "2C-2S",
    "7-16": "2C-3C",
    "7-17": "2C-3D",
    "8-11": "2NT-3D",
    "8-17": "2NT-3H",
    "9-11": "2S-3D",
}

# 表1-4 开叫总表 → "花色开叫" 平铺段（空叫牌序列检索入口）
# 每行：开叫[(/开叫)]：点力，说明（参考表）
OPENING_TOTAL = [
    ("pass", "0~11", "均型牌", ""),
    ("1C/1D", "12~21", "3张以上♣或♦，没有5张高花套", "表2-1/3-1"),
    ("1H/1S", "12~21", "5张以上♥或♠套", "表4-1/5-1"),
    ("1NT", "15~17", "均型牌，允许有5张高花套", "表6-1"),
    ("2C", "22", "任意牌型，9赢墩以上时可18点以上", "表7-1"),
    ("2D/2H/2S", "6~10", "6张以上♦或♥或♠好套", "表9-1/2/3"),
    ("2NT", "20~21", "均型牌，允许有5张高花套", "表8-1"),
    ("3C/3D/3H/3S", "6~10", "7张好套，阻击叫", "表9-15"),
    ("3NT", "9~12", "赌博性，7张坚强低花套", "表9-16"),
    ("4C/4D/4H/4S", "6~10", "8张好套，阻击叫", ""),
    ("5C/5D", "6~10", "9张好套，或8张有单缺，阻击叫", ""),
]
OPENING_TOTAL_TABLES = {"1-4"}


def load_tables():
    tables = {}
    for f in sorted(PDF.glob("tables_ch*.json")):
        for t in json.loads(f.read_text(encoding="utf-8")):
            tid = t["table_id"]
            if t.get("secondary"):
                B.SECONDARY_TABLES.add(tid)
            if tid in tables:
                tables[tid]["words"].extend(t.get("words", []))
            else:
                tables[tid] = t
    return tables


def render_opening_total():
    lines = ["花色开叫", "新睿二盖一体系：开叫条件总表（表1-4）"]
    for bid, pts, desc, ref in OPENING_TOTAL:
        meta = [pts + "点"] if pts else []
        if desc:
            meta.append(desc)
        if ref:
            meta.append(ref)
        lines.append(f"{bid}：{'，'.join(meta)}")
    return lines


def render_response(openings, oid, o3rd, kw, parsed, tables):
    lines = []
    if oid in parsed:
        lines.append(kw)
        lines.append(f"新睿二盖一体系：{'/'.join(openings)}开叫后的应叫（表{oid}）")
        for e in parsed[oid]:
            if not e["bids"]:
                continue
            bid = e["bids"][0]
            meta = [e["points"] + "点"] if e["points"] else []
            if e["desc"]:
                meta.append(e["desc"])
            mark = "〔OCR校正〕" if e.get("fixed_bid") else ""
            lines.append(f"{openings[0]}-{bid}：{'，'.join(meta)}{mark}")
    if o3rd and o3rd in parsed:
        base = openings[0]
        for e in parsed[o3rd]:
            if not e["bids"]:
                continue
            meta = [e["points"] + "点"] if e["points"] else []
            if e["desc"]:
                meta.append(e["desc"])
            lines.append(f"第三四家开叫{base}时：应叫{e['bids'][0]}，{'，'.join(meta)}（表{o3rd}）")
    return lines


def _root_table_seq(tid):
    parts = [p for p in B.TABLE_SEQ.get(tid, "").split("-") if p != "3rd"]
    if len(parts) == 2 and all(p not in ("pass", "X", "XX") for p in parts):
        return "-".join(parts)
    return None


def _pick_canonical(group, parsed):
    """同一 seq 出现多个根表时，选首层叫品最多、且最低叫品最底的作为主干根表。
    其余表（多为续写/进局逼叫表，OCR 索引被截为两叫）移入兜底保留，供人工校对。"""
    def score(tid):
        entries = parsed.get(tid, [])
        bids = [b for e in entries for b in e["bids"]]
        n = len(bids)
        low = min((B.bid_rank(b) for b in bids if B.bid_rank(b) >= 0), default=10 ** 9)
        return (n, -low, tid)
    return max(group, key=score)


def render_trees(openings, tables, parsed):
    roots = []
    for tid in tables:
        seq = _root_table_seq(tid)
        if seq and seq.split("-")[0] in openings:
            roots.append(tid)
    roots.sort(key=lambda t: (int(t.split("-")[1]), t))

    by_seq = {}
    for rt in roots:
        by_seq.setdefault(_root_table_seq(rt), []).append(rt)

    suppressed = []
    segs = []
    for seq, group in by_seq.items():
        canonical = _pick_canonical(group, parsed)
        for rt in group:
            if rt != canonical:
                suppressed.append(rt)
                print(f"  [dup-seq] {rt}: {seq} -> 兜底保留（主干取 {canonical}）")
        kw = B.TABLE_SEQ[canonical]
        try:
            nodes = B.build_tree_node(canonical, tables, set(), parsed)
        except Exception as ex:
            print(f"  !! tree build fail {canonical}: {ex}")
            continue
        lines = [kw, f"新睿二盖一体系：{kw} 开叫人再叫及后续（表{canonical}）"]
        B.render_tree_nodes(nodes, 0, lines)
        segs.append("\n".join(lines))
    return segs, suppressed


def render_fallback(parsed, tables, suppressed=None):
    # seq 缺失（干扰/应叫总表/无法解析）→ 平铺兜底段，保留全部内容供人工核对
    suppressed = suppressed or []
    segs = []
    by_ch = {}
    for tid in sorted(tables, key=lambda t: (int(t.split("-")[0]), int(t.split("-")[1]))):
        if tid in B.TABLE_SEQ and tid not in suppressed:
            continue
        if tid in OPENING_TOTAL_TABLES:
            continue
        ch = tid.split("-")[0]
        by_ch.setdefault(ch, []).append(tid)
    for ch in sorted(by_ch, key=int):
        dup = [tid for tid in by_ch[ch] if tid in suppressed]
        lines = [f"第{ch}章 未结构化表（SEQ缺失/干扰/参考，兜底）", f"新睿二盖一体系：第{ch}章未结构化表（{len(by_ch[ch])}个）"]
        if dup:
            lines.append(f"含 {len(dup)} 个 seq 重复续写表（已保留全文，待人工校对正确序列）：{'、'.join(dup)}")
        for tid in by_ch[ch]:
            rendered_now = 0
            for e in parsed.get(tid, []):
                if not e["bids"] and not e["desc"]:
                    continue
                bid = "/".join(e["bids"]) if e["bids"] else "?"
                meta = [e["points"] + "点"] if e["points"] else []
                if e["desc"]:
                    meta.append(e["desc"])
                lines.append(f"表{tid} {bid}：{'，'.join(meta)}")
                rendered_now += 1
            # 参考章（首攻/信号/约定叫注释）或没有可读叫品条目的表 → 追加转储原始行文本，避免内容丢失
            always_raw = ch in ("12", "13")
            if always_raw or rendered_now == 0:
                tb = tables.get(tid, {})
                dumped = 0
                for r in tb.get("rows", []):
                    cols = " ".join(str(c).strip() for c in r.get("cols", []) if str(c).strip())
                    if cols:
                        lines.append(f"表{tid} {cols}")
                        dumped += 1
                if not dumped:
                    words = " ".join(w["w"] for w in tb.get("words", []) if w.get("w"))
                    if words:
                        lines.append(f"表{tid} {words}")
                        dumped += 1
                if always_raw and rendered_now:
                    lines.append(f"表{tid} 〔以上为原始行转储，供人工校对；上列叫品条目仅供参考〕")
        segs.append("\n".join(lines))
    return segs


def main():
    tables = load_tables()
    seq = json.loads((DATA / "tables_seq.json").read_text(encoding="utf-8"))
    seq.update(MANUAL_SEQ)
    filtered = {}
    for ch, prefixes in CH_TOPIC.items():
        for tid in list(seq):
            if not tid.startswith(f"{ch}-"):
                continue
            s = seq[tid]
            first = s.split("-")[0]
            if s.startswith(prefixes):
                filtered[tid] = s
            else:
                print(f"  [seq-drop] {tid}: {s} (章{ch}主题不符 → 兜底)")
    B.TABLE_SEQ.update(filtered)

    parsed = {tid: B.parse_table(tb) for tid, tb in tables.items()}
    parsed, dropped = B.dedup_ownership(parsed)
    print(f"dedup: entries dropped {sum(len(v) for v in dropped.values())}")

    for tid in B.MANUAL_TABLES:
        parsed[tid] = list(B.MANUAL_TABLES[tid])
    order = sorted(tables, key=lambda t: (int(t.split("-")[0]), int(t.split("-")[1])))
    for tid in order:
        for e in parsed.get(tid, []):
            B.derive_bids_from_links(e, tid)
        B.fix_entry_bids(tid, parsed.get(tid, []))

    no_bid = [(tid, e) for tid in order for e in parsed[tid] if not e["bids"]]
    print(f"tables={len(tables)} entries={sum(len(v) for v in parsed.values())} no-bid={len(no_bid)}")

    segs = []
    segs.append("\n".join(render_opening_total()))
    trees_out = {}
    all_suppressed = []
    for openings, oid, o3rd, kw in OPENINGS:
        segs.append("\n".join(render_response(openings, oid, o3rd, kw, parsed, tables)))
        tsegs, suppressed = render_trees(openings, tables, parsed)
        segs.extend(tsegs)
        all_suppressed.extend(suppressed)
        trees_out[kw] = {
            "openings": openings,
            "response_table": oid,
            "roots": [B.TABLE_SEQ[rt] for rt in
                      [t for t in tables if len([p for p in B.TABLE_SEQ.get(t, "").split("-") if p not in ("3rd", "pass", "X", "XX")]) == 2
                       and B.TABLE_SEQ.get(t, "").split("-")[0] in openings
                       and t not in all_suppressed]],
        }

    segs.extend(render_fallback(parsed, tables, all_suppressed))

    OUT_MD.write_text("\n\n\n".join(segs) + "\n", encoding="utf-8")
    built = {"tables": parsed, "trees": trees_out}
    OUT_JSON.write_text(json.dumps(built, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"saved -> {OUT_MD}")
    print(f"saved -> {OUT_JSON}")


if __name__ == "__main__":
    main()