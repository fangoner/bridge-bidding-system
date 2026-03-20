from knowledge.loader import JFLoader, parse_content_to_tree, navigate_tree_by_bids, get_subsequent_bids_from_node, extract_bids_from_sequence

loader = JFLoader('JF实战_标准自然 - Rev 3.2.docx')
segments = loader.load()

content = segments[17]['content']

print("=" * 80)
print("1D-1H原始内容（前30行）")
print("=" * 80)
lines = content.split('\n')
for i, line in enumerate(lines[:30]):
    print(f"{i:3d}: {line}")

print("\n" + "=" * 80)
print("1D-1H-1S后续叫品详细检查")
print("=" * 80)

tree, keyword_bids = parse_content_to_tree(content)
print(f"关键词叫品: {keyword_bids}")

bidding_sequence = "(南)1D-(西)pass-(北)1H-(东)pass-(南)1S-(西)pass-"
bids_in_sequence = extract_bids_from_sequence(bidding_sequence)
print(f"叫牌序列: {bidding_sequence}")
print(f"叫品列表: {bids_in_sequence}")

start_idx = 1
partner_node, partner_bid = navigate_tree_by_bids(tree, bids_in_sequence, start_idx=start_idx)
print(f"\n队友叫品: {partner_bid}")

if partner_node:
    subsequent_bids = get_subsequent_bids_from_node(partner_node, content)
    print(f"\n后续叫品（共{len(subsequent_bids)}个）:")
    for i, sb in enumerate(subsequent_bids, 1):
        print(f"{i:2d}. 【{sb['bid']}】{sb['line']}")
