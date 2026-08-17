"""修正 pdf_tables 中各章节 JSON 内重复 table_id 的误标项。

同一物理表格在不同提取批次被分配了不同 table_id，导致 load_tables 按 id 合并词集，
污染真表数据（如 ch4 表4-3 的 1♥-1♠ 树段被清空）。本脚本将重复对中的"续写/散文/重复提取"
项重命名为唯一编号，保留全部内容；真表保留原 id。重命名项无 seq 映射，自动落入兜底段。
"""
import json
from pathlib import Path

BASE = Path(__file__).resolve().parent
PDF = BASE / "xr_data" / "pdf_tables"

# (文件名, 旧id, 页码) -> 新id
RENAME = {
    "tables_ch4.json": {
        ("4-3", 135): "4-35",    # 表4-3误标了表4-35(1♥-2NT雅各比后续)内容
        ("4-9", 116): "4-116",   # 第四花色逼局散文段
        ("4-11", 120): "4-120",  # 1♥应叫总表重复提取
        ("4-12", 118): "4-118",  # 二盖一应叫散文段
    },
    "tables_ch6.json": {
        ("6-1", 191): "6-4",     # 1NT开叫后续续写表
        ("6-2", 184): "6-16",    # 应叫总表跨页溢出
    },
    "tables_ch7_8.json": {
        ("7-12", 202): "7-202",  # 2♣应叫总表重复提取
    },
}


def main():
    for fname, renames in RENAME.items():
        path = PDF / fname
        data = json.loads(path.read_text(encoding="utf-8"))
        for t in data:
            key = (t["table_id"], t.get("page"))
            if key in renames:
                new = renames[key]
                print(f"  {fname}: 表{t['table_id']} page{t.get('page')} -> 表{new} (title={t.get('title')})")
                t["table_id"] = new
                t["secondary"] = True
        path.write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")


if __name__ == "__main__":
    main()