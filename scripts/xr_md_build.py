import json
import re
from pathlib import Path

DATA = Path(__file__).resolve().parent / "xr_data"
IN = DATA / "md_tables.json"
OUT_MD = DATA / "新睿实战_二盖一体系.md"

ORDER = {"C": 0, "D": 1, "H": 2, "S": 3, "NT": 4}


def bid_sort_key(bid):
    if bid == "pass":
        return (0, 0, 0)
    if bid in ("X", "XX"):
        return (0, 0, 1)
    m = re.match(r"^([1-7])(C|D|H|S|NT)$", bid)
    return (1, int(m.group(1)), ORDER[m.group(2)]) if m else (2, 0, 0)


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


def fmt_nodes(nodes):
    """渲染为带缩进的树格式文本。"""
    lines = []

    def rec(ns, depth):
        prefix = "│-----" * depth
        for n in ns:
            if not n["bids"]:
                continue
            bid_str = "/".join(n["bids"])
            meta = []
            if n["points"]:
                meta.append(n["points"] + "点")
            if n["desc"]:
                meta.append(n["desc"])
            text = bid_str + "：" + ("，".join(meta) if meta else "")
            lines.append(f"{prefix}├{text}")
            rec(n["children"], depth + 1)

    rec(nodes, 0)
    return lines


SEQ_INDEX = None
FIRST = None


def child_table(cur_seq, bid):
    """seq == cur_seq+'-'+bid 的首选（同 seq 多表时确定性取表 id 最小者）。"""
    want = (cur_seq + "-" + bid) if cur_seq else bid
    return FIRST.get(want)


def build(tid, cur_seq, visited):
    nodes = []
    for e in ENTRIES.get(tid, []):
        if not e["bids"]:
            continue
        node = {"bids": e["bids"], "points": e["points"], "desc": e["desc"],
                "fixed_bid": False, "children": []}
        if tid not in visited:
            for b in sorted(set(e["bids"]), key=bid_sort_key):
                if not re.match(r"^[1-7](C|D|H|S|NT)$", b):
                    continue
                ct = child_table(cur_seq, b)
                if ct and ct not in visited:
                    sub = build(ct, (cur_seq + "-" + b) if cur_seq else b,
                                visited | {tid, ct})
                    node["children"].extend(sub)
        nodes.append(node)
    return nodes


def tally(nodes, stats):
    for n in nodes:
        stats["n"] += 1
        if n["desc"]:
            stats["desc"] += 1
        if n["children"]:
            stats["branch"] += 1
        tally(n["children"], stats)


def flat_segment(head, lines):
    return "\n".join([head] + lines)


def opening_suit_segment(md):
    """第1章开叫总表 → 花色开叫段（平铺行）。"""
    t = md.get("1-4")
    if not t:
        return ""
    lines = ["新睿二盖一体系：开叫条件总表（表1-4）"]
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
    return flat_segment("花色开叫", lines)


def dump_deprecated(md, title):
    """无seq/未挂树/干扰表的兜底段（原文平铺，不建树）。"""
    lines = [title]
    for tid, tb in sorted(md.items(), key=lambda kv: kv[0]):
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
    global ENTRIES, SEQ_INDEX, FIRST
    ENTRIES = {tid: tb["entries"] for tid, tb in md.items()}
    SEQ_INDEX = {}
    for tid, tb in md.items():
        if tb["seq"]:
            SEQ_INDEX.setdefault(tb["seq"], []).append(tid)
    FIRST = {s: sorted(v)[0] for s, v in SEQ_INDEX.items()}

    segs = [opening_suit_segment(md)]
    for root_tid, root_seq, kw in OPENINGS:
        nodes = build(root_tid, root_seq, set())
        stats = {"n": 0, "desc": 0, "branch": 0}
        tally(nodes, stats)
        lines = [kw, f"新睿二盖一体系：{kw}应叫及后续（根表{root_tid}）"]
        lines += fmt_nodes(nodes)
        segs.append("\n".join(lines))
        print(f"[{kw}] seq根={root_seq} 节点={stats['n']} 详述={stats['desc']} "
              f"续树={stats['branch']}")

    # 各章兜底段：无seq表 + 干扰表（未挂树条目），首行即章节兜底关键词
    for ch in ["1", "2", "3", "4", "5", "6", "7", "8", "9", "10", "11", "12", "13"]:
        segs.append(dump_deprecated({t: tb for t, tb in md.items()
                                     if t.startswith(ch + "-")},
                                    f"第{ch}章 未结构化表（SEQ缺失/干扰/参考，兜底）"))

    # 去空段（第6章暂缺失，兜底段不生成）
    segs = [s for s in segs if s.strip()]
    OUT_MD.write_text("\n\n\n".join(segs) + "\n", encoding="utf-8")
    print(f"saved -> {OUT_MD}")

    report(md)


def report(md):
    """残留问题筛查：歧义seq、孤立表、无叫品条目。"""
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
    lines.append("## B. 无 seq 表（未排序/信息表/干扰表/参考表，整体不入树，兜底保留）")
    nseq = [tid for tid, t in md.items() if not t["seq"]]
    lines.append(f"共 {len(nseq)} 张：`{', '.join(nseq)}`")
    lines.append("")
    lines.append("## C. 含无叫品条目的表（条目缺叫品列，仅描述/说明，需人工核对是否漏列叫品）")
    nobid_tables = sorted({tid for tid, t in md.items() for e in t["entries"] if not e["bids"]},
                          key=lambda x: (int(x.split('-')[0]), int(x.split('-')[1])))
    lines.append(f"共 {len(nobid_tables)} 张：`{', '.join(nobid_tables)}`")
    lines.append("")
    text = "\n".join(lines) + "\n"
    OUT_CK = DATA / "新睿全量人工核对清单.md"
    OUT_CK.write_text(text, encoding="utf-8")
    print("\n===== 残留问题报告 =====")
    print("A. 同seq多表（歧义，仅挂表id最小者，其余待人工判定）:")
    for s, v in sorted(SEQ_INDEX.items(), key=lambda kv: kv[0]):
        if len(v) > 1:
            print(f"   {s} -> 挂{sorted(v)[0]} 其余待定 {v}")
    print("B. 无seq表（未排序/信息表/干扰表，不入树）:")
    print(f"   共{len(nseq)}张: {nseq}")
    print("C. 含无叫品条目的表:")
    print(f"   共{len(nobid_tables)}张: {nobid_tables}")
    print(f"saved checklist -> {OUT_CK}")


if __name__ == "__main__":
    main()