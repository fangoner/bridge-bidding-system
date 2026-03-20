from knowledge.loader import JFLoader, parse_content_to_tree

loader = JFLoader('JF实战_标准自然 - Rev 3.2.docx')
segments = loader.load()

# 片段17内容
content = segments[17]['content']

print("=" * 80)
print("片段17: 1D-1H后的进程")
print("=" * 80)
print()

tree, keyword_bids = parse_content_to_tree(content)

print(f"关键词叫品: {keyword_bids}")
print()

def print_tree(node, indent=0):
    prefix = "  " * indent
    for bid, child in node.items():
        print(f"{prefix}{bid}")
        if child:
            print_tree(child, indent + 1)

if tree:
    print("树结构:")
    print_tree(tree)
