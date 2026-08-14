from knowledge.loader import JFLoader, preprocess_jf_content
from main import extract_retrieval_keyword

loader = JFLoader('JF实战_标准自然 - Rev 3.2.docx')

# 用户给出的完整补全序列
bidding_sequence = "(南)1C-(西)pass-(北)1S-(东)pass-(南)1NT-(西)pass-"

print(f"=== 测试完整补全序列 ===")
print(f"完整序列: {bidding_sequence}")

# 检查不同叫牌人的关键词
positions = ["南", "西", "北", "东"]

for position in positions:
    keyword = extract_retrieval_keyword(bidding_sequence, "自然", position)
    print(f"\n=== 叫牌人 {position} ===")
    print(f"关键词: {keyword}")
    
    # 预处理结果
    segments = loader.load()
    found = False
    for seg in segments:
        content = seg.get('content', '')
        if keyword in content:
            found = True
            result = preprocess_jf_content(content, bidding_sequence, position, keyword)
            print(f"预处理结果: 有结构={result['has_structure']}, 后续叫品数量={len(result['subsequent_bids'])}")
            if result['subsequent_bids']:
                for sb in result['subsequent_bids'][:3]:
                    print(f"  - {sb['bid']}: {sb['line'][:50]}...")
            else:
                print("  (无后续叫品)")
            break
    
    if not found:
        print("未找到相关片段")

# 检查序列解析
print(f"\n=== 序列解析检查 ===")
from knowledge.loader import extract_bids_from_sequence
bids = extract_bids_from_sequence(bidding_sequence)
print(f"提取的叫品: {bids}")
print(f"叫品数量: {len(bids)}")
print(f"当前叫牌人: 北（下一个叫牌人）")
print(f"序列模式: 1C-1S-1NT")

# 检查关键词提取逻辑
print(f"\n=== 关键词提取逻辑检查 ===")
print(f"序列长度: {len(bids)}个叫品")
print(f"前两个叫品: {bids[0]}-{bids[1]}")
print(f"应该返回的关键词: {bids[0]}-{bids[1]}")
