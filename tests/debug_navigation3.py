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

print("\n手动导航:")
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
    print(f"\n索引{i}: 查找 {bid}")
    print(f"  当前节点: {list(node.keys()) if node else 'None'}")
    print(f"  node.get('{bid}'): {node.get(bid)}")
    node = node.get(bid)
    print(f"  结果节点: {list(node.keys()) if node else 'None'}")
    if node is None:
        print(f"  找不到节点，退出")
        break

print(f"\n最终节点: {list(node.keys()) if node else 'None'}")

print("\n使用navigate_tree_by_bids函数:")
partner_node = navigate_tree_by_bids(tree, bids_in_sequence, start_idx=start_idx)
print(f"结果节点: {list(partner_node.keys()) if partner_node else 'None'}")
