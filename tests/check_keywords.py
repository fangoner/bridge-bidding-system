import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from knowledge.loader import JFLoader
import json

loader = JFLoader('JF实战_标准自然 - Rev 3.2.docx')
segments = loader.load()

print("=" * 80)
print("所有关键词列表")
print("=" * 80)

for i, segment in enumerate(segments, 1):
    keywords = segment.get('keywords', [])
    print(f"{i}. {keywords}")
    for keyword in keywords:
        if '1NT' in keyword:
            print(f"   -> 包含1NT: {keyword}")

print("\n" + "=" * 80)
print("搜索包含'应叫'的关键词")
print("=" * 80)

for i, segment in enumerate(segments, 1):
    keywords = segment.get('keywords', [])
    for keyword in keywords:
        if '应叫' in keyword:
            print(f"{i}. {keyword}")
