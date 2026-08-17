import re
import collections
from pathlib import Path

t = Path("scripts/xr_data/validate_report.txt").read_text(encoding="utf-8")
lines = [l for l in t.splitlines() if l.startswith("  段")]
mods = collections.Counter()
for l in lines:
    if "关键字" in l:
        typ = "关键字"
    elif "缺少说明" in l:
        typ = "缺少说明"
    elif "缩进跳级" in l:
        typ = "缩进跳级"
    elif "非法叫品" in l:
        typ = "非法叫品"
    elif "不高于父" in l:
        typ = "不高于父"
    else:
        typ = "未识别行"
    mods[typ] += 1
print("分类统计:", dict(mods))
print("total:", len(lines))

pref = collections.Counter()
for l in lines:
    if "未识别行" in l:
        m = re.search(r"'(.*?)'", l)
        if m:
            pref[m.group(1)[:10]] += 1
print("未识别行前缀Top30:")
for k, v in pref.most_common(30):
    print(v, repr(k))