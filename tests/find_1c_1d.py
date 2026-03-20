from knowledge.loader import JFLoader

loader = JFLoader('JF实战_标准自然 - Rev 3.2.docx')
segments = loader.load()

print("查找包含1C-1D的片段:")
for i, segment in enumerate(segments):
    keywords = segment['keywords']
    for keyword in keywords:
        if '1C-1D' in keyword or '1C-1D' in keyword.upper():
            print(f"\n片段{i}:")
            print(f"  关键词: {keywords}")
            print(f"  内容前500字符:")
            print(f"  {segment['content'][:500]}")
            break
