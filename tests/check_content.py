from knowledge.loader import JFLoader

loader = JFLoader('JF实战_标准自然 - Rev 3.2.docx')
segments = loader.load()
content = segments[17]['content']

print('原始内容:')
print(content)
print('\n\n前30行:')
lines = content.split('\n')
for i, line in enumerate(lines[:30]):
    print(f'{i}: {line}')
