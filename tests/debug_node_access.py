from knowledge.loader import JFLoader, parse_content_to_tree, normalize_bid

loader = JFLoader('JF实战_标准自然 - Rev 3.2.docx')
segments = loader.load()
content = segments[17]['content']

tree, keyword_bids = parse_content_to_tree(content)

tree_1d_1h_1s_2c_2d = tree['1D']['1H']['1S']['2C']['2D']
print(f"1D->1H->1S->2C->2D的子节点: {list(tree_1d_1h_1s_2c_2d.keys())}")

print("\n模拟navigate_tree_by_bids:")
node = tree_1d_1h_1s_2c_2d
bid = '2H'
normalized_bid = normalize_bid(bid)
print(f"  查找: {bid}")
print(f"  normalize_bid: {normalized_bid}")
print(f"  node.get('{normalized_bid}'): {node.get(normalized_bid)}")

print("\n直接访问:")
print(f"  node['2H']: {node.get('2H')}")

print("\n检查类型:")
print(f"  type(node): {type(node)}")
print(f"  node is dict: {isinstance(node, dict)}")
