"""飞牌文档与代码同步校验（直接运行，非 pytest）。

目的：`docs/飞牌介入管线图解.md` 第一版曾按 v1.71 写就，在代码重写 20 多个版本后
仍被当作现行文档（引用的 9 个函数全部不存在、阈值 Δ=0.4/RATIO=0.95 也已作废）。
本脚本把该文档的事实依赖固化成可执行校验，避免同类漂移再次发生。

校验三项：
  ① 文档声明的函数符号在源码中确实存在（挡住"改名/删除"型漂移）
  ② 文档声明的配置阈值与 config.py 实测值一致（挡住"阈值改了文档没改"型漂移）
  ③ 文档声明的开关常量在 config.py 中存在

**能力边界（诚实声明）**：本脚本**不能**发现分支顺序调换、新增分支、判据内部逻辑
改动。它只能挡住最粗的一类漂移。文档与代码冲突时，**以代码为准**。

运行: python tests/test_finesse_doc_sync.py
"""

import io
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DOC = os.path.join(ROOT, "docs", "飞牌介入管线图解.md")
PLAY_SERVICE = os.path.join(ROOT, "bridge", "play_service.py")
DD_SEARCH = os.path.join(ROOT, "bridge", "mcts", "dd_search.py")

# 文档中「八、判据/符号速查」声称存在的函数 → 期望所在文件
EXPECTED_SYMBOLS = {
    "_intervene": PLAY_SERVICE,
    "_is_leading": PLAY_SERVICE,
    "_is_discarding": PLAY_SERVICE,
    "_garrison_lead": PLAY_SERVICE,
    "_garrison_follow": PLAY_SERVICE,
    "_garrison_target": PLAY_SERVICE,
    "_finesse_lead": PLAY_SERVICE,
    "_probe_lead_finesse_prefer": PLAY_SERVICE,
    "_probe_partner_finesse_struct": PLAY_SERVICE,
    "_partner_overhand_action": PLAY_SERVICE,
    "_cash_reentry": PLAY_SERVICE,
    "_finesse_launch_worthwhile": PLAY_SERVICE,
    "_subset_select": PLAY_SERVICE,
    "_finesse_commit_check": PLAY_SERVICE,
    "_apply_finesse_commit": PLAY_SERVICE,
    "_finesse_commit_ratio_ok": PLAY_SERVICE,
    "_finesse_ratio_ok": PLAY_SERVICE,
    "_detect_finesse_struct": PLAY_SERVICE,
    "_registry_finesse_struct": PLAY_SERVICE,
    "_register_finesse_flow": PLAY_SERVICE,
    "_probe_finesse_ok": PLAY_SERVICE,
    "_top1_make": PLAY_SERVICE,
    "_finalize_finesse_probe": DD_SEARCH,
    "_probe_ok": DD_SEARCH,
    "_honor_missing_of_state": DD_SEARCH,
    "_FINESSE_WINDOW_BASE": DD_SEARCH,
    "_accumulate_finesse_probe": DD_SEARCH,
    "_accumulate_finesse_probe_follow": DD_SEARCH,
    "_finalize_finesse_probe_follow": DD_SEARCH,
}

# 文档中给出的配置阈值 → 从 config 读取的实测值（容忍 1e-9 浮点误差）
EXPECTED_VALUES = [
    "FINESSE_RATIO",
    "FINESSE_PROBE_DELTA",
    "FINESSE_COMMIT_DIE_PCT",
    "FINESSE_COMMIT_ALIVE_PCT",
    "FINESSE_NEC_MAKE",
    "FINESSE_NEC_MIN_RATIO",
    "FINESSE_NEC_MAKE_HIGH",
    "FINESSE_NEC_RATIO",
]

# 文档中给出的开关常量（只校验存在性，不比对布尔值）
EXPECTED_SWITCHES = [
    "FINESSE_DEFER_ENABLE",
    "DD_FINESSE_ENABLE",
    "FINESSE_EIGHT_NINE_ENABLE",
]


def _read(path):
    return io.open(path, encoding="utf-8").read()


