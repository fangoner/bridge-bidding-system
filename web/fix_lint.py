"""
lint 自动修复脚本
用法: python fix_lint.py
功能: 自动修复 ESLint 报告中可安全修复的 no-unused-vars / no-empty / no-useless-escape 问题。
     不可自动修复的（exhaustive-deps / rules-of-hooks / set-state-in-effect 等）跳过并打印提示。
"""
import json
import re
import subprocess
import sys
from collections import defaultdict
from pathlib import Path

WEB_ROOT = Path(__file__).resolve().parent
ESLINT_REPORT = WEB_ROOT / 'eslint-report.json'

# ── 1. 生成 ESLint JSON 报告 ──────────────────────────────────────────────────
def gen_report():
    print('[1/4] 生成 ESLint JSON 报告...')
    subprocess.run(
        ['npx', 'eslint', 'src/', '-f', 'json', '-o', str(ESLINT_REPORT)],
        cwd=str(WEB_ROOT), shell=True, capture_output=True,
    )
    with open(ESLINT_REPORT, 'r', encoding='utf-8') as f:
        return json.load(f)

# ── 2. 提取变量名 ─────────────────────────────────────────────────────────────
def extract_var_name(message):
    m = re.match(r"'([^']+)'", message)
    return m.group(1) if m else None

# ── 3. 删除行内解构/import 中的未使用变量 ─────────────────────────────────────
def remove_var_from_line(line, var_name, col):
    """从解构或 import 行中安全删除指定变量名，返回新行或 None（无法处理）。"""
    # 跳过以 _ 开头的变量（按惯例允许未使用）
    if var_name.startswith('_'):
        return None

    # 模式 A: 行首缩进 + varName, otherStuff  →  缩进 + otherStuff
    #   如: "    showPartnerHand, setShowPartnerHand,"
    m = re.match(r'^(\s*)' + re.escape(var_name) + r',\s*', line)
    if m:
        return m.group(1) + line[m.end():]

    # 模式 B: , varName,  →  ,
    #   如: "    a, b, varName, c,"  →  "    a, b, c,"
    new = re.sub(r',\s*' + re.escape(var_name) + r',', ',', line, count=1)
    if new != line:
        return new

    # 模式 C: , varName } 或 , varName )  →  } 或 )
    #   如: "    a, b, varName }"  →  "    a, b }"
    new = re.sub(r',\s*' + re.escape(var_name) + r'(\s*[}\)])', r'\1', line, count=1)
    if new != line:
        return new

    # 模式 D: { varName }  →  {} (仅一个变量)——不处理，可能误删整行
    # 模式 E: ( varName )  →  ()  (仅一个参数)
    new = re.sub(r'[(\{]\s*' + re.escape(var_name) + r'\s*[)\}]', lambda m: m.group(0)[0] + m.group(0)[-1], line, count=1)
    if new != line:
        return new

    return None

# ── 4. 修复 catch 参数 ─────────────────────────────────────────────────────────
def fix_catch_param(line, var_name):
    """catch (e) { → catch {"""
    new = re.sub(r'\bcatch\s*\(\s*' + re.escape(var_name) + r'\s*\)', 'catch', line)
    return new if new != line else None

# ── 5. 修复函数参数（末尾位置） ─────────────────────────────────────────────────
def fix_trailing_param(line, var_name):
    """(a, b, e) → (a, b)  或  (a, e) → (a)"""
    new = re.sub(r',\s*' + re.escape(var_name) + r'(\s*[)\)])', r'\1', line, count=1)
    if new != line:
        return new
    # 单参数 (e) → ()
    new = re.sub(r'[(\[]\s*' + re.escape(var_name) + r'\s*[)\]]', lambda m: m.group(0)[0] + m.group(0)[-1], line, count=1)
    return new if new != line else None

# ── 6. 修复局部变量声明（整行删除） ──────────────────────────────────────────────
def fix_local_var_decl(line, var_name, lines, line_idx):
    """const varName = ... → 删除整行（仅当行内只有这一个声明）"""
    stripped = line.strip()
    # 仅处理 "const varName = ..." 或 "let varName = ..."
    if re.match(r'^(const|let)\s+' + re.escape(var_name) + r'\s*=', stripped):
        # 检查是否是解构（同一行有其他变量）——不处理解构
        if '{' in stripped[:stripped.index('=')] or '[' in stripped[:stripped.index('=')]:
            return None
        # 安全删除整行
        return '__DELETE_LINE__'
    return None

# ── 主修复逻辑 ─────────────────────────────────────────────────────────────────
SKIP_RULES = {
    'react-hooks/exhaustive-deps': '需人工判断依赖（自动添加可能引入无限循环）',
    'react-hooks/rules-of-hooks': '需重构 hooks 调用顺序',
    'react-hooks/set-state-in-effect': '需重构 effect 逻辑',
    'react-hooks/preserve-manual-memoization': '编译器优化问题，需手动调整 useMemo/useCallback',
    'react-refresh/only-export-components': '需拆分文件',
}

