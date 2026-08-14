from knowledge.loader import JFLoader, preprocess_jf_content
from main import extract_retrieval_keyword

loader = JFLoader('JF实战_标准自然 - Rev 3.2.docx')

# 测试不同的序列
sequences = [
    "(南)1C-(西)pass-(北)1S-(东)pass-",  # 用户问的序列
    "(南)1C-(西)pass-(北)1S-(东)pass-(南)1NT-"  # 之前的完整序列
]

for bidding_sequence in sequences:
    print(f"\n=== 测试序列: {bidding_sequence} ===")
    
    # 提取关键词
    keyword = extract_retrieval_keyword(bidding_sequence, "自然", "南")
    print(f"关键词: {keyword}")
    
    # 预处理结果
    segments = loader.load()
    found = False
    for seg in segments:
        content = seg.get('content', '')
        if keyword in content:
            found = True
            print(f"找到相关片段")
            
            result = preprocess_jf_content(content, bidding_sequence, "南", keyword)
            print(f"预处理结果: 有结构={result['has_structure']}, 后续叫品数量={len(result['subsequent_bids'])}")
            if result['subsequent_bids']:
                for sb in result['subsequent_bids'][:5]:
                    print(f"  - {sb['bid']}: {sb['line'][:50]}...")
            else:
                print("  (无后续叫品)")
            break
    
    if not found:
        print("未找到相关片段")

# 检查不同叫牌人的关键词
print(f"\n=== 检查不同叫牌人的关键词 ===")

bidding_sequence = "(南)1C-(西)pass-(北)1S-(东)pass-"
positions = ["南", "西", "北", "东"]

for position in positions:
    keyword = extract_retrieval_keyword(bidding_sequence, "自然", position)
    print(f"叫牌人 {position}: 关键词 = {keyword}")