from knowledge.loader import JFLoader, parse_indent_level

loader = JFLoader('JF实战_标准自然 - Rev 3.2.docx')
segments = loader.load()
content = segments[17]['content']

lines = [l.rstrip() for l in content.splitlines() if l.strip()]

print('前10行的缩进级别:')
for i, line in enumerate(lines[:10]):
    indent = parse_indent_level(line)
    print(f'{i}: indent={indent} | {line}')

print('\n问题分析:')
print('1D-1H是关键词行，应该跳过')
print('├1S是depth=0，应该是1H的子节点')
print('│-----├1NT是depth=1，应该是1S的子节点')
print('\n所以depth=0的行应该添加到1H下，depth=1的行应该添加到1S下')
print('初始栈应该让depth=0的行添加到1H下')