def main():
    report = gen_report()

    # 按 file 分组
    by_file = defaultdict(list)
    skip_stats = defaultdict(int)
    for entry in report:
        for msg in entry['messages']:
            rule = msg.get('ruleId')
            if rule in SKIP_RULES:
                skip_stats[rule] += 1
                continue
            if rule in ('no-unused-vars', 'no-empty', 'no-useless-escape'):
                by_file[entry['filePath']].append(msg)
            else:
                skip_stats[rule] += 1

    print(f'[2/4] 待修复文件数: {len(by_file)}')
    print(f'      跳过（不可自动修复）: {sum(skip_stats.values())} 个')
    for rule, cnt in skip_stats.items():
        print(f'        - {rule}: {cnt}（{SKIP_RULES.get(rule, "")}）')

    total_fixed = 0
    total_skipped = 0
    fix_log = []

    print('[3/4] 修复中...')
    for filepath, msgs in by_file.items():
        rel = Path(filepath).relative_to(WEB_ROOT)
        with open(filepath, 'r', encoding='utf-8') as f:
            lines = f.readlines()

        # 从后往前处理，避免行号偏移
        msgs_sorted = sorted(msgs, key=lambda m: m['line'], reverse=True)
        file_fixed = 0

        for msg in msgs_sorted:
            line_idx = msg['line'] - 1
            if line_idx >= len(lines):
                continue
            line = lines[line_idx]
            rule = msg['ruleId']
            result = None

            if rule == 'no-useless-escape':
                new = line.replace('\\-', '-', 1)
                if new != line:
                    result = new
                    fix_log.append(f'  ✓ {rel}:{msg["line"]} no-useless-escape')

            elif rule == 'no-empty':
                # 空块 {} → {/* empty */}
                if '{}' in line:
                    result = line.replace('{}', '{/* empty */}', 1)
                    fix_log.append(f'  ✓ {rel}:{msg["line"]} no-empty')
                elif re.search(r'\{\s*\}', line):
                    result = re.sub(r'\{\s*\}', '{/* empty */}', line, count=1)
                    fix_log.append(f'  ✓ {rel}:{msg["line"]} no-empty')

            elif rule == 'no-unused-vars':
                var_name = extract_var_name(msg['message'])
                if not var_name:
                    total_skipped += 1
                    continue

                # 尝试 catch 参数修复
                if re.search(r'\bcatch\s*\(', line):
                    result = fix_catch_param(line, var_name)
                    if result:
                        fix_log.append(f'  ✓ {rel}:{msg["line"]} unused catch param "{var_name}"')

                # 尝试解构/import 变量删除
                if result is None:
                    result = remove_var_from_line(line, var_name, msg.get('column', 1) - 1)
                    if result:
                        fix_log.append(f'  ✓ {rel}:{msg["line"]} unused var "{var_name}" (解构/import)')

                # 尝试末尾函数参数删除
                if result is None:
                    result = fix_trailing_param(line, var_name)
                    if result:
                        fix_log.append(f'  ✓ {rel}:{msg["line"]} unused trailing param "{var_name}"')

                # 尝试局部变量声明删除
                if result is None:
                    result = fix_local_var_decl(line, var_name, lines, line_idx)
                    if result == '__DELETE_LINE__':
                        fix_log.append(f'  ✓ {rel}:{msg["line"]} unused local var "{var_name}" (删除整行)')

            if result is not None:
                if result == '__DELETE_LINE__':
                    del lines[line_idx]
                else:
                    lines[line_idx] = result
                file_fixed += 1
            else:
                total_skipped += 1

        if file_fixed > 0:
            with open(filepath, 'w', encoding='utf-8') as f:
                f.writelines(lines)
            total_fixed += file_fixed

    # 打印日志
    for log in fix_log:
        print(log)
    print(f'\n  已修复: {total_fixed}')
    print(f'  跳过（无法自动处理）: {total_skipped}')

    # ── 验证 ──────────────────────────────────────────────────────────────────
    print('[4/4] 重新运行 ESLint 验证...')
    r = subprocess.run(
        ['npx', 'eslint', 'src/', '-f', 'compact'],
        cwd=str(WEB_ROOT), shell=True, capture_output=True, text=True,
    )
    # 统计剩余问题
    remaining = len([l for l in r.stdout.splitlines() if 'error' in l or 'warning' in l])
    # 用 problems 行
    for line in r.stdout.splitlines():
        if 'problems' in line:
            print(f'  {line.strip()}')
            break
    else:
        print(f'  剩余问题行数: {remaining}')

    # 清理报告文件
    ESLINT_REPORT.unlink(missing_ok=True)
    print('\n完成。建议运行 npm run build 验证无破坏性更改。')

if __name__ == '__main__':
    main()
