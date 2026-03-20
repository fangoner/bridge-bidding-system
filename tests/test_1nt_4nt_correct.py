import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from knowledge.loader import JFLoader, preprocess_jf_content
from bridge.bidding import extract_retrieval_keyword
import json

loader = JFLoader('JF实战_标准自然 - Rev 3.2.docx')
segments = loader.load()

bidding_sequence = "(南)1NT-(西)pass-(北)4NT-(东)pass-"

print("=" * 80)
print(f"叫牌序列: {bidding_sequence}")
print("=" * 80)

keyword = extract_retrieval_keyword(bidding_sequence)
print(f"\nextract_retrieval_keyword提取的关键词: {keyword}")

for i, segment in enumerate(segments, 1):
    keywords = segment.get('keywords', [])
    content = segment.get('content', '')
    
    for k in keywords:
        if k == keyword:
            print(f"\n{'=' * 80}")
            print(f"找到匹配的段落 {i}")
            print(f"关键词: {keywords}")
            print(f"{'=' * 80}")
            print(f"内容:\n{content}")
            
            result = preprocess_jf_content(content, bidding_sequence, partner_name="北", keyword=keyword)
            
            print(f"\n{'=' * 80}")
            print(f"【预处理结果】")
            print(f"队友叫品: {result['partner_bid']}")
            print(f"是否有结构: {result['has_structure']}")
            print(f"是否结构性约定: {result['is_structural_convention']}")
            
            print(f"\n【后续叫品】")
            if result['subsequent_bids']:
                for j, bid_info in enumerate(result['subsequent_bids'], 1):
                    print(f"{j}. 【{bid_info['bid']}】{bid_info['line'][:100]}{'...' if len(bid_info['line']) > 100 else ''}")
            else:
                print("无后续叫品")
            
            print(f"\n【完整JSON】")
            print(json.dumps(result, ensure_ascii=False, indent=2))
            break
    
    if keyword in keywords:
        break
