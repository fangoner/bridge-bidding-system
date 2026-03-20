from knowledge.loader import JFLoader, parse_content_to_tree, navigate_tree_by_bids, extract_bids_from_sequence, get_subsequent_bids_from_node

loader = JFLoader('JF实战_标准自然 - Rev 3.2.docx')
segments = loader.load()

# 片段17内容
content = segments[17]['content']

print("=" * 80)
print("测试序列1: (南)1D-(西)pass-(北)1H-(东)pass-(南)1S-(西)pass-")
print("=" * 80)

bidding_sequence1 = "(南)1D-(西)pass-(北)1H-(东)pass-(南)1S-(西)pass-"
bids_in_sequence1 = extract_bids_from_sequence(bidding_sequence1)
print(f"叫品列表: {bids_in_sequence1}")

tree, keyword_bids = parse_content_to_tree(content)
print(f"关键词叫品: {keyword_bids}")

partner_node1 = navigate_tree_by_bids(tree, bids_in_sequence1)
if partner_node1:
    partner_bid = list(partner_node1.keys())[0]
    print(f"\n找到队友叫品节点: {partner_bid}")
    subsequent_bids = get_subsequent_bids_from_node(partner_node1, content)
    print(f"后续叫品数量: {len(subsequent_bids)}")
    print(f"后续叫品:")
    for sb in subsequent_bids:
        print(f"  【{sb['bid']}】{sb['line'][:70]}")
else:
    print("\n未找到队友叫品节点")

print("\n" + "=" * 80)
print("测试序列2: (南)1D-(西)pass-(北)1H-(东)pass-(南)1S-(西)pass-(北)2D-(东)pass-")
print("=" * 80)

bidding_sequence2 = "(南)1D-(西)pass-(北)1H-(东)pass-(南)1S-(西)pass-(北)2D-(东)pass-"
bids_in_sequence2 = extract_bids_from_sequence(bidding_sequence2)
print(f"叫品列表: {bids_in_sequence2}")

partner_node2 = navigate_tree_by_bids(tree, bids_in_sequence2)
if partner_node2:
    partner_bid = list(partner_node2.keys())[0]
    print(f"\n找到队友叫品节点: {partner_bid}")
    subsequent_bids = get_subsequent_bids_from_node(partner_node2, content)
    print(f"后续叫品数量: {len(subsequent_bids)}")
    print(f"后续叫品:")
    for sb in subsequent_bids:
        print(f"  【{sb['bid']}】{sb['line'][:70]}")
else:
    print("\n未找到队友叫品节点")
