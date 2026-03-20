from knowledge.loader import JFLoader, parse_indent_level

loader = JFLoader('JF实战_标准自然 - Rev 3.2.docx')
segments = loader.load()
content = segments[17]['content']

lines = content.split('\n')
print('前30行的缩进级别:')
for i, line in enumerate(lines[:30]):
    indent = parse_indent_level(line)
    print(f'{i}: indent={indent} | {line}')
