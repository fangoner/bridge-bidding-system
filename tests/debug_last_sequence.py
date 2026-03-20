from knowledge.loader import JFLoader, parse_content_to_tree, navigate_tree_by_bids, extract_bids_from_sequence, normalize_bid

loader = JFLoader('JF实战_标准自然 - Rev 3.2.docx')
segments = loader.load()
content = segments[17]['content']

bidding_sequence = "(南)1D-(西)pass-(北)1H-(东)pass-(南)1S-(西)pass-(北)2C-(东)pass-(南)2D-(西)pass-(北)2H-(东)pass-"
bids_in_sequence = extract_bids_from_sequence(bidding_sequence)
print(f"叫品列表: {bids_in_sequence}")

tree, keyword_bids = parse_content_to_tree(content)
print(f"关键词叫品: {keyword_bids}")

start_idx = 1

print("\n导航过程:")
node = tree
first_keyword = list(tree.keys())[0] if tree else None
print(f"第一个关键词: {first_keyword}")

first_bid = normalize_bid(bids_in_sequence[0])
print(f"第一个叫品: {first_bid}")

if first_bid == first_keyword:
    print(f"匹配，导航到 {first_keyword}")
    node = node.get(first_keyword)
    print(f"当前节点: {list(node.keys()) if node else 'None'}")

for i in range(start_idx, len(bids_in_sequence)):
    bid = normalize_bid(bids_in_sequence[i])
    print(f"  索引{i}: 查找 {bid}")
    print(f"  当前节点: {list(node.keys()) if node else 'None'}")
    node = node.get(bid)
    print(f"  结果节点: {list(node.keys()) if node else 'None'}")
    if node is None:
        break

print(f"\n最终节点: {list(node.keys()) if node else 'None'}")

print("\n检查2D节点:")
tree_1d_1h = tree['1D']['1H']
tree_1d_1h_1s = tree_1d_1h['1S']
tree_1d_1h_1s_2c = tree_1d_1h_1s['2C']
print(f"1D->1H->1S->2C的子节点: {list(tree_1d_1h_1s_2c.keys())}")
tree_1d_1h_1s_2c_2d = tree_1d_1h_1s_2c['2D']
print(f"1D->1H->1S->2C->2D的子节点: {list(tree_1d_1h_1s_2c_2d.keys())}")
