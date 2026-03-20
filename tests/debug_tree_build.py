from knowledge.loader import JFLoader, parse_content_to_tree, parse_indent_level, extract_bid_from_line

loader = JFLoader('JF实战_标准自然 - Rev 3.2.docx')
segments = loader.load()
content = segments[17]['content']

lines = [l.rstrip() for l in content.splitlines() if l.strip()]

keyword_bids = []
keyword_line_idx = -1
for i, line in enumerate(lines[:3]):
    m = __import__('re').search(r'[1-7](?:[CDHS]|NT)-[1-7](?:[CDHS]|NT)', line)
    if m:
        keyword_bids = m.group(0).split('-')
        keyword_line_idx = i
        break

start_line = 0
if keyword_bids and len(keyword_bids) >= 2:
    start_line = keyword_line_idx + 1

print(f'关键词叫品: {keyword_bids}')
print(f'关键词行号: {keyword_line_idx}')
print(f'开始解析行号: {start_line}')
print('\n解析过程:')
print('=' * 80)

root = {}
stack = [(-1, root)]

for line_idx, line in enumerate(lines[start_line:], start=start_line):
    depth = parse_indent_level(line)
    m = __import__('re').search(r'[├└]([A-Z0-9NT]+)', line)
    if not m:
        continue

    bid = m.group(1)
    bid = bid.upper().replace('10', 'T')
    if bid.endswith('NT'):
        pass
    elif bid.endswith('N') and len(bid) >= 2 and bid[0].isdigit():
        bid = bid[:-1] + 'NT'

    print(f'行{line_idx}: depth={depth}, bid={bid}')
    print(f'  内容: {line[:70]}')

    node = {}

    while stack and stack[-1][0] >= depth:
        popped = stack.pop()
        print(f'  弹出栈: depth={popped[0]}')

    parent = stack[-1][1]
    parent[bid] = node
    print(f'  添加节点: {bid} -> parent depth={stack[-1][0]}')
    print(f'  当前栈: {[(d, list(n.keys())[:3]) for d, n in stack]}')

    stack.append((depth, node))
    print(f'  压入栈: depth={depth}')
    print()
