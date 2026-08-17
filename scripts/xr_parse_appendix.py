import json
import re
from pathlib import Path

BASE = Path(__file__).resolve().parent.parent
SRC = BASE / "书籍" / "新睿桥牌二盖一体系.md"
OUT = BASE / "scripts" / "xr_data" / "tables_seq.json"

SUIT_FIX = [
    ("4ft", "C"), ("14ft", "C"), ("24ft", "C"), ("1ft", "C"), ("2ft", "C"), ("3ft", "C"),
    ("5ft", "C"), ("6ft", "C"), ("7ft", "C"), ("ft", "C"), ("lt", "C"), ("1t", "C"),
    ("2t", "C"), ("3t", "C"), ("4t", "C"), ("5t", "C"), ("6t", "C"), ("7t", "C"),
    ("tft", "C"), ("4ft", "C"),
    ("今", "S"), ("会", "S"), ("令", "D"), ("曾", "H"), ("萼", "H"), ("¥", "H"),
    ("等", "C"), ("*", "C"), ("＊", "C"), ("＋", ""), ("+", ""),
    ("l", "1"), ("I换成", "1"), ("I", "1"),
]
SUIT_CH = {"♣": "C", "♦": "D", "♥": "H", "♠": "S"}
NOISE = "·•。，,；;::：！!？?~～—－—_｜|【】,.："


def clean(s: str) -> str:
    s = s.replace(" ", "")
    for k, v in SUIT_FIX:
        s = s.replace(k, v)
    for ch, c in SUIT_CH.items():
        s = s.replace(ch, c)
    s = s.translate(str.maketrans("０１２３４５６７８９", "0123456789"))
    return s


LINE_RE = re.compile(r"表\s*(\d+)[-—－一](\d+)\s*(.*)$")


def parse_seq(s: str):
    s = clean(s)
    s = s.replace("一", "-").replace("－", "-").replace("—", "-")
    s = s.replace("(", "(").replace("）", ")").replace("（", "(")
    s = s.replace("/", "/")
    s = re.sub(r"(?:迈克尔斯|特殊2NT|兰迪|跳新花阻击|跳加叫阻击|斯普林特|跳叫2NT|一盖一逼叫|2NT重询|3\+重询|新高花逼局|逆叫|邀请).*$", "", s)
    tokens = []
    i = 0
    n = len(s)
    while i < n:
        c = s[i]
        if c == "-":
            i += 1
            continue
        if c == "(":
            j = s.find(")", i)
            if j == -1:
                break
            inner = s[i + 1:j]
            alts = []
            for part in inner.split("/"):
                part = part.strip()
                if part.lower() in ("pass", "p", "pss"):
                    alts.append("pass")
                elif part in ("X", "XX", "x", "xx"):
                    alts.append("X" if len(part) == 1 else "XX")
                else:
                    alts.append(part)
            tokens.append("(" + "/".join(alts) + ")")
            i = j + 1
            continue
        m = re.match(r"^([1-7])(NT)", s[i:])
        if m:
            tokens.append(m.group(1) + "NT")
            i += len(m.group(0))
            continue
        m = re.match(r"^([1-7])([CDHS])", s[i:])
        if m:
            tokens.append(m.group(1) + m.group(2))
            i += len(m.group(0))
            continue
        if c in ("X", "x"):
            tokens.append("X")
            i += 1
            continue
        m = re.match(r"^([a-zA-Z0-9]+)", s[i:])
        if m:
            tokens.append(m.group(1))
            i += len(m.group(0))
            continue
        i += 1
    return "-".join(tokens)


def main():
    lines = SRC.read_text(encoding="utf-8").splitlines()
    start = None
    end = None
    for idx, line in enumerate(lines):
        if "附录一" in line and "叫牌过程索引" in line and start is None:
            start = idx
        elif "附录二" in line and "约定" in line and start is not None:
            end = idx
            break
    if start is None or end is None:
        print("appendix range not found")
        return
    seq = {}
    for line in lines[start:end]:
        m = LINE_RE.match(line.strip())
        if not m:
            continue
        tid = f"{m.group(1)}-{m.group(2)}"
        rest = m.group(3)
        parsed = parse_seq(rest)
        if parsed and ("-" in parsed or parsed == "3rd" or "(" in parsed or len(parsed) >= 2):
            if tid not in seq or len(parsed) > len(seq[tid]):
                seq[tid] = parsed
    OUT.write_text(json.dumps(seq, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"saved {len(seq)} seqs -> {OUT}")
    for tid in sorted(seq, key=lambda t: (int(t.split("-")[0]), int(t.split("-")[1]))):
        print(f"  {tid}  {seq[tid]}")


if __name__ == "__main__":
    main()