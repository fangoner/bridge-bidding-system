import json
import re
from pathlib import Path

BASE = Path(__file__).resolve().parent.parent
PDF_DIR = BASE / "scripts" / "xr_data" / "pdf_tables"

SUIT_FIX = {"今": "S", "会": "S", "令": "D", "曾": "H", "萼": "H", "¥": "H", "＊": "C", "*": "C",
            "+": "C", "孽": "H", "簪": "H", "＂": "H", "｀": "C", "等": "C", "停": "C", "喻": "H",
            "管": "S", "ft": "C", "tft": "C", "4ft": "C", "lt": "C", "1t": "C", "tt": "C"}
SUIT_CH = {"♣": "C", "♦": "D", "♥": "H", "♠": "S"}
SUIT_C = {"C": "♣", "D": "♦", "H": "♥", "S": "♠"}
NOISE = "·•。,，。；;::：！!？?~～—－—“”\"'’`｜|（）()［］[]【】"


def clean(s: str) -> str:
    for k, v in SUIT_FIX.items():
        s = s.replace(k, v)
    for ch, c in SUIT_CH.items():
        s = s.replace(ch, c)
    s = s.replace("l", "1").replace("I", "1").replace("L", "1")
    s = s.translate(str.maketrans("０１２３４５６７８９", "0123456789"))
    return s


def parse_seq_text(tail: str):
    s = clean(tail)
    if "第三四家" in s or "一二家不同" in s or "一二家" in s:
        return "3rd"
    s = s.replace("迈克尔斯扣叫", "").replace("特殊2NT", "").replace("兰迪", "")
    s = re.sub(r"后续.*$", "", s)
    s = re.sub(r"都是进局逼叫.*$", "", s)
    s = re.sub(r"（单缺答叫）.*$", "", s)
    s = re.sub(r"的争议.*$", "", s)
    s = re.sub(r"叫.*$", "", s)
    s = re.sub(r"应叫.*$", "", s)
    s = ("".join(ch for ch in s if ch not in NOISE))
    s = s.replace("一", "-").replace("－", "-").replace("—", "-")
    s = s.replace("(X)", "(X)").replace("（X)", "(X)").replace("(X）", "(X)")
    s = s.replace("（", "(").replace("）", ")")
    s = s.replace("／", "/").replace("/", "/")
    tokens = []
    i = 0
    while i < len(s):
        c = s[i]
        if c == "-":
            i += 1
            continue
        if c == "(":
            j = s.find(")", i)
            if j == -1:
                return None
            inner = s[i + 1:j]
            bids = []
            for part in inner.split("/"):
                part = part.strip()
                if part.lower() in ("pass", "p"):
                    bids.append(("pass",))
                elif part in ("X", "x"):
                    bids.append(("X",))
                elif part in ("XX", "xx"):
                    bids.append(("XX",))
                else:
                    m = re.match(r"^([1-7])(NT)?$", part)
                    if m:
                        bids.append((m.group(1) + "NT",))
                        continue
                    mm = re.match(r"^([1-7])([CDHS])$", part)
                    if mm:
                        bids.append((mm.group(1) + mm.group(2),))
                    else:
                        return None
            tokens.append(bids)
            i = j + 1
            continue
        m = re.match(r"^([1-7])(NT)", s[i:])
        if m:
            tokens.append([m.group(1) + "NT"])
            i += len(m.group(0))
            continue
        m = re.match(r"^([1-7])([CDHS])", s[i:])
        if m:
            tokens.append([m.group(1) + m.group(2)])
            i += len(m.group(0))
            continue
        if c in ("X", "x"):
            tokens.append(["X"])
            i += 1
            continue
        return None
    flat = []
    for t in tokens:
        flat.append("/".join(t))
    return "-".join(flat)


def main():
    files = sorted([f for f in PDF_DIR.glob("tables_ch*.json")])
    seq = {}
    tails = {}
    for f in files:
        data = json.loads(f.read_text(encoding="utf-8"))
        for tb in data:
            tid = tb["table_id"]
            tail = tb.get("tail", "") or ""
            if not tail:
                title = tb.get("title", "")
                m = re.search(r"表\d+[-—－一]\d+\s?(.*)$", title)
                tail = m.group(1) if m else ""
            parsed = parse_seq_text(tail)
            if tid not in seq and parsed:
                seq[tid] = parsed
                tails[tid] = tail
            elif parsed and tid in seq:
                if len(parsed.replace("-", "")) > len(seq[tid].replace("-", "")):
                    seq[tid] = parsed
                    tails[tid] = tail
    out = BASE / "scripts" / "xr_data" / "tables_seq.json"
    out.write_text(json.dumps(seq, ensure_ascii=False, indent=1), encoding="utf-8")
    (BASE / "scripts" / "xr_data" / "tables_tail.json").write_text(
        json.dumps(tails, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"saved {len(seq)} seqs -> {out}")
    for tid in sorted(seq, key=lambda t: (int(t.split("-")[0]), int(t.split("-")[1]))):
        print(f"  {tid}  {seq[tid]!r}  <-- {tails[tid][:40]!r}")


if __name__ == "__main__":
    main()