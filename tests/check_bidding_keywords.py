import sys
sys.path.insert(0, r'd:\Bridge Card\Bidding System')

from knowledge.loader import JFLoader, JFRetriever
from config import JF_CONVENTION_FILE

loader = JFLoader(JF_CONVENTION_FILE)
segments = loader.load()

print("检查JF文档中叫牌序列相关的关键字:")
print("=" * 60)

bidding_keywords = []
for i, seg in enumerate(segments):
    lines = seg['content'].split('\n')
    for j, line in enumerate(lines[:3]):
        line = line.strip()
        if '-' in line and any(c.isdigit() for c in line):
            bidding_keywords.append((i+1, j+1, line))

for seg_num, line_num, keyword in bidding_keywords[:30]:
    print(f"片段{seg_num} 第{line_num}行: {keyword}")