def check_symbols():
    """① 文档速查表列出的函数/常量是否都在期望文件里**定义**。

    必须匹配真实定义（`def NAME` / `NAME =`），不能用子串匹配——
    否则 `def _garrison_target` 被改名为 `def _RENAMED_garrison_target` 时，
    原名仍是子串，检查会漏报（该漏洞由负向测试发现并已修复）。
    """
    doc = _read(DOC)
    sources = {p: _read(p) for p in set(EXPECTED_SYMBOLS.values())}
    problems = []
    for sym, path in sorted(EXPECTED_SYMBOLS.items()):
        if sym not in doc:
            problems.append(f"{sym}：文档速查表未列出（图可能已删该步）")
            continue
        # 真实定义：def NAME / async def NAME / NAME = （模块级常量）
        pattern = re.compile(
            rf"(?:^\s*(?:async\s+)?def\s+{re.escape(sym)}\b)"
            rf"|(?:^\s*{re.escape(sym)}\s*=)",
            re.MULTILINE,
        )
        if not pattern.search(sources[path]):
            problems.append(
                f"{sym}：文档仍声明存在，但 {os.path.relpath(path, ROOT)} 中找不到定义"
            )
    return problems


def check_values():
    """② 文档声明的阈值数值是否与 config.py 实测一致。"""
    import config

    doc = _read(DOC)
    problems = []
    for name in EXPECTED_VALUES:
        actual = getattr(config, name, None)
        if actual is None:
            problems.append(f"{name}：config.py 中不存在（常量已删除/改名）")
            continue
        # 抓取 `NAME` 所在**同一表格行/同一行内**紧随其后的小数。
        # 为何限定在行内：早期版本用 [^`]*? 会跨越整段文字去捞数字，
        # 结果把章节交叉引用（如 "§4.1"）当成声明值——必须限定作用域。
        # 为何只认小数：飞牌阈值全为小数，避免与正文里的整数混淆。
        for line in doc.splitlines():
            if f"`{name}`" not in line:
                continue
            m = re.search(r"`" + re.escape(name) + r"`[^`]*?(\d+\.\d+)", line)
            if m:
                declared = float(m.group(1))
                break
        else:
            problems.append(f"{name}：文档中未找到声明的小数值")
            continue
        declared = float(m.group(1))
        if abs(declared - float(actual)) > 1e-9:
            problems.append(
                f"{name}：文档声明 {declared}，config.py 实测 {actual}"
            )
    return problems


def check_switches():
    """③ 文档提到的开关常量是否存在于 config.py。"""
    import config

    doc = _read(DOC)
    problems = []
    for name in EXPECTED_SWITCHES:
        if name not in doc:
            problems.append(f"{name}：文档未提及（开关表可能不全）")
        elif not hasattr(config, name):
            problems.append(f"{name}：文档仍提及，但 config.py 中不存在")
    return problems


def main():
    if not os.path.exists(DOC):
        print(f"[!!] 文档不存在：{DOC}")
        print("     若已归档，请同步更新本脚本或删除本脚本。")
        return 1

    groups = [
        ("① 符号存在性（函数改名/删除检测）", check_symbols),
        ("② 阈值一致性（config.py 实测比对）", check_values),
        ("③ 开关常量存在性", check_switches),
    ]

    total = 0
    for title, fn in groups:
        problems = fn()
        total += len(problems)
        status = "OK" if not problems else "!!"
        print(f"[{status}] {title}")
        for p in problems:
            print(f"       - {p}")

    print()
    if total:
        print(f"不一致 {total} 项 —— 请同步 docs/飞牌介入管线图解.md（以代码为准）")
        print("提示：若图已整体失效，应按 docs/README.md 的约定归档并在索引中登记。")
        return 1
    print("通过：文档声明的符号 / 阈值 / 开关均与代码一致")
    print("注意：本脚本不覆盖分支顺序、新增分支与判据内部逻辑——改飞牌代码后仍需人工核对图解。")
    return 0


if __name__ == "__main__":
    sys.exit(main())
