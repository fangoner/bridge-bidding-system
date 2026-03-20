from knowledge.loader import JFLoader, parse_content_to_tree, navigate_tree_by_bids, extract_bids_from_sequence, get_subsequent_bids_from_node

loader = JFLoader('JF实战_标准自然 - Rev 3.2.docx')
segments = loader.load()
content = segments[17]['content']

print("=" * 80)
print("测试序列: (南)1D-(西)pass-(北)1H-(东)pass-(南)1S-(西)pass-")
print("=" * 80)

bidding_sequence = "(南)1D-(西)pass-(北)1H-(东)pass-(南)1S-(西)pass-"
bids_in_sequence = extract_bids_from_sequence(bidding_sequence)
print(f"叫品列表: {bids_in_sequence}")

tree, keyword_bids = parse_content_to_tree(content)
print(f"关键词叫品: {keyword_bids}")

start_idx = 0
if keyword_bids and len(keyword_bids) >= 2:
    start_idx = 1

print(f"起始索引: {start_idx}")

partner_node = navigate_tree_by_bids(tree, bids_in_sequence, start_idx=start_idx)
if partner_node is not None:
    print(f"\n找到队友叫品节点")
    subsequent_bids = get_subsequent_bids_from_node(partner_node, content)
    print(f"后续叫品数量: {len(subsequent_bids)}")
    if subsequent_bids:
        print(f"后续叫品:")
        for sb in subsequent_bids:
            print(f"  【{sb['bid']}】{sb['line'][:70]}")
    else:
        print(f"没有后续叫品（该节点没有子节点）")
else:
    print("\n未找到队友叫品节点")

print("\n" + "=" * 80)
print("测试序列2: (南)1D-(西)pass-(北)1H-(东)pass-(南)1S-(西)pass-(北)1NT-(东)pass-")
print("=" * 80)

bidding_sequence2 = "(南)1D-(西)pass-(北)1H-(东)pass-(南)1S-(西)pass-(北)1NT-(东)pass-"
bids_in_sequence2 = extract_bids_from_sequence(bidding_sequence2)
print(f"叫品列表: {bids_in_sequence2}")

partner_node2 = navigate_tree_by_bids(tree, bids_in_sequence2, start_idx=start_idx)
if partner_node2 is not None:
    print(f"\n找到队友叫品节点")
    subsequent_bids2 = get_subsequent_bids_from_node(partner_node2, content)
    print(f"后续叫品数量: {len(subsequent_bids2)}")
    if subsequent_bids2:
        print(f"后续叫品:")
        for sb in subsequent_bids2:
            print(f"  【{sb['bid']}】{sb['line'][:70]}")
    else:
        print(f"没有后续叫品（该节点没有子节点）")
else:
    print("\n未找到队友叫品节点")
