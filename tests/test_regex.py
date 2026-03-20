import re

line1 = "3.2        1D-1H后的进程"
line2 = "1D-1H"

pattern1 = r'[1-7](?:[CDHS]|NT)-[1-7](?:[CDHS]|NT)'
pattern2 = r'^[1-7](?:[CDHS]|NT)-[1-7](?:[CDHS]|NT)$'

print(f"行1: {line1}")
print(f"模式1匹配: {re.search(pattern1, line1)}")
print(f"模式2匹配: {re.search(pattern2, line1)}")

print(f"\n行2: {line2}")
print(f"模式1匹配: {re.search(pattern1, line2)}")
print(f"模式2匹配: {re.search(pattern2, line2)}")
