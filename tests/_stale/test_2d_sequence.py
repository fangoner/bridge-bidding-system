from knowledge.loader import JFLoader, preprocess_jf_content
from main import extract_retrieval_keyword

loader = JFLoader('JF实战_标准自然 - Rev 3.2.docx')

# 双人模式下的序列
bidding_sequence = "(南)2D-"

# 提取关键词
keyword = extract_retrieval_keyword(bidding_sequence, "自然", "南")
print(f"序列: {bidding_sequence}")
print(f"关键词: {keyword}")
print()

# 预处理结果
segments = loader.load()
for seg in segments:
    content = seg.get('content', '')
    if keyword in content:
        print(f'=== 找到包含 {keyword} 的片段 ===')
        print(content[:1000])
        print('\n=== 预处理结果 ===')
        result = preprocess_jf_content(content, bidding_sequence, "", keyword)
        print(f"有结构: {result['has_structure']}")
        print(f"是结构性约定: {result['is_structural_convention']}")
        print(f"后续叫品数量: {len(result['subsequent_bids'])}")
        for sb in result['subsequent_bids']:
            print(f"  - {sb['bid']}: {sb['line']}")
        break
