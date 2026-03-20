from knowledge.loader import JFLoader

loader = JFLoader('JF实战_标准自然 - Rev 3.2.docx')
segments = loader.load()

content = segments[17]['content']

print("=" * 80)
print("1D-1H原始内容")
print("=" * 80)
print(content)
