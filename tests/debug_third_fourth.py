from knowledge.loader import JFLoader, parse_content_to_tree, navigate_tree_by_bids, extract_bids_from_sequence, get_subsequent_bids_from_node
import json

loader = JFLoader('JF实战_标准自然 - Rev 3.2.docx')
segments = loader.load()

content = segments[43]['content']

print("=" * 80)
print("原始内容:")
print("=" * 80)
print(content[:800])

print("\n" + "=" * 80)
print("树结构转换:")
print("=" * 80)
tree, keyword_bids = parse_content_to_tree(content)
print(f"关键词叫品: {keyword_bids}")
print(f"\n树结构:")
print(json.dumps(tree, indent=2, ensure_ascii=False))

print("\n" + "=" * 80)
print("手动导航测试:")
print("=" * 80)

test_cases = [
    ("(南)1H-(西)pass-(北)1S-(东)pass-", ['1H', '1S']),
    ("(南)1H-(西)pass-(北)1NT-(东)pass-", ['1H', '1NT']),
    ("(南)1H-(西)pass-(北)2C-(东)pass-", ['1H', '2C']),
    ("(南)1H-(西)pass-(北)2C-(东)pass-(南)2D-(西)pass-", ['1H', '2C', '2D']),
    ("(南)1H-(西)pass-(北)2C-(东)pass-(南)2H-(西)pass-", ['1H', '2C', '2H']),
]

for i, (bidding_sequence, bids_in_sequence) in enumerate(test_cases, 1):
    print(f"\n测试序列{i}: {bidding_sequence}")
    print(f"叫品列表: {bids_in_sequence}")
    
    print(f"\n手动导航:")
    node = tree
    for bid in bids_in_sequence:
        print(f"  当前节点: {list(node.keys()) if node else 'None'}")
        print(f"  查找: {bid}")
        next_node = node.get(bid)
        print(f"  结果: {list(next_node.keys()) if next_node else 'None'}")
        if next_node is None:
            print(f"  找不到节点，退出")
            break
        node = next_node
    
    print(f"\n最终节点: {list(node.keys()) if node else 'None'}")
    
    print(f"\n使用navigate_tree_by_bids函数:")
    partner_node = navigate_tree_by_bids(tree, bids_in_sequence, start_idx=0)
    print(f"结果节点: {list(partner_node.keys()) if partner_node else 'None'}")
    
    if partner_node is not None:
        subsequent_bids = get_subsequent_bids_from_node(partner_node, content)
        print(f"后续叫品数量: {len(subsequent_bids)}")
        if subsequent_bids:
            print(f"后续叫品:")
            for sb in subsequent_bids:
                print(f"  【{sb['bid']}】{sb['line'][:70]}")
        else:
            print(f"没有后续叫品（该节点没有子节点）")
