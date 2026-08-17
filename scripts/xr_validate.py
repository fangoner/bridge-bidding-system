import json
import re
import sys
import collections
from pathlib import Path

BASE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE / "knowledge"))
DATA = BASE / "scripts" / "xr_data"
MD = DATA / (sys.argv[1] if len(sys.argv) > 1 else "新睿实战_二盖一体系_试点.md")
BUILT = DATA / "tables_built.json"

TREE_LINE = re.compile(r"^(│-----)*(├|└)([1-7](?:C|D|H|S|NT)(?:/[1-7](?:C|D|H|S|NT))*|pass|X|XX)(：(.*))?$")
KEYWORD_LINE = re.compile(r"^[1-7](?:C|D|H|S|NT)(?:-[1-7](?:C|D|H|S|NT))*$")
RESP_LINE = re.compile(r"^[1-7](?:C|D|H|S|NT)-(pass|[1-7](?:C|D|H|S|NT)|X|XX)：")

BID_ORDER = {"C": 0, "D": 1, "H": 2, "S": 3, "NT": 4}


def bid_rank(bid):
    m = re.match(r"^([1-7])(C|D|H|S|NT)$", bid)
    if not m:
        return None
    return (int(m.group(1)) - 1) * 5 + BID_ORDER[m.group(2)]


def parse_indent(line):
    n = 0
    i = 0
    while line[i:i + 6] in ("│-----", "├-----"):
        n += 1
        i += 6
    return n


def main():
    text = MD.read_text(encoding="utf-8")
    segments = [s for s in re.split(r"\n\s*\n\s*\n", text) if s.strip()]
    errors = []
    warnings = []
    stats = {"segments": 0, "tree_lines": 0, "resp_lines": 0, "tree_nodes": 0, "pass_lines": 0}

    for si, seg in enumerate(segments):
        lines = [l.rstrip() for l in seg.splitlines() if l.strip()]
        stats["segments"] += 1
        if not lines:
            continue
        kw = lines[0].strip()
        # 兜底段（非结构化原文平铺）整体豁免逐行检查
        if "未结构化" in kw or "兜底" in kw:
            continue
        has_tree = any(TREE_LINE.match(l) for l in lines[1:])
        if has_tree and not KEYWORD_LINE.match(kw) and not kw.endswith("开叫"):
            errors.append(f"段{si + 1}: 关键词行格式异常 {kw!r}")
        is_opening_flat = kw == "花色开叫" or (kw.endswith("开叫") and not has_tree)

        stack = []
        for li, line in enumerate(lines[1:], 2):
            if TREE_LINE.match(line):
                stats["tree_lines"] += 1
                depth = parse_indent(line)
                m = TREE_LINE.match(line)
                bids = m.group(3).split("/")
                if m.group(5) is None:
                    warnings.append(f"段{si + 1}行{li}: 缺少说明 {line[:50]!r}")
                if len(stack) < depth:
                    errors.append(f"段{si + 1}行{li}: 缩进跳级 depth={depth} prev={len(stack)} {line[:40]!r}")
                while len(stack) > depth:
                    stack.pop()
                parent_bid = stack[-1] if stack else None
                for b in bids:
                    if b in ("pass", "X", "XX"):
                        stats["pass_lines"] += 1
                        continue
                    r = bid_rank(b)
                    if r is None:
                        errors.append(f"段{si + 1}行{li}: 非法叫品 {b!r}")
                        continue
                    stack.append(bids[-1])
            elif RESP_LINE.match(line):
                stats["resp_lines"] += 1
            elif is_opening_flat and "：" in line:
                stats["resp_lines"] += 1
            elif li == 2 and ("新睿" in line or "体系" in line):
                continue
            else:
                if line.startswith("第三四家"):
                    continue
                warnings.append(f"段{si + 1}行{li}: 未识别行 {line[:50]!r}")

    from loader import parse_content_to_tree
    loader_stats = []
    for si, seg in enumerate(segments):
        lines = [l.rstrip() for l in seg.splitlines() if l.strip()]
        kw = lines[0].strip()
        if not KEYWORD_LINE.match(kw):
            continue
        result = parse_content_to_tree(seg)
        if isinstance(result, tuple):
            tree, kwbids = result
        else:
            tree, kwbids = result, []
        count = [0]

        def walk(node):
            count[0] += 1
            for c in node.values():
                walk(c.get("children", {}))

        walk(tree)
        loader_stats.append((kw, kwbids, count[0]))
        if kwbids and "-".join(kwbids) != kw:
            errors.append(f"段{si + 1}: loader关键词 {kwbids} != 文档关键词 {kw}")

    built = json.loads(BUILT.read_text(encoding="utf-8"))
    rendered_bids = set()
    for seg in segments:
        for line in seg.splitlines():
            m = TREE_LINE.match(line.rstrip())
            if m:
                rendered_bids.update(m.group(3).split("/"))
    total_entries = sum(len(v) for v in built["tables"].values())
    no_bid = sum(1 for v in built["tables"].values() for e in v if not e["bids"])

    print("=" * 60)
    print("结构统计:", stats)
    print(f"built条目: {total_entries}, 无叫品: {no_bid}")
    print("-" * 60)
    print("loader解析结果:")
    for kw, kwbids, n in loader_stats:
        print(f"  {kw}: loader_kw={'-'.join(kwbids) or '(无)'} nodes={n}")
    print("-" * 60)
    if errors:
        print(f"ERRORS ({len(errors)}):")
        for e in errors:
            print(" ", e)
    else:
        print("ERRORS: 0")
    if warnings:
        print(f"WARNINGS ({len(warnings)}):")
        for w in warnings[:20]:
            print(" ", w)
        if len(warnings) > 20:
            print(f"  ... 共{len(warnings)}条")
        cat = collections.Counter()
        for w in warnings:
            if "关键字" in w:
                cat["关键字"] += 1
            elif "缺少说明" in w:
                cat["缺少说明"] += 1
            elif "缩进跳级" in w:
                cat["缩进跳级"] += 1
            elif "非法叫品" in w:
                cat["非法叫品"] += 1
            elif "不高于父" in w:
                cat["不高于父"] += 1
            else:
                cat["未识别行"] += 1
        print("WARN分类:", dict(cat))
        (DATA / "validate_warnings.txt").write_text(
            "\n".join(warnings), encoding="utf-8")
    else:
        print("WARNINGS: 0")
    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main())
