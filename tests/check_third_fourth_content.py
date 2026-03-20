from knowledge.loader import JFLoader, parse_indent_level

loader = JFLoader('JF实战_标准自然 - Rev 3.2.docx')
segments = loader.load()

content = segments[43]['content']

print("原始内容:")
print(content)
print("\n" + "=" * 80)
print("前20行的缩进级别:")
print("=" * 80)

lines = content.split('\n')
for i, line in enumerate(lines[:20]):
    indent = parse_indent_level(line)
    print(f'{i}: indent={indent} | {line}')
