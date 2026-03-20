import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from knowledge.loader import JFLoader

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
        if keyword == '1NT-4NT':
            print(f"\n{'=' * 80}")
            print(f"段落 {i}")
            print(f"关键词: {keywords}")
            print(f"{'=' * 80}")
            print(f"内容长度: {len(content)} 字符")
            print(f"内容预览: {content[:500]}...")
            found = True
            break
    
    if found:
        break

if not found:
    print("\n未找到关键词'1NT-4NT'")
    print("\n搜索包含'1NT'和'4NT'的关键词:")
    for i, segment in enumerate(segments, 1):
        keywords = segment.get('keywords', [])
        for keyword in keywords:
            if '1NT' in keyword and '4NT' in keyword:
                print(f"{i}. {keyword}")
