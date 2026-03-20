from knowledge.loader import JFLoader

loader = JFLoader('JF实战_标准自然 - Rev 3.2.docx')
segments = loader.load()

content = segments[3]['content']

print("=" * 80)
print("测试片段3：1C开叫")
print("=" * 80)

print("完整原始内容:")
print(content)
