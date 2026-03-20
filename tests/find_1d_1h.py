from knowledge.loader import JFLoader

loader = JFLoader('JF实战_标准自然 - Rev 3.2.docx')
segments = loader.load()

print("查找包含1D-1H的片段:")
for i, segment in enumerate(segments):
    keywords = segment['keywords']
    for keyword in keywords:
        if '1D-1H' in keyword:
            print(f"\n片段{i}:")
            print(f"  关键词: {keywords}")
            print(f"  内容前1200字符:")
            print(f"  {segment['content'][:1200]}")
            break
