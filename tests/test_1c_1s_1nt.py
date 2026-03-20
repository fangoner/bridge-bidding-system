from knowledge.loader import JFLoader, preprocess_jf_content
from main import extract_retrieval_keyword

loader = JFLoader('JF实战_标准自然 - Rev 3.2.docx')

# 测试双人模式下的序列
bidding_sequence = "(南)1C-(西)pass-(北)1S-(东)pass-(南)1NT-"

print(f"=== 双人模式序列测试 ===")
print(f"完整序列: {bidding_sequence}")

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
        print(f"\n=== 找到相关片段 ===")
        print(f"内容前500字符:")
        print(content[:500])
        
        result = preprocess_jf_content(content, bidding_sequence, "南", keyword)
        print(f"\n预处理结果: 有结构={result['has_structure']}, 后续叫品数量={len(result['subsequent_bids'])}")
        if result['subsequent_bids']:
            for sb in result['subsequent_bids']:
                print(f"  - {sb['bid']}: {sb['line']}")
        else:
            print("  (无后续叫品)")
        break

if not found:
    print("\n未找到相关片段")
    
# 检查序列解析是否正确
print(f"\n=== 序列解析检查 ===")
print(f"当前叫牌人: 南")
print(f"最后一个叫品: 1NT")
print(f"前一个叫品: 1S (北)")
print(f"序列模式: 1C-1S-1NT")

# 尝试不同的关键词
print(f"\n=== 尝试其他可能的关键词 ===")
test_keywords = [
    "1C-1S-1NT",
    "1C-1S",
    "1S-1NT", 
    "1NT",
    "1C开叫",
    "1S应叫"
]

for test_keyword in test_keywords:
    print(f"\n--- 测试关键词: {test_keyword} ---")
    for seg in segments:
        content = seg.get('content', '')
        if test_keyword in content:
            print(f"找到包含 '{test_keyword}' 的片段")
            result = preprocess_jf_content(content, bidding_sequence, "南", test_keyword)
            print(f"预处理结果: 有结构={result['has_structure']}, 后续叫品数量={len(result['subsequent_bids'])}")
            if result['subsequent_bids']:
                for sb in result['subsequent_bids'][:3]:
                    print(f"  - {sb['bid']}: {sb['line'][:50]}...")
            break
