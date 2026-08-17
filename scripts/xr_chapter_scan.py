import re
lines = open(r"d:\Bridge Card\Bidding System\书籍\新睿桥牌二盖一体系.md", encoding="utf-8").read().split("\n")
chapters = []
cur = None
for i, l in enumerate(lines):
    m = re.match(r"^# (第[一二三四五六七八九十]+章 [^\n]*)", l)
    if m:
        if cur:
            chapters.append(cur)
        cur = {"title": m.group(1), "start": i, "tables": set()}
    elif cur:
        for tm in re.finditer(r"表(\d+)-(\d+)", l):
            cur["tables"].add(tm.group(0))
if cur:
    chapters.append(cur)
allt = set()
for c in chapters:
    n = sorted(c["tables"], key=lambda x: int(x.split("-")[1]))
    allt.update(n)
    first = ",".join(n[:3])
    last = ",".join(n[-2:]) if len(n) > 3 else ""
    print(f"{c['title']}: 表数={len(n)}  range={n[0] if n else ''}~{n[-1] if n else ''}  {first}...{last}")
print("全书总表数(按章节内引用去重):", len(allt))