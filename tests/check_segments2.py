from docx import Document
from pathlib import Path

docx_path = Path(r'd:\Bridge Card\Bidding System\JF实战_标准自然_For DIFY - Rev 3.1.docx')
doc = Document(docx_path)

print("按双换行（连续两个空段落）分割测试:")
segments = []
current_segment = []
empty_count = 0

for para in doc.paragraphs:
    text = para.text.strip()
    if not text:
        empty_count += 1
        if empty_count >= 2 and current_segment:
            segments.append("\n".join(current_segment))
            current_segment = []
    else:
        if empty_count >= 2 and current_segment:
            segments.append("\n".join(current_segment))
            current_segment = []
        current_segment.append(text)
        empty_count = 0

if current_segment:
    segments.append("\n".join(current_segment))

print(f"得到 {len(segments)} 个片段")

print("\n前10个片段预览:")
for i, seg in enumerate(segments[:10]):
    print(f"\n--- 片段 {i+1} ---")
    first_line = seg.split('\n')[0] if seg else ""
    print(f"首行: {first_line}")
    print(f"长度: {len(seg)} 字符")
