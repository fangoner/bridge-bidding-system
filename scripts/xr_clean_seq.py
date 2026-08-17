import json
import re
from pathlib import Path

BASE = Path(__file__).resolve().parent.parent
DATA = BASE / "scripts" / "xr_data"
PDF_DIR = DATA / "pdf_tables"

SEQ_SUIT = {
    "if": "C", "fi": "C", "f": "C", "ft": "C", "tft": "C", "lt": "C", "1t": "C",
    "tt": "C", "4ft": "C", "t": "C", "4": "C",
    "~": "S", "•": "S", "．": "S", "i": "S", "1'": "S",
    "｀": "C", "等": "C", "停": "C",
    "今": "S", "会": "S", "令": "D", "曾": "H", "萼": "H", "¥": "H", "喻": "H",
    "＊": "C", "*": "C", "+": "C", "管": "S",
}
SUIT_CH = {"♣": "C", "♦": "D", "♥": "H", "♠": "S"}

# 已验证的 ch2 手写 seq（覆盖附录噪声）
MANUAL_SEQ = {
    "2-1": "1C", "2-2": "1C-3rd", "2-3": "1C-1D", "2-4": "1C-1D-1H", "2-5": "1C-1D-1S",
    "2-6": "1C-1D-2C", "2-7": "1C-1D-2D", "2-8": "1C-1H", "2-9": "1C-1H-1S",
    "2-10": "1C-1H-2C", "2-11": "1C-1H-2H", "2-12": "1C-1H-2H-2NT", "2-13": "1C-1S",
    "2-14": "1C-1S-2C", "2-15": "1C-1S-2S", "2-16": "1C-1S-2S-2NT", "2-17": "1C-1D-1NT",
    "2-18": "1C-1D-1NT-2C-2D", "2-19": "1C-1D-1NT-2D", "2-20": "1C-1H-1NT",
    "2-21": "1C-1H-1NT-2C-2D", "2-22": "1C-1H-1NT-2D", "2-23": "1C-1S-1NT",
    "2-24": "1C-1S-1NT-2C-2D", "2-25": "1C-1S-1NT-2D", "2-26": "1C-1H-2C-2D",
    "2-27": "1C-1S-2C-2D", "2-28": "1C-1NT", "2-29": "1C-2C", "2-30": "1C-2C-2D",
    "2-31": "1C-2C-2H", "2-32": "1C-2C-2S", "2-33": "1C-2C-2NT", "2-34": "1C-2D",
    "2-35": "1C-2D-2NT", "2-36": "1C-2H", "2-37": "1C-2H-2NT", "2-38": "1C-2S",
    "2-39": "1C-2S-2NT", "2-40": "1C-2NT", "2-41": "1C-3C", "2-42": "1C-3D",
    "2-43": "1C-3H", "2-44": "1C-3S", "2-45": "1C-1H-2D", "2-46": "1C-1H-2D-2S",
    "2-47": "1C-1S-2D", "2-48": "1C-1S-2D-2H", "2-49": "1C-1S-2H", "2-50": "1C-1S-2H-2NT",
    "2-51": "1C-1NT-2D", "2-52": "1C-1NT-2H", "2-53": "1C-1NT-2S", "2-54": "1C-1D-2H",
    "2-55": "1C-1D-2S", "2-56": "1C-1H-2S", "2-57": "1C-1D-2NT", "2-58": "1C-1H-2NT",
    "2-59": "1C-1H-2NT-3C", "2-60": "1C-1S-2NT", "2-61": "1C-1S-2NT-3C",
    "2-62": "1C-1D-3C", "2-63": "1C-1H-3C", "2-64": "1C-1S-3C", "2-65": "1C-1NT-3C",
    "2-66": "1C-1D-3D", "2-67": "1C-1H-3H", "2-68": "1C-1S-3S",
}


def clean_seq(s: str):
    s = s.replace(" ", "").replace("（", "(").replace("）", ")")
    s = s.replace("一", "-").replace("－", "-").replace("—", "-")
    s = re.sub(r"-\d{2,3}$", "", s)  # 剥离尾部页码
    if "(" in s:
        return None  # 干扰序列，非线性树
    if "3rd" in s or "第三" in s:
        return "3rd" if s.strip() == "3rd" else None
    toks = []
    for t in s.split("-"):
        t = t.strip()
        if not t:
            continue
        if re.match(r"^\d+$", t):
            continue  # 孤立数字（页码/缺花色）
        nb = norm_tok(t)
        if nb is None:
            return None
        toks.append(nb)
    if not toks:
        return None
    return "-".join(toks)


def norm_tok(tok):
    low = tok.lower()
    if low in ("pass", "p", "pss"):
        return "pass"
    if tok in ("X", "x"):
        return "X"
    if tok in ("XX", "xx"):
        return "XX"
    m = re.match(r"^(\d+)NT$", tok)
    if m:
        return m.group(1) + "NT"
    m = re.match(r"^(\d)([CDHScdhs])$", tok)
    if m:
        return m.group(1) + m.group(2).upper()
    m = re.match(r"^(\d)(.+)$", tok)
    if m:
        left = m.group(2)
        if left in SEQ_SUIT:
            return m.group(1) + SEQ_SUIT[left]
        for k in sorted(SEQ_SUIT, key=len, reverse=True):
            if left.endswith(k):
                return m.group(1) + SEQ_SUIT[k]
    return None


def main():
    appendix = json.loads((DATA / "tables_seq.json").read_text(encoding="utf-8"))
    tables = {}
    for f in sorted(PDF_DIR.glob("tables_ch*.json")):
        for t in json.loads(f.read_text(encoding="utf-8")):
            tables[t["table_id"]] = t
    valid = set(tables)
    out = {}
    missing = []
    for tid in sorted(valid, key=lambda t: (int(t.split("-")[0]), int(t.split("-")[1]))):
        if tid in MANUAL_SEQ:
            out[tid] = MANUAL_SEQ[tid]
            continue
        raw = appendix.get(tid, "")
        cs = clean_seq(raw) if raw else None
        if cs:
            out[tid] = cs
        else:
            missing.append(tid)
    (DATA / "tables_seq.json").write_text(
        json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"cleaned: {len(out)} seqs (manual {len([t for t in out if t in MANUAL_SEQ])}, appendix {len(out)-len([t for t in out if t in MANUAL_SEQ])})")
    print(f"SEQ_MISSING ({len(missing)}, 表存在但seq无法解析):")
    print("  " + ", ".join(missing))
    bad = [t for t in out if not re.match(r"^(?:[1-7](?:C|D|H|S|NT)|pass|X|XX)(?:-[1-7](?:C|D|H|S|NT|pass|X|XX))*$", out[t])]
    if bad:
        print("非规范seq:")
        for t in bad:
            print(f"  {t} {out[t]!r}")


if __name__ == "__main__":
    main()