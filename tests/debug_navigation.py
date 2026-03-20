from knowledge.loader import JFLoader, parse_content_to_tree, navigate_tree_by_bids, extract_bids_from_sequence, normalize_bid

loader = JFLoader('JF实战_标准自然 - Rev 3.2.docx')
segments = loader.load()
content = segments[17]['content']

bidding_sequence = "(南)1D-(西)pass-(北)1H-(东)pass-(南)1S-(西)pass-"
bids_in_sequence = extract_bids_from_sequence(bidding_sequence)
print(f"叫品列表: {bids_in_sequence}")

tree, keyword_bids = parse_content_to_tree(content)
print(f"关键词叫品: {keyword_bids}")

start_idx = 1
print(f"起始索引: {start_idx}")

print("\n导航过程:")
node = tree
for i in range(start_idx, len(bids_in_sequence)):
    bid = normalize_bid(bids_in_sequence[i])
    print(f"  索引{i}: 查找 {bid}")
    print(f"  当前节点: {list(node.keys()) if node else 'None'}")
    node = node.get(bid)
    print(f"  结果节点: {list(node.keys()) if node else 'None'}")
    if node is None:
        break

print(f"\n最终节点: {list(node.keys()) if node else 'None'}")
