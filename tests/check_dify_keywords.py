import sys
sys.path.insert(0, r'd:\Bridge Card\Bidding System')

from knowledge.loader import JFLoader, JFRetriever
from config import JF_CONVENTION_FILE

loader = JFLoader(JF_CONVENTION_FILE)
segments = loader.load()

keywords_from_dify = [
    "花色开叫",
    "第二家争叫",
    "第四家争叫",
    "我方开叫1低花",
    "我方开叫1高花",
    "我方开叫阻击",
    "我方开叫1NT",
    "我方开叫2C",
    "2NT均型强牌",
    "技术性加倍以后",
    "Michaels扣叫与两套牌争叫",
    "1NT争叫",
    "普通争叫",
    "对抗对方阻击叫",
    "对1NT开叫",
    "对精确1C和自然2C开叫",
    "成局与满贯",
    "自然叫牌",
    "平衡位置的叫牌",
    "第三四家开叫1H",
    "第三四家开叫1S",
]

print("检查Dify关键字在JF文档中的匹配情况:")
print("=" * 60)

for kw in keywords_from_dify:
    found = False
    found_in = []
    
    for i, seg in enumerate(segments):
        lines = seg['content'].split('\n')
        first_line = lines[0] if lines else ""
        second_line = lines[1] if len(lines) > 1 else ""
        
        if kw == first_line or kw == second_line:
            found = True
            found_in.append(f"片段{i+1} 完全匹配")
        elif kw in seg['content']:
            found = True
            found_in.append(f"片段{i+1} 包含")
    
    if found:
        print(f"✓ '{kw}': {', '.join(found_in)}")
    else:
        print(f"✗ '{kw}': 未找到")
