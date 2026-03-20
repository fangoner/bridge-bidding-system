from knowledge.loader import JFLoader, JFRetriever

loader = JFLoader('JF实战_标准自然 - Rev 3.2.docx')
segments = loader.load()
retriever = JFRetriever(segments)

print("=" * 80)
print("验证1D-1H-1S的后续叫品")
print("=" * 80)

keyword = "1D-1H"
bidding_sequence = "(南)1D-(西)pass-(北)1H-(东)pass-(南)1S-(西)pass-"
player = "北"

result = retriever.retrieve_with_preprocess(keyword, bidding_sequence, player)

print(f"关键词: {keyword}")
print(f"叫牌序列: {bidding_sequence}")
print(f"玩家: {player}")
print(f"有结构: {result['has_structure']}")
print(f"是结构化约定: {result['is_structural_convention']}")
print(f"队友叫品: {result['partner_bid']}")
print(f"\n后续叫品（共{len(result['subsequent_bids'])}个）:")
for i, sb in enumerate(result['subsequent_bids'], 1):
    print(f"{i:2d}. 【{sb['bid']}】{sb['line']}")
