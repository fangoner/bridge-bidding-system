import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from bridge.bidding import extract_retrieval_keyword

bidding_sequence = "(南)1NT-(西)pass-(北)4NT-(东)pass-"

keyword = extract_retrieval_keyword(bidding_sequence)

print("=" * 80)
print(f"叫牌序列: {bidding_sequence}")
print(f"提取的关键词: {keyword}")
print("=" * 80)
