from knowledge.loader import JFLoader, parse_content_to_tree, normalize_bid

loader = JFLoader('JF实战_标准自然 - Rev 3.2.docx')
segments = loader.load()
content = segments[17]['content']

tree, keyword_bids = parse_content_to_tree(content)

tree_1d_1h_1s_2c_2d = tree['1D']['1H']['1S']['2C']['2D']
print(f"1D->1H->1S->2C->2D的子节点: {list(tree_1d_1h_1s_2c_2d.keys())}")

print("\n检查每个键:")
for key in tree_1d_1h_1s_2c_2d.keys():
    print(f"  键: '{key}', normalize: '{normalize_bid(key)}'")

print("\n查找2H:")
print(f"  normalize_bid('2H'): '{normalize_bid('2H')}'")
print(f"  '2H' in tree_1d_1h_1s_2c_2d: {'2H' in tree_1d_1h_1s_2c_2d}")
print(f"  tree_1d_1h_1s_2c_2d.get('2H'): {tree_1d_1h_1s_2c_2d.get('2H')}")
