from knowledge.loader import JFLoader, parse_indent_level
import re

loader = JFLoader('JF实战_标准自然 - Rev 3.2.docx')
segments = loader.load()

content = segments[17]['content']

lines = [l.rstrip() for l in content.splitlines() if l.strip()]

keyword_bids = []
keyword_line_idx = -1
for i, line in enumerate(lines[:5]):
    m = re.search(r'[1-7](?:[CDHS]|NT)-[1-7](?:[CDHS]|NT)', line)
    if m:
        keyword_bids = m.group(0).split('-')
        keyword_line_idx = i
        break

print(f"关键词叫品: {keyword_bids}")
print(f"关键词行索引: {keyword_line_idx}")
print(f"关键词行内容: {lines[keyword_line_idx]}")

start_line = keyword_line_idx + 1

print(f"\n从第{start_line}行开始解析树结构:")
for i, line in enumerate(lines[start_line:20]):
    depth = parse_indent_level(line)
    m = re.search(r'[├└]([A-Z0-9NT/]+)', line)
    if m:
        bids_str = m.group(1)
        m_desc = re.search(r'：(.+)', line)
        description = m_desc.group(1).strip() if m_desc else ""
        print(f"行{i+start_line:3d}: 深度={depth}, 叫品={bids_str}, 描述={description[:40]}")
