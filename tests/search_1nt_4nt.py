import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from knowledge.loader import JFLoader, preprocess_jf_content, extract_bids_from_sequence
import json

loader = JFLoader('JF实战_标准自然 - Rev 3.2.docx')
segments = loader.load()

print("=" * 80)
print("搜索关键词：1NT-4NT")
print("=" * 80)

found = False
for i, segment in enumerate(segments, 1):
    keywords = segment.get('keywords', [])
    content = segment.get('content', '')
    
    for keyword in keywords:
        if '1NT-4NT' in keyword or '1NT-4NT' in content:
            print(f"\n{'=' * 80}")
            print(f"段落 {i}")
            print(f"关键词: {keywords}")
            print(f"{'=' * 80}")
            
            print(f"内容长度: {len(content)} 字符")
            print(f"内容预览: {content[:300]}...")
            
            test_sequences = [
                "(南)1NT-(西)pass-(北)4NT-(东)pass-",
                "(南)1NT-(西)pass-(北)5NT-(东)pass-",
                "(南)1NT-(西)pass-(北)6NT-(东)pass-",
            ]
            
            for j, bidding_sequence in enumerate(test_sequences, 1):
                print(f"\n{'-' * 80}")
                print(f"测试序列 {j}: {bidding_sequence}")
                print('-' * 80)
                
                result = preprocess_jf_content(content, bidding_sequence, partner_name="北", keyword=keyword)
                
                print(f"\n【预处理结果】")
                print(f"队友叫品: {result['partner_bid']}")
                print(f"是否有结构: {result['has_structure']}")
                print(f"是否结构性约定: {result['is_structural_convention']}")
                
                print(f"\n【后续叫品】")
                if result['subsequent_bids']:
                    for k, bid_info in enumerate(result['subsequent_bids'], 1):
                        print(f"{k}. 【{bid_info['bid']}】{bid_info['line'][:100]}{'...' if len(bid_info['line']) > 100 else ''}")
                else:
                    print("无后续叫品")
            
            found = True
            break
    
    if found:
        break

if not found:
    print("\n未找到包含'1NT-4NT'的关键词")
    print("\n搜索包含'1NT'和'4NT'的关键词:")
    for i, segment in enumerate(segments, 1):
        keywords = segment.get('keywords', [])
        for keyword in keywords:
            if '1NT' in keyword and '4NT' in keyword:
                print(f"{i}. {keyword}")
