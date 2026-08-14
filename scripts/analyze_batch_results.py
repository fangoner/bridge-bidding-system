"""批量回归结果统计：汇总 cdp_batch20.py 输出的 board_*.json。

用法: python scripts/analyze_batch_results.py [结果目录]
默认目录: %TEMP%/trae/batch20_game
"""
import glob
import json
import os
import re
import sys
from collections import Counter


def parse_time(s):
    """HH:MM:SS → 秒；无效返回 None"""
    if not s:
        return None
    parts = s.split(":")
    if len(parts) != 3:
        return None
    try:
        return int(parts[0]) * 3600 + int(parts[1]) * 60 + int(parts[2])
    except ValueError:
        return None


def result_category(result):
    """result 文本 → 类别: 完成/宕N/超N/得分/失败"""
    if not result:
        return "无结果"
    r = result.strip()
    if r == "完成":
        return "正好完成"
    m = re.match(r"^超\s*(\d+)$", r)
    if m:
        return f"超{m.group(1)}"
    m = re.match(r"^宕\s*(\d+)$", r)
    if m:
        return f"宕{m.group(1)}"
    m = re.match(r"^[+-]\d{3,}$", r)  # 3 位以上是得分（如 +150），不是墩差
    if m:
        return f"得分{m.group(0)}"
    m = re.match(r"^[+-](\d+)$", r)   # 1-2 位是墩差（兼容旧格式记录）
    if m:
        return f"超{m.group(1)}" if r.startswith('+') else f"宕{m.group(1)}"
    return r


def main():
    outdir = sys.argv[1] if len(sys.argv) > 1 else os.path.join(
        os.environ.get("TEMP", "."), "trae", "batch20_game")
    files = sorted(glob.glob(os.path.join(outdir, "board_*.json")))
    # 排除 _0813 这类历史备份
    files = [f for f in files if not re.search(r"_\d{4}\.json$", f)]

    if not files:
        print(f"结果目录无 board_*.json: {outdir}")
        return

    rows = []
    for f in files:
        with open(f, encoding="utf-8") as fh:
            rec = json.load(fh)
        rows.append(rec)

    total = len(rows)
    ok = sum(1 for r in rows if r.get("ok"))
    fail = total - ok

    print(f"===== 批量回归统计（{outdir}）=====")
    print(f"总副数: {total} | 成功: {ok} | 失败: {fail} | 成功率: {ok / total * 100:.0f}%")

    if rows:
        durations = []
        for r in rows:
            s, e = parse_time(r.get("start")), parse_time(r.get("end"))
            if s is not None and e is not None and e >= s:
                durations.append(e - s)
        if durations:
            print(f"单副耗时: 最短 {min(durations)}s / 最长 {max(durations)}s / 平均 {sum(durations) // len(durations)}s")

    print("\n-- 定约分布 --")
    for contract, n in Counter(r.get("contract") for r in rows).most_common():
        print(f"  {contract}: {n} 副")

    print("\n-- 结果分布 --")
    for cat, n in Counter(result_category(r.get("result")) for r in rows).most_common():
        print(f"  {cat}: {n} 副")

    print("\n-- 明细 --")
    for r in rows:
        cat = result_category(r.get("result"))
        status = "OK " if r.get("ok") else "FAIL"
        print(f"  {status} 副{r.get('board'):>3}  定约={r.get('contract')}  结果={cat}  "
              f"{r.get('start','?')}→{r.get('end','?')}")
        if not r.get("ok"):
            txt = (r.get("bidding_text") or r.get("play_text") or "")[:200]
            print(f"        失败线索: {txt!r}")

    # 失败原因归类（board_%02d.json 里 bidding_text 含页面文本）
    if fail > 0:
        print("\n-- 失败详情 --")
        for r in rows:
            if r.get("ok"):
                continue
            t = (r.get("play_text") or "") + (r.get("bidding_text") or "")
            if "Contract:" in (r.get("bidding_text") or ""):
                hint = "叫牌完成但打牌未完成"
            elif "13/13" in t:
                hint = "打牌已完成但标记失败（提取问题？）"
            else:
                hint = "叫牌未完成（可能 UI 文案/对话框不匹配）"
            print(f"  副{r.get('board')}: {hint}")


if __name__ == "__main__":
    main()
