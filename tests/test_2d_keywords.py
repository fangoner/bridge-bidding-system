from knowledge.loader import JFLoader, preprocess_jf_content
from main import extract_retrieval_keyword

loader = JFLoader('JF实战_标准自然 - Rev 3.2.docx')

# 测试不同的关键词提取逻辑
bidding_sequence = "(南)2D-"

# 尝试不同的关键词提取方式
keywords_to_try = ["2D开叫", "2D开叫", "2D", "开叫2D"]

for keyword in keywords_to_try:
    print(f"\n=== 测试关键词: {keyword} ===")
    
    # 预处理结果
    segments = loader.load()
    found = False
    for seg in segments:
        content = seg.get('content', '')
        if keyword in content:
            found = True
            print(f'找到包含 {keyword} 的片段')
            print(content[:800])
            
            print('\n=== 预处理结果 ===')
            result = preprocess_jf_content(content, bidding_sequence, "", keyword)
            print(f"有结构: {result['has_structure']}")
            print(f"是结构性约定: {result['is_structural_convention']}")
            print(f"后续叫品数量: {len(result['subsequent_bids'])}")
            for sb in result['subsequent_bids']:
                print(f"  - {sb['bid']}: {sb['line']}")
            break
    
    if not found:
        print(f"未找到包含 {keyword} 的片段")
