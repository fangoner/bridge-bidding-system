from knowledge.loader import JFLoader
import re

loader = JFLoader('JF实战_标准自然 - Rev 3.2.docx')
segments = loader.load()

content = segments[17]['content']

lines = [l.rstrip() for l in content.splitlines() if l.strip()]

print("=" * 80)
print("检查正则表达式匹配")
print("=" * 80)

keyword_bids = []
keyword_line_idx = -1
for i, line in enumerate(lines[:5]):
    print(f"行{i}: {line}")
    m = re.search(r'^[1-7](?:[CDHS]|NT)-[1-7](?:[CDHS]|NT)$', line)
    if m:
        keyword_bids = m.group(0).split('-')
        keyword_line_idx = i
        print(f"  匹配成功！关键词: {keyword_bids}")
        break

print(f"\n关键词叫品: {keyword_bids}")
print(f"关键词行索引: {keyword_line_idx}")
print(f"关键词行内容: {lines[keyword_line_idx]}")
