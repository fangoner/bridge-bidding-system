from knowledge.loader import JFLoader, parse_content_to_tree, parse_indent_level
import re

loader = JFLoader('JF实战_标准自然 - Rev 3.2.docx')
segments = loader.load()

content = segments[17]['content']

lines = [l.rstrip() for l in content.splitlines() if l.strip()]

print("=" * 80)
print("树结构构建过程")
print("=" * 80)

keyword_bids = []
keyword_line_idx = -1
for i, line in enumerate(lines[:5]):
    m = re.search(r'^[1-7](?:[CDHS]|NT)-[1-7](?:[CDHS]|NT)$', line)
    if m:
        keyword_bids = m.group(0).split('-')
        keyword_line_idx = i
        break

print(f"关键词叫品: {keyword_bids}")
print(f"关键词行索引: {keyword_line_idx}")

start_line = keyword_line_idx + 1
print(f"起始行: {start_line}")

root = {}
stack = [(-1, root)]

first_keyword = keyword_bids[0]
second_keyword = keyword_bids[1]

root[first_keyword] = {"description": "", "children": {}}
root[first_keyword]["children"][second_keyword] = {"description": "", "children": {}}

stack = [(-1, root), (-1, root[first_keyword]["children"][second_keyword])]

print(f"\n初始栈:")
for i, (depth, node) in enumerate(stack):
    print(f"  栈[{i}]: 深度={depth}, 节点keys={list(node.keys())}")

print(f"\n开始解析树结构:")
for i, line in enumerate(lines[start_line:10]):
    depth = parse_indent_level(line)
    
    m = re.search(r'[├└]([A-Z0-9NT/]+)', line)
    if not m:
        print(f"  行{i+start_line:3d}: 深度={depth}, 无叫品")
        continue
    
    bids_str = m.group(1)
    
    if '/' in bids_str:
        bids_list = bids_str.split('/')
    else:
        bids_list = [bids_str]
    
    m_desc = re.search(r'：(.+)', line)
    description = m_desc.group(1).strip() if m_desc else ""
    
    print(f"  行{i+start_line:3d}: 深度={depth}, 叫品={bids_str}, 描述={description[:30]}")
    
    for bid in bids_list:
        if re.match(r'^[CDHS]$', bid):
            bid = '3' + bid
        
        print(f"    处理叫品: {bid}")
        
        node = {"description": description, "children": {}}
        
        print(f"    当前栈: {[(d, list(n.keys())) for d, n in stack]}")
        
        while stack and stack[-1][0] >= depth:
            popped = stack.pop()
            print(f"    弹出栈: 深度={popped[0]}, 节点keys={list(popped[1].keys())}")
        
        parent = stack[-1][1]
        print(f"    父节点keys: {list(parent.keys())}")
        parent[bid] = node
        stack.append((depth, node["children"]))
        print(f"    添加节点: {bid}, 新栈深度={depth}")

print(f"\n最终树结构:")
print(f"根节点keys: {list(root.keys())}")
if first_keyword in root:
    print(f"{first_keyword}节点keys: {list(root[first_keyword].keys())}")
    if "children" in root[first_keyword]:
        print(f"{first_keyword}.children节点keys: {list(root[first_keyword]['children'].keys())}")
        if second_keyword in root[first_keyword]['children']:
            print(f"{first_keyword}.children.{second_keyword}节点keys: {list(root[first_keyword]['children'][second_keyword].keys())}")
            if "children" in root[first_keyword]['children'][second_keyword]:
                print(f"{first_keyword}.children.{second_keyword}.children节点keys: {list(root[first_keyword]['children'][second_keyword]['children'].keys())}")
