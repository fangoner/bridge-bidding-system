import sys, json, re, collections
from pathlib import Path
sys.path.insert(0, r"d:\Bridge Card\Bidding System\scripts")
import xr_build_all as A
import xr_build_tree as B

DATA = Path(r"d:\Bridge Card\Bidding System\scripts\xr_data")
OUT_MD = Path(r"d:\Bridge Card\Bidding System\docs\新睿全量人工核对清单.md")


def setup():
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
    parity, _ = B.dedup_ownership(parsed)
    parsed = parity
    for tid in B.MANUAL_TABLES:
        parsed[tid] = list(B.MANUAL_TABLES[tid])
    order = sorted(tables, key=lambda t: (int(t.split("-")[0]), int(t.split("-")[1])))
    for tid in order:
        for e in parsed.get(tid, []):
            B.derive_bids_from_links(e, tid)
        B.fix_entry_bids(tid, parsed.get(tid, []))
    return tables, parsed, order


def collect_rendered(tables, parsed):
    rendered, suppressed = set(), set()
    for openings, oid, o3rd, kw in A.OPENINGS:
        by_seq = {}
        for tid in tables:
            s = A._root_table_seq(tid)
            if s and s.split("-")[0] in openings:
                by_seq.setdefault(s, []).append(tid)
        for seq, grp in by_seq.items():
            canon = A._pick_canonical(grp, parsed)
            for rt in grp:
                if rt != canon:
                    suppressed.add(rt)
            rendered.add(canon)
            try:
                nodes = B.build_tree_node(canon, tables, set(), parsed)
            except Exception:
                nodes = []
            def walk(nd):
                if isinstance(nd, dict):
                    if nd.get("table"):
                        rendered.add(str(nd["table"]))
                    walk(nd.get("children", []))
                elif isinstance(nd, list):
                    for i in nd:
                        walk(i)
            walk(nodes)
    return rendered, suppressed


def chapter(tid):
    return tid.split("-")[0]


def main():
    tables, parsed, order = setup()
    rendered, suppressed = collect_rendered(tables, parsed)

    out = []
    out.append("# 新睿二盖一体系 全量人工核对清单")
    out.append("")
    out.append("> 范围：全书章程表（2-13 章，干扰/兜底/满贯等非结构表除外）。")
    out.append("> 程序自动识别出的遗留问题，需对照《新睿桥牌二盖一体系.pdf》原文人工核对确认。")
    out.append("> 图中标注〔OCR校正〕的为程序已修正；未标注的在此列清单。")
    out.append("")

    cat = collections.Counter()
    MERGE_PAT = re.compile(r"(逼局不逼叫|不逼叫逼局|逼局邀请|邀请逼局|邀请不逼叫|不逼叫邀请|逼局逼局|逼局5张|5张以上♥，邀请6|，邀请5|，逼局5张)")
    RARE = set("妒翋篝勹扱媒跃汹堪奌")

    chapters = sorted(set(chapter(t) for t in tables), key=int)
    for ch in chapters:
        ch_tables = sorted([t for t in tables if chapter(t) == ch],
                           key=lambda t: int(t.split("-")[1]))
        out.append(f"## 第{ch}章（{len(ch_tables)} 表）")
        out.append("")

        # A. 无叫品行
        a = []
        for tid in ch_tables:
            for e in parsed.get(tid, []):
                if not e["bids"] and tid in rendered:
                    a.append(f'- **{tid}** raw=`{e.get("raw")}` pts=`{e.get("points")}` desc=`{e["desc"][:50]}`')
        out.append("### A. 树内无叫品行（no-bid，需补叫品）")
        out.append("（共 %d 条）" % len(a))
        out.extend(a or ["- 无"])
        out.append("")

        # B. 疑似两行合并
        b = []
        for tid in ch_tables:
            for e in parsed.get(tid, []):
                if not e["bids"] or tid not in rendered:
                    continue
                if MERGE_PAT.search(e["desc"]):
                    b.append(f'- **{tid}** {"/".join(e["bids"])}: pts=`{e["points"]}` desc=`{e["desc"][:70]}`')
        out.append("### B. 疑似多行粘连（需拆分）")
        out.append("（共 %d 条）" % len(b))
        out.extend(b or ["- 无"])
        out.append("")

        # C. 点力缺失
        c = []
        for tid in ch_tables:
            for e in parsed.get(tid, []):
                if e["bids"] and not e["points"] and tid in rendered:
                    c.append(f'- **{tid}** {"/".join(e["bids"])}: desc=`{e["desc"][:50]}`')
        out.append("### C. 点力缺失（需补）")
        out.append("（共 %d 条）" % len(c))
        out.extend(c or ["- 无"])
        out.append("")

        # D. OCR 乱码
        d = []
        for tid in ch_tables:
            for e in parsed.get(tid, []):
                if not e["bids"]:
                    continue
                hit = [x for x in RARE if x in e["desc"]]
                if hit:
                    d.append(f'- **{tid}** {"/".join(e["bids"])}: {hit} desc=`{e["desc"][:60]}`')
        out.append("### D. 描述残留乱码字")
        out.append("（共 %d 条）" % len(d))
        out.extend(d or ["- 无"])
        out.append("")

        # E. seq 重复/疑似续写表（已兜底保留，需人工判定正确序列）
        e_dup = [t for t in ch_tables if t in suppressed]
        out.append("### E. seq 重复续写表（已兜底保留全文，需人工判定并注入 MANUAL_SEQ/合并）")
        for t in e_dup:
            s = B.TABLE_SEQ.get(t, "")
            line = f'- **{t}** seq=`{s}` title=`{tables[t].get("title", "")[:50]}`'
            out.append(line)
        out.append("（共 %d 条）" % len(e_dup))
        out.append("")

        # F. 未入树（seq 缺失/干扰，兜底保留）
        f_miss = [t for t in ch_tables if t not in B.TABLE_SEQ and t not in suppressed]
        out.append("### F. seq 缺失/未入树（兜底保留，需补 seq 或归入树）")
        for t in f_miss:
            out.append(f'- **{t}** title=`{tables[t].get("title", "")[:50]}`')
        out.append("（共 %d 条）" % len(f_miss))
        out.append("")

        cat["A"] += len(a)
        cat["B"] += len(b)
        cat["C"] += len(c)
        cat["D"] += len(d)
        cat["E"] += len(e_dup)
        cat["F"] += len(f_miss)

    out.append("## 汇总")
    out.append("")
    out.append(f"- A 无叫品：{cat['A']}")
    out.append(f"- B 粘连：{cat['B']}")
    out.append(f"- C 点力缺失：{cat['C']}")
    out.append(f"- D 乱码：{cat['D']}")
    out.append(f"- E seq重复续写：{cat['E']}")
    out.append(f"- F seq缺失/未入树：{cat['F']}")
    out.append("")

    OUT_MD.write_text("\n".join(out) + "\n", encoding="utf-8")
    print("tables=%d rendered=%d suppressed=%d" % (len(tables), len(rendered & set(tables)), len(suppressed)))
    print("分类:", dict(cat))
    print("[已写入] docs/新睿全量人工核对清单.md")


if __name__ == "__main__":
    main()