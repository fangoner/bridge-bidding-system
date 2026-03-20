import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from knowledge.loader import JFLoader
import json

loader = JFLoader('JF实战_标准自然 - Rev 3.2.docx')
segments = loader.load()

print("=" * 80)
print("搜索包含'1NT'的所有段落")
print("=" * 80)

for i, segment in enumerate(segments, 1):
    content = segment.get('content', '')
    if '1NT' in content:
        keywords = segment.get('keywords', [])
        print(f"\n段落 {i}:")
        print(f"关键词: {keywords}")
        print(f"内容预览: {content[:200]}...")
        print("-" * 80)
