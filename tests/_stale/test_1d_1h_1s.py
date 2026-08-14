from knowledge.loader import JFLoader, parse_content_to_tree, navigate_tree_by_bids, extract_bids_from_sequence, get_subsequent_bids_from_node
import json

loader = JFLoader('JF实战_标准自然 - Rev 3.2.docx')
segments = loader.load()

content = segments[17]['content']

print("=" * 80)
print("测试：1D-1H-1S序列")
print("=" * 80)

tree, keyword_bids = parse_content_to_tree(content)
print(f"关键词叫品: {keyword_bids}")
print(f"\n树结构:")
print(json.dumps(tree, indent=2, ensure_ascii=False))

bidding_sequence = "(南)1D-(西)pass-(北)1H-(东)pass-(南)1S-(西)pass-"
bids_in_sequence = extract_bids_from_sequence(bidding_sequence)
print(f"\n叫牌序列: {bidding_sequence}")
print(f"叫品列表: {bids_in_sequence}")

start_idx = 1
partner_node = navigate_tree_by_bids(tree, bids_in_sequence, start_idx=start_idx)
print(f"\n导航结果:")
print(f"队友叫品节点: {list(partner_node.keys()) if partner_node else 'None'}")

if partner_node:
    subsequent_bids = get_subsequent_bids_from_node(partner_node, content)
    print(f"\n后续叫品数量: {len(subsequent_bids)}")
    print(f"后续叫品:")
    for sb in subsequent_bids:
        print(f"  【{sb['bid']}】{sb['line'][:60]}")
