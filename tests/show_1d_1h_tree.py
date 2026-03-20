from knowledge.loader import JFLoader, parse_content_to_tree
import json

loader = JFLoader('JF实战_标准自然 - Rev 3.2.docx')
segments = loader.load()

content = segments[2]['content']

print("=" * 80)
print("测试片段2：1D-1H")
print("=" * 80)

print("完整原始内容:")
print(content)

print("\n" + "=" * 80)
print("树结构转换:")
print("=" * 80)
tree, keyword_bids = parse_content_to_tree(content)
print(f"关键词叫品: {keyword_bids}")
print(f"\n树结构:")
print(json.dumps(tree, indent=2, ensure_ascii=False))
