import sys
sys.path.insert(0, r'd:\Bridge Card\Bidding System')

from knowledge.loader import JFLoader
from config import JF_CONVENTION_FILE

loader = JFLoader(JF_CONVENTION_FILE)
segments = loader.load()

print("每个片段的前两行:")
print("=" * 60)

for i, seg in enumerate(segments[:30]):
    lines = seg['content'].split('\n')
    first = lines[0] if lines else ""
    second = lines[1] if len(lines) > 1 else ""
    print(f"\n片段 {i+1}:")
    print(f"  第1行: {first}")
    if second:
        print(f"  第2行: {second}")
