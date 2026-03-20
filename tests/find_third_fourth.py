from knowledge.loader import JFLoader

loader = JFLoader('JF实战_标准自然 - Rev 3.2.docx')
segments = loader.load()

print("查找包含第三四家开叫1高花的片段:")
for i, segment in enumerate(segments):
    keywords = segment['keywords']
    for keyword in keywords:
        if '第三四家开叫' in keyword and ('1H' in keyword or '1S' in keyword):
            print(f"\n片段{i}:")
            print(f"  关键词: {keywords}")
            print(f"  内容前800字符:")
            print(f"  {segment['content'][:800]}")
            break
