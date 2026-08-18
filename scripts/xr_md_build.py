import json
import re
from pathlib import Path

DATA = Path(__file__).resolve().parent / "xr_data"
IN = DATA / "md_tables.json"
OUT_MD = DATA / "新睿实战_二盖一体系.md"

OPENINGS = [
    ("2-1", "1C", "1C开叫"),
    ("3-1", "1D", "1D开叫"),
    ("4-1", "1H", "1H开叫"),
    ("5-1", "1S", "1S开叫"),
    ("6-1", "1NT", "1NT开叫"),
    ("7-1", "2C", "2C开叫"),
    ("8-1", "2NT", "2NT开叫"),
    ("9-1", "2D", "2D开叫"),
    ("9-2", "2H", "2H开叫"),
    ("9-3", "2S", "2S开叫"),
]


def _loader_seq(s):
    """把 canon 形式 seq 还原为 JF 文档连字符分隔形式（敌括号前补 -）：
    1NT(2C) -> 1NT-(2C)，1D-1H(2C) -> 1D-1H-(2C)。"""
    if not s:
        return s
    return re.sub(r"([1-7](?:C|D|H|S|NT))(\()", r"\1-(", s)


def render_seq_segment(tid, tb, kw=None, seq_header=None):
    """render one seq table as an independent JF-style segment.

    - opening root tables: keyword row ``1C开叫``
    - continuation tables: header = ``<seq>`` row
    - entries: each a level-0 ``├bid：points，desc`` line (no cross-table merge)
    """
    title = (tb["title"] or "").strip()
    lines = []
    if kw:
        lines.append(kw)
        if title:
            lines.append(title)
    else:
        lines.append(seq_header if seq_header is not None else tb["seq"])
        if title:
            lines.append(title)
    for e in tb["entries"]:
        if not e["bids"]:
            continue
        bid_str = "/".join(e["bids"])
        meta = []
        if e["points"]:
            meta.append(e["points"] + "点")
        if e["desc"]:
            meta.append(e["desc"])
        lines.append(f"├{bid_str}：" + "，".join(meta))
    return "\n".join(lines)


def opening_suit_segment(md):
    """chapter-1 opening overview table -> flat ``花色开叫`` segment."""
    t = md.get("1-4")
    if not t:
        return ""
    lines = ["花色开叫", "新睿二盖一体系：开叫条件总表（表1-4）"]
    for e in t["entries"]:
        bid_str = "/".join(e["bids"]) if e["bids"] else ""
        meta = []
        if e["points"]:
            meta.append(e["points"] + "点")
        if e["desc"]:
            meta.append(e["desc"])
        if bid_str:
            lines.append(f"{bid_str}：{'，'.join(meta)}")
        else:
            lines.append("，".join(meta))
    return "\n".join(lines)


def flat_segment(head, lines):
    return "\n".join([head] + lines)


def dump_deprecated(tables, title):
    """unstructured/ambiguous leftovers -> flat info segment, no tree."""
    lines = [title]
    for tid, tb in sorted(tables.items(), key=lambda kv: kv[0]):
        lines.append(f"· 表{tid} {tb['title'] or ''}".rstrip())
        for e in tb["entries"]:
            bid_str = "/".join(e["bids"]) if e["bids"] else ""
            meta = []
            if e["points"]:
                meta.append(e["points"] + "点")
            if e["desc"]:
                meta.append(e["desc"])
            if bid_str or meta:
                lines.append(f"  - {bid_str}：{'，'.join(meta)}" if bid_str
                             else f"  - {'，'.join(meta)}")
    return flat_segment(title, lines)


def main():
    md = json.loads(IN.read_text(encoding="utf-8"))
    SEQ_INDEX = {}
    for tid, tb in md.items():
        seqs = tb["seq"]
        if not seqs:
            continue
        if isinstance(seqs, str):
            seqs = [seqs]
        for s in seqs:
            if s:
                SEQ_INDEX.setdefault(s, []).append(tid)
    FIRST = {s: sorted(v)[0] for s, v in SEQ_INDEX.items()}

    covered = set()
    segs = [opening_suit_segment(md)]
    for root_tid, root_seq, kw in OPENINGS:
        tb = md.get(root_tid)
        if not tb:
            continue
        covered.add(root_tid)
        segs.append(render_seq_segment(root_tid, tb, kw=kw))

    for s in sorted(SEQ_INDEX, key=lambda kv: kv):
        if len(s.split("-")) < 2:
            continue
        tid = FIRST[s]
        covered.add(tid)
        segs.append(render_seq_segment(tid, md[tid], kw=None, seq_header=_loader_seq(s)))

    deprecated_tids = set()
    for s, v in SEQ_INDEX.items():
        if len(s.split("-")) >= 2:
            for t in v:
                if t != FIRST[s]:
                    deprecated_tids.add(t)
        else:
            for t in v:
                if t not in covered:
                    deprecated_tids.add(t)
    for tid, tb in md.items():
        if not tb["seq"]:
            deprecated_tids.add(tid)

    for ch in ["1", "2", "3", "4", "5", "6", "7", "8", "9", "10", "11", "12", "13"]:
        chap = {t: tb for t, tb in md.items()
                if t in deprecated_tids and t.startswith(ch + "-")}
        if chap:
            segs.append(dump_deprecated(chap, f"第{ch}章 未结构化表（兜底）"))

    segs = [s for s in segs if s.strip()]
    OUT_MD.write_text("\n\n\n".join(segs) + "\n", encoding="utf-8")
    print(f"segments={len(segs)} covered={len(covered)} "
          f"deprecated={len(deprecated_tids)}")
    for s in segs[:4]:
        print("\n----- segment preview -----")
        print(s[:600])
    print(f"saved -> {OUT_MD}")

    report(md, SEQ_INDEX, FIRST, covered, deprecated_tids)


def report(md, SEQ_INDEX, FIRST, covered, deprecated_tids):
    """leftover issues to human review."""
    lines = []
    lines.append("# 新睿二盖一体系 全量重建人工核对清单")
    lines.append("")
    lines.append("> 由《新睿自然.md》新版全量自动解析重建，程序识别出的遗留问题需人工对照原文判定。")
    lines.append("")
    lines.append("## A. 同 seq 多表（歧义。仅挂表id最小者入树，其余以下原文兜底保留）")
    for s, v in sorted(SEQ_INDEX.items(), key=lambda kv: kv[0]):
        if len(v) > 1:
            lines.append(f"- `{s}` -> 挂 `{sorted(v)[0]}`，其余待定 {v}")
    lines.append("")
    lines.append("## B. 无 seq 表 / 单叫品非开叫 / 歧义次位（整体不入树，兜底保留）")
    lines.append(f"共 {len(deprecated_tids)} 张：`{', '.join(sorted(deprecated_tids))}`")
    lines.append("")
    lines.append("## C. 含无叫品条目的表（条目缺叫品列，仅描述/说明，需人工核对是否漏列叫品）")
    nobid_tables = sorted({tid for tid, t in md.items() for e in t["entries"] if not e["bids"]},
                          key=lambda x: (int(x.split('-')[0]), int(x.split('-')[1])))
    lines.append(f"共 {len(nobid_tables)} 张：`{', '.join(nobid_tables)}`")
    lines.append("")
    OUT_CK = DATA / "新睿全量人工核对清单.md"
    OUT_CK.write_text("\n".join(lines), encoding="utf-8")
    print(f"saved checklist -> {OUT_CK}")


if __name__ == "__main__":
    main()