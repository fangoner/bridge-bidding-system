import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from knowledge.loader import JFLoader, preprocess_jf_content, extract_bids_from_sequence
import json

loader = JFLoader('JF实战_标准自然 - Rev 3.2.docx')
segments = loader.load()

print("=" * 80)
print("测试：1NT应叫的预处理结果")
print("=" * 80)

found = False
for segment in segments:
    keywords = segment.get('keywords', [])
    content = segment['content']
    
    for keyword in keywords:
        if '1NT' in keyword and '应叫' in keyword:
            print(f"\n关键词: {keyword}")
            print(f"内容长度: {len(content)} 字符")
            print("\n" + "=" * 80)
            
            test_sequences = [
                "(南)1C-(西)pass-(北)1NT-(东)pass-",
                "(南)1D-(西)pass-(北)1NT-(东)pass-",
                "(南)1H-(西)pass-(北)1NT-(东)pass-",
                "(南)1S-(西)pass-(北)1NT-(东)pass-",
            ]
            
            for i, bidding_sequence in enumerate(test_sequences, 1):
                print(f"\n{'=' * 80}")
                print(f"测试序列 {i}: {bidding_sequence}")
                print('=' * 80)
                
                result = preprocess_jf_content(content, bidding_sequence, partner_name="北", keyword=keyword)
                
                print(f"\n【预处理结果】")
                print(f"队友叫品: {result['partner_bid']}")
                print(f"是否有结构: {result['has_structure']}")
                print(f"是否结构性约定: {result['is_structural_convention']}")
                
                print(f"\n【后续叫品】")
                if result['subsequent_bids']:
                    for j, bid_info in enumerate(result['subsequent_bids'], 1):
                        print(f"{j}. 【{bid_info['bid']}】{bid_info['line'][:80]}{'...' if len(bid_info['line']) > 80 else ''}")
                else:
                    print("无后续叫品")
                
                print(f"\n【完整JSON】")
                print(json.dumps(result, ensure_ascii=False, indent=2))
            
            found = True
            break
    
    if found:
        break

if not found:
    print("\n未找到包含'1NT应叫'的关键词")
    print("\n所有包含'1NT'的关键词:")
    for segment in segments:
        keywords = segment.get('keywords', [])
        for keyword in keywords:
            if '1NT' in keyword:
                print(f"  - {keyword}")
