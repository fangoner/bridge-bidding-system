from knowledge.loader import JFLoader, parse_content_to_tree
import json

loader = JFLoader('JF实战_标准自然 - Rev 3.2.docx')
segments = loader.load()

content = segments[17]['content']

print("=" * 80)
print("测试：1D-1H树结构")
print("=" * 80)

tree, keyword_bids = parse_content_to_tree(content)
print(f"关键词叫品: {keyword_bids}")

def print_tree(node, indent=0):
    for bid, child in node.items():
        if isinstance(child, dict):
            description = child.get("description", "")
            children = child.get("children", {})
            print("  " * indent + f"{bid}: {description[:50] if description else ''}")
            if children:
                print_tree(children, indent + 1)
        else:
            print("  " * indent + f"{bid}: {child}")

print_tree(tree)
