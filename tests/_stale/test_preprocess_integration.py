from knowledge.loader import JFLoader, JFRetriever

loader = JFLoader('JF实战_标准自然 - Rev 3.2.docx')
segments = loader.load()
retriever = JFRetriever(segments)

print("=" * 80)
print("测试预处理程序与整个程序的连接")
print("=" * 80)

test_cases = [
    ("1D-1H", "(南)1D-(西)pass-(北)1H-(东)pass-(南)1S-(西)pass-"),
    ("1C-1D", "(南)1C-(西)pass-(北)1D-(东)pass-(南)1H-(西)pass-"),
    ("2D-2NT", "(南)2D-(西)pass-(北)2NT-(东)pass-(南)3C-(西)pass-"),
    ("第三四家开叫1H", "(南)1H-(西)pass-(北)2C-(东)pass-"),
    ("第三四家开叫1S", "(南)1S-(西)pass-(北)2C-(东)pass-(南)2D-(西)pass-"),
]

for keyword, bidding_sequence in test_cases:
    print(f"\n{'='*80}")
    print(f"关键词: {keyword}")
    print(f"叫牌序列: {bidding_sequence}")
    print(f"{'='*80}")
    
    result = retriever.retrieve_with_preprocess(keyword, bidding_sequence, "北")
    
    print(f"有结构: {result['has_structure']}")
    print(f"是结构化约定: {result['is_structural_convention']}")
    print(f"队友叫品: {result['partner_bid']}")
    print(f"后续叫品数量: {len(result['subsequent_bids'])}")
    
    if result['subsequent_bids']:
        print(f"后续叫品:")
        for sb in result['subsequent_bids'][:5]:
            print(f"  【{sb['bid']}】{sb['line'][:60]}")
        if len(result['subsequent_bids']) > 5:
            print(f"  ... 还有{len(result['subsequent_bids']) - 5}个")
