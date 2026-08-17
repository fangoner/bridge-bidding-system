import io
import json
import re
from pathlib import Path

BASE = Path(__file__).resolve().parent.parent
SRC = BASE / "书籍" / "新睿桥牌二盖一体系.md"
OUT_DIR = BASE / "scripts" / "xr_data" / "source_slices"
OUT_DIR.mkdir(parents=True, exist_ok=True)

CHAPTER_RANGES = {
    "ch1_总纲": (375, 782),
    "ch2_1C": (782, 2733),
    "ch3_1D": (2733, 4434),
    "ch10_满贯": (10030, 10330),
}

SECTION_RANGES = {
    "ch2_1C": {
        "第一节_开叫条件": (782, 813),
        "第二节_叫牌要点": (813, 1038),
        "第三节_开叫后续": (1038, 2459),
        "第三节一_对1C开叫的应叫": (1043, 1111),
        "第三节二_一盖一应叫": (1111, 1485),
        "第三节三_双路斯泰曼": (1485, 1712),
        "第三节四_新低花逼局": (1712, 1761),
        "第三节五_1NT应叫": (1761, 1774),
        "第三节六_低花反加叫": (1774, 1868),
        "第三节七_应叫人跳叫": (1868, 2035),
        "第三节八_开叫人逆叫": (2035, 2212),
        "第三节九_开叫人跳叫": (2212, 2459),
        "第四节_被干扰": (2459, 2733),
    },
    "ch3_1D": {
        "第一节_开叫条件": (2733, 2760),
        "第二节_叫牌要点": (2760, 2968),
        "第三节_开叫后续": (2968, 4162),
        "第三节一_对1D开叫的应叫": (2968, 3013),
        "第三节二_一盖一应叫": (3013, 3282),
        "第三节三_双路斯泰曼": (3282, 3397),
        "第三节四_新低花逼局": (3397, 3456),
        "第三节五_1NT应叫": (3456, 3482),
        "第三节六_二盖一应叫": (3482, 3628),
        "第三节七_低花反加叫": (3628, 3721),
        "第三节八_应叫人跳叫": (3721, 3871),
        "第三节九_开叫人逆叫": (3871, 3927),
        "第三节十_开叫人跳叫": (3927, 4162),
        "第四节_被干扰": (4162, 4434),
    },
}


def main():
    lines = io.open(SRC, encoding="utf-8").readlines()
    manifest = []

    for name, (start, end) in CHAPTER_RANGES.items():
        text = "".join(lines[start:end])
        tables = []
        for i in range(start, end):
            m = re.match(r"^\s*表\s*(\d+)[-—－](\d+)\s*(.*)", lines[i])
            if m:
                tables.append({"line": i, "table_id": f"{m.group(1)}-{m.group(2)}", "title": m.group(3).strip()})
        path = OUT_DIR / f"{name}.md"
        path.write_text(text, encoding="utf-8")
        manifest.append({"file": path.name, "range": [start, end], "tables": tables})

    for chapter, sections in SECTION_RANGES.items():
        for name, (start, end) in sections.items():
            text = "".join(lines[start:end])
            path = OUT_DIR / f"{chapter}__{name}.md"
            path.write_text(text, encoding="utf-8")
            manifest.append({"file": path.name, "range": [start, end]})

    (OUT_DIR / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=1), encoding="utf-8")
    total_tables = sum(len(m.get("tables", [])) for m in manifest)
    print(f"slices written: {len(manifest)}, table titles found: {total_tables}")


if __name__ == "__main__":
    main()
