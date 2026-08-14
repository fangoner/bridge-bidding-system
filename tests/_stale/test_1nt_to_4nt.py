import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from knowledge.loader import JFLoader, preprocess_jf_content, extract_bids_from_sequence
import json

loader = JFLoader('JF实战_标准自然 - Rev 3.2.docx')
segments = loader.load()

print("=" * 80)
print("测试：1NT-4NT的预处理结果")
print("=" * 80)

for i, segment in enumerate(segments, 1):
    keywords = segment.get('keywords', [])
    content = segment.get('content', '')
    
    if '1NT开叫' in ' '.join(keywords) or '1NT开叫后的' in content:
        print(f"\n{'=' * 80}")
        print(f"段落 {i}")
        print(f"关键词: {keywords}")
        print(f"{'=' * 80}")
        
        test_sequences = [
            "(南)1NT-(西)pass-(北)2C-(东)pass-(南)2D-(西)pass-(北)2NT-(东)pass-(南)3NT-(西)pass-(北)4NT-(东)pass-",
            "(南)1NT-(西)pass-(北)4NT-(东)pass-",
            "(南)1NT-(西)pass-(北)2C-(东)pass-(南)2D-(西)pass-(北)3NT-(东)pass-",
            "(南)1NT-(西)pass-(北)2C-(东)pass-(南)2D-(西)pass-(北)4NT-(东)pass-",
        ]
        
        for j, bidding_sequence in enumerate(test_sequences, 1):
            print(f"\n{'-' * 80}")
            print(f"测试序列 {j}: {bidding_sequence}")
            print('-' * 80)
            
            keyword = keywords[0] if keywords else ""
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
            
            print(f"\n【完整JSON】")
            print(json.dumps(result, ensure_ascii=False, indent=2))
        
        break
