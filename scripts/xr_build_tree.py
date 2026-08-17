import json
import re
from pathlib import Path

BASE = Path(__file__).resolve().parent.parent
DATA = BASE / "scripts" / "xr_data"
TABLES_JSON = DATA / "pdf_tables" / "tables_ch2.json"
OUT_MD = DATA / "新睿实战_二盖一体系_试点.md"
OUT_JSON = DATA / "tables_built.json"

BAD_BID_ORDER = []

SECONDARY_TABLES = set()

SUIT_FIX = {"今": "♠", "会": "♠", "令": "♦", "曾": "♥", "萼": "♥", "¥": "♥", "＊": "♣", "*": "♣", "+": "♣",
            "孽": "♥", "簪": "♥", "＂": "♥", "｀": "♣", "等": "♣", "停": "♣", "喻": "♥", "管": "♠"}
LINK_FIX = {"表2习": "2-7"}
PAGE_NOISE_RE = re.compile(r"^(第[一二三四五六七八九十百]+章|续表|表\d+[-—－一]\d+.*|第[一二三四五六七八九十]+节|一、|二、|三、|四、|五、)")
BID_WORD_RE = re.compile(r"^[0-9~＞>≥\-—－~•·.]+$")
CLUB_OCR = re.compile(r"(?<=[1-7l])[·\.\-!:]*(?:ft|lt|t|1t|tt)(?=$|[^A-Za-z])")
DESC_FIX = [
    ("叫l.,,", "叫1♥"), ("叫l♦", "叫1♠"), ("叫l.", "叫1♥"), ("叫1♦，逼叫", "叫1♠，逼叫"),
    ("1•／♠", "1♥/1♠"), ("lNT", "1NT"), ("l♣", "1♣"), ("l♦", "1♦"), ("l♥", "1♥"), ("l♠", "1♠"),
    ("1♦一1♦", "1♣-1♦"), ("1♠一］♥", "1♣-1♥"), ("1•一1♦", "1♣-1♦"), ("：：一", ""), (";：一", ""),
    ("I保持原商", "顺叫保持原叫"), ("5－5", "5-5"), ("4-4-l-4", "4-4-3-4"), ("表2-10张", "表2-10"),
    ("愿意打43配合", "愿意打4-3配合"), ("加直阻击", "加重阻击"), ("顺叫保持原叫，但不逼叫说明", "顺叫保持原叫，但不逼叫；说明"),
    ("表2习", "表2-7"), ("表2-105张", "表2-10；5张"), ("4张'I", "4张♥"), ("4张＇I", "4张♥"), ("4张＇", "4张♥"),
    ("..4张", "4张"), ("表2-54/55", "（表2-54/55）"), ("4张.,", "4张♥"), ("5张.,", "5张♥"),
    ("6张以上．，", "6张以上♥，"), ("说明6张以上．", "说明6张以上♥"),
    ("以上.,", "以上♥"), ("没有商花", "没有高花"), ("打43配合", "打4-3配合"),
    ("以上0强烈", "以上♠强烈"),
]

DESC_TRIM_RE = [
    (re.compile(r"^1[♣♦♥♠][-－一]1[♣♦♥♠].{0,14}?说明"), ""),
    (re.compile(r"1[♣♦♥♠]开叫后续说明?"), ""),
    (re.compile(r"(?:[-~～－]1[♣♦♥♠]|一1[♣♦♥♠])后续[0-7]?[♣♦♥♠NT]*$"), ""),
    (re.compile(r"[~～－]1?[♣♦♥♠]$"), ""),
    (re.compile(r"第三四家开叫1[♣♦♥♠]，应叫与一二家不同.*$"), ""),
    (re.compile(r"[，,。]?[1lI]$"), ""),
    (re.compile(r"^[说明]*说明$"), ""),
    (re.compile(r"[~～]?[1lI]?[♣♦♥♠•](?:一[1lI•'；;f♣♦♥♠NTnt]{0,8})?后续(?:[0-9lI•'；;f♣♦♥♠NTnt\-－一~～.;。]{0,12}说明?)?"), ""),
    (re.compile(r"[~～]?[1lI]?[♣♦♥♠•](?:一[1lI•'；;f♣♦♥♠NTnt]{0,8})?后续[^，,。；;）)]{0,14}$"), ""),
    (re.compile(r"1[♣♦♥♠]开叫(后续)?说明?"), ""),
    (re.compile(r"止叫[1lI]?[♣♦♥♠•NTnt]{0,3}$"), "止叫"),
    (re.compile(r"[~～:;；\-－.，,]+$"), ""),
    # 无干扰后续表标题合并噪声前缀：<seq>后续/都是进局逼叫/说明（如"1♥一2都是进局逼叫说明垃圾叫"）
    (re.compile(r"^[1-7][♣♦♥♠][\-－一\s]*[1-7][♣♦♥♠NT]*(?:后续|都是进局逼叫|进局逼叫)+[\.\d]*说明?"), ""),
    (re.compile(r"^[1-7][♣♦♥♠][\-－一\s]*[1-7][♣♦♥♠NT]*(?:后续|都是进局逼叫)"), ""),
    # 无干扰后续表标题合并噪声后缀（如"满贯兴趣~:-2都是进局逼叫"）
    (re.compile(r"(?:[~:;\s]、]*[1-7][♣♦♥♠][\-－一][1-7][♣♦♥♠NT]*[\.\d]*(?:后续|都是进局逼叫|进局逼叫))$"), ""),
]


def clean_text(s: str) -> str:
    for k, v in SUIT_FIX.items():
        s = s.replace(k, v)
    s = s.translate(str.maketrans("０１２３４５６７８９", "0123456789"))
    s = re.sub(r"^;[::,，]+", ">", s)
    return s.strip()


def clean_desc(s: str) -> str:
    s = clean_text(s)
    for k, v in DESC_FIX:
        s = s.replace(k, v)
    for pat, rep in DESC_TRIM_RE:
        s = pat.sub(rep, s)
    s = re.sub(r"\s+", "", s)
    s = re.sub(r"^[~～，,。;;::｜|．.\-－]+", "", s)
    s = re.sub(r"[，,]{2,}", "，", s)
    s = re.sub(r"[（(]?(表\d+[-—－一]\d+(?:[／/]\d+)*)[）)]?", r"（\1）", s)
    s = re.sub(r"[，,]{2,}", "，", s)
    return s


SUIT_MAP = {"C": "C", "D": "D", "H": "H", "S": "S", "N": "NT", "M": "NT", "T": "NT",
            "c": "C", "d": "D", "h": "H", "s": "S", "n": "NT", "m": "NT", "t": "NT",
            "♦": "D", "♥": "H", "♠": "S", "♣": "C"}
WRONG_SUIT = {"D": "S", "S": "D", "H": "C", "C": "H"}
PARTNER_SUIT = {"S": "H", "H": "S", "D": "C", "C": "D"}


def parse_bid_token(p: str):
    p = p.strip(".·-—")
    if p.lower() in ("pass", "p", "pss"):
        return "pass"
    if p in ("X", "XX", "x", "xx"):
        return p.upper()
    m = re.match(r"^([1-7])(NT|nt|N|T)$", p)
    if m:
        return f"{m.group(1)}NT"
    m = re.match(r"^([1-7])([CDHScdhs♦♥♠♣])$", p)
    if m:
        return m.group(1) + SUIT_MAP[m.group(2)]
    return None


def expand_bid_group(s: str):
    m = re.match(r"^([1-7])([CDHS♦♥♠♣])[Il'’·]+([CDHS♦♥♠♣])", s)
    if not m:
        return None
    lev, s1, s2 = m.group(1), SUIT_MAP[m.group(2)], SUIT_MAP[m.group(3)]
    chain = ["C", "D", "H", "S"]
    try:
        i1, i2 = chain.index(s1), chain.index(s2)
    except ValueError:
        return None
    if i2 <= i1:
        return None
    return [f"{lev}{chain[k]}" for k in range(i1, i2 + 1)]


def expand_bullet_pair(s: str):
    m = re.match(r"^([1-7])[•·.](?:／|/)([CDHS♦♥♠♣])", s)
    if not m:
        return None
    lev, s2 = m.group(1), SUIT_MAP[m.group(2)]
    return [lev + PARTNER_SUIT[s2], lev + s2]


def parse_bid_cell(cell: str):
    s = clean_text(cell)
    for k, v in LINK_FIX.items():
        s = s.replace(k, v)
    s = CLUB_OCR.sub("♣", s)
    s = re.sub(r"[Il]", "1", s) if re.match(r"^[Il][1-7NTCDHScdhs♦♥♠♣]", s) else s
    grp = expand_bid_group(s)
    if grp:
        return grp
    bp = expand_bullet_pair(s)
    if bp:
        return bp
    s = re.sub(r"[，,。;;::\s／/|｜’']+", "/", s)
    s = s.strip("/")
    bids = []
    level = None
    for part in s.split("/"):
        part = part.strip()
        if not part:
            continue
        b = parse_bid_token(part)
        if b:
            bids.append(b)
            if b[0] in "1234567":
                level = b[0]
            continue
        if len(part) == 1 and part in SUIT_MAP and level:
            bids.append(level + SUIT_MAP[part])
            continue
        return None
    if not bids:
        return None
    fixed = []
    for b in bids:
        while b in fixed:
            if b.endswith("NT"):
                break
            alt = b[0] + WRONG_SUIT.get(b[1], b[1])
            if alt == b:
                break
            b = alt
        fixed.append(b)
    return fixed


def looks_like_bid_cell(raw: str):
    s = clean_text(raw)
    return bool(re.match(r"^[1-7lI][•·.＊]?(?:／|/)?[CDHS♦♥♠♣]?$", s)) and len(s) <= 6


def parse_points_text(s: str):
    s = clean_text(s)
    s = s.replace("≥", "~").replace("＞", ">")
    s = re.sub(r"[•·\s]", "", s)
    if not s or not re.match(r"^[>~]?\d{1,2}([~\-—－]\d{1,2})?$", s):
        return None
    s = s.replace("—", "-").replace("－", "-")
    return s


def cluster(items, tol=40):
    out = []
    for it in sorted(items, key=lambda t: t["y"]):
        if out and it["y"] - out[-1]["_ymax"] < tol:
            out[-1]["items"].append(it)
            out[-1]["_ymax"] = max(out[-1]["_ymax"], it["y"])
        else:
            out.append({"_ymax": it["y"], "items": [it]})
    return out


def find_header(ws):
    pts = [w for w in ws if w["w"] == "牌点"]
    for p in pts:
        row = [w for w in ws if abs(w["y"] - p["y"]) <= 15]
        text = "".join(w["w"] for w in row)
        if "说明" in text or "再叫" in text or "说" in text:
            bid_x = None
            desc_x = None
            for w in row:
                if w["w"] in ("应叫", "再叫") or "再叫" in w["w"] or "应叫" in w["w"]:
                    bid_x = w["x"]
                if w["w"] in ("说", "说明"):
                    desc_x = w["x"]
            return {"y": p["y"], "points_x": p["x"], "bid_x": bid_x or 278, "desc_x": desc_x or (p["x"] + 400)}
    return None


def compute_bounds(ws, header):
    refs = [w for w in ws if re.match(r"^表\d+[-—－一]", w["w"])]
    ref_left = min((w["x"] for w in refs), default=10 ** 9)
    if ref_left < header["desc_x"]:
        ref_left = 10 ** 9
    return {
        "bid_right": header["points_x"] - 90,
        "points_left": header["points_x"] - 90,
        "points_right": header["points_x"] + 140,
        "desc_left": header["points_x"] + 140,
        "desc_right": ref_left - 60,
        "ref_left": ref_left - 60,
    }


def parse_page(ws, bounds, page):
    bid_w, pts_w, desc_w, ref_w = [], [], [], []
    for w in ws:
        x = w["x"]
        if x < bounds["bid_right"]:
            bid_w.append(w)
        elif x < bounds["points_right"]:
            if BID_WORD_RE.match(w["w"]):
                pts_w.append(w)
        elif x < bounds["desc_right"]:
            if not PAGE_NOISE_RE.match(w["w"]):
                desc_w.append(w)
        else:
            ref_w.append(w)

    anchors = []
    for cl in cluster(bid_w, 30):
        text = "".join(w["w"] for w in sorted(cl["items"], key=lambda t: (t["y"], t["x"])))
        bids = parse_bid_cell(text)
        if bids or looks_like_bid_cell(text):
            yc = sum(w["y"] for w in cl["items"]) / len(cl["items"])
            anchors.append({"y": yc, "bids": bids or [], "_raw": text})
    if not anchors:
        return []
    anchors.sort(key=lambda a: a["y"])

    def assign(col_clusters, key):
        for c in col_clusters:
            yc = sum(w["y"] for w in c["items"]) / len(c["items"])
            best, bd = None, 10 ** 9
            for a in anchors:
                d = abs(yc - a["y"])
                if d < bd:
                    best, bd = a, d
            if best is not None:
                best.setdefault(key, []).append((yc, c))
        for a in anchors:
            a[key] = sorted(a.get(key, []), key=lambda t: t[0])

    assign(cluster(pts_w, 25), "pts")
    assign(cluster(desc_w, 45), "desc")
    assign(cluster(ref_w, 45), "ref")

    for i, a in enumerate(anchors):
        if not a.get("pts") and i > 0:
            prev = anchors[i - 1]
            if len(prev.get("pts", [])) > 1:
                a["pts"] = [prev["pts"].pop()]
        elif len(a.get("pts", [])) > 1 and i + 1 < len(anchors) and not anchors[i + 1].get("pts"):
            anchors[i + 1]["pts"] = [a["pts"].pop()]

    entries = []
    for a in anchors:
        points = None
        for _, c in a.get("pts", []):
            t = "".join(w["w"] for w in sorted(c["items"], key=lambda t: (t["y"], t["x"])))
            p = parse_points_text(t)
            if p:
                points = p if points is None else points + "/" + p
        desc = "".join(
            "".join(w["w"] for w in sorted(c["items"], key=lambda t: (t["y"], t["x"])))
            for _, c in a.get("desc", []))
        desc = clean_desc(desc)
        links = []
        for _, c in a.get("ref", []):
            t = "".join(w["w"] for w in sorted(c["items"], key=lambda t: (t["y"], t["x"])))
            for m in re.finditer(r"表\s*(\d+)[-—－一](\d+)", t):
                links.append(f"{m.group(1)}-{m.group(2)}")
        for m in re.finditer(r"表\s*(\d+)[-—－一](\d+)", desc):
            lk = f"{m.group(1)}-{m.group(2)}"
            if lk not in links:
                links.append(lk)
        dedup_links = []
        for lk in links:
            if lk not in dedup_links:
                dedup_links.append(lk)
        entries.append({"bids": a["bids"], "points": points or "", "desc": desc, "links": dedup_links,
                        "raw": a["_raw"], "y": round(a["y"]), "page": page})
    return entries


def parse_table(tb):
    pages = {}
    for w in tb["words"]:
        pages.setdefault(w["page"], []).append(w)
    entries = []
    bounds = None
    for pno in sorted(pages):
        ws = sorted(pages[pno], key=lambda w: (w["y"], w["x"]))
        header = find_header(ws)
        if header:
            bounds = compute_bounds(ws, header)
        if bounds is None:
            continue
        entries.extend(parse_page(ws, bounds, pno))
    return entries


def dedup_ownership(parsed):
    index = {}
    for tid, entries in parsed.items():
        ch = tid.split("-")[0]
        for i, e in enumerate(entries):
            key = (ch, e["page"], e["y"] // 8)
            index.setdefault(key, []).append((tid, i, e))
    dropped = {}
    for key, hits in index.items():
        if len(hits) < 2:
            continue
        # secondary 表（OCR 误标/重复提取项）永不作 owner，避免剥夺真表归属
        candidates = [h for h in hits if h[0] not in SECONDARY_TABLES]
        if not candidates:
            candidates = hits
        owner = max(candidates, key=lambda h: int(h[0].split("-")[1]))[0]
        for tid, i, e in hits:
            if tid != owner:
                dropped.setdefault(tid, set()).add(i)
    out = {}
    for tid, entries in parsed.items():
        out[tid] = [e for i, e in enumerate(entries) if i not in dropped.get(tid, set())]
    return out, dropped


MANUAL_TABLES = {
    "2-2": [
        {"bids": ["1D"], "points": "8~11", "desc": "顺叫保持原叫，但不逼叫；说明4张以上♦，没有4张高花，不逼叫", "links": []},
    ],
}

MANUAL_BID_FIX = {
    ("2-1", "5D", "4~8"): "5S",
    ("2-8", "1D", "12~17"): "1S",
    ("2-8", "3D", "16~18"): "3C",
    ("2-13", "4D", "18~21"): "4S",
    ("2-17", "2D", "10~12/6~9"): "2C",
}

# 无叫品行（raw 为乱码叫品）→ 依据链接表序列人工确定的叫品
MANUAL_NOBID_BID = {
    "3-9": "3C",   # 表3-9(1D-1S) 跳叫新花 18~21逼局 → 表3-55(=1D-1S-3C)
    "6-3": ["3H", "3S"],  # 表6-3(1NT-2♣) 斯莫伦转移叫：5-4高套，所叫高花4张，>10逼局（表6-12/14）
}

MANUAL_SPLIT = {
    ("2-8", ("2D",)): [
        {"bids": ["2C"], "points": "12~15", "desc": "6张以上♣，没有4张高花，不逼叫（表2-10）", "links": ["2-10"]},
        {"bids": ["2D"], "points": "16~21", "desc": "5张以上♣，4张♦，逆叫，逼叫（表2-45）", "links": ["2-45"]},
        {"bids": ["2H"], "points": "12~14", "desc": "4张♥，或3张♥有单缺，不逼叫（表2-11）", "links": ["2-11"]},
    ],
    ("2-13", ("2C",)): [
        {"bids": ["2C"], "points": "12~15", "desc": "6张以上♣，不逼叫（表2-14）", "links": ["2-14"]},
        {"bids": ["2D"], "points": "16~21", "desc": "5张以上♣，4张♦，逆叫，逼叫（表2-47）", "links": ["2-47"]},
    ],
    ("2-4", ("3NT",)): [
        {"bids": ["3D", "4C"], "points": "12~15", "desc": "4张以上♥，5张以上♦，所叫花色单缺，逼局", "links": []},
        {"bids": ["3NT"], "points": "13~15", "desc": "止叫", "links": []},
    ],
    ("2-19", ("2D",)): [
        {"bids": ["2H"], "points": "12~14", "desc": "有♥止张，没有♠止张", "links": []},
        {"bids": ["2S"], "points": "12~14", "desc": "有♠止张，没有♥止张", "links": []},
    ],
    ("2-11", ("3D", "4C", "4D")): [
        {"bids": ["3S", "4C", "4D"], "points": "13", "desc": "5张以上♥，斯普林特，所叫花色单缺，逼局", "links": []},
        {"bids": ["4H"], "points": "12~15", "desc": "5张以上♥，止叫", "links": []},
    ],
    ("2-20", ("3C", "3D")): [
        {"bids": ["3C"], "points": "6~9", "desc": "5张以上♠，要求开叫人无条件叫3♣，之后Pass，不逼叫", "links": []},
        {"bids": ["3D"], "points": "10~12", "desc": "5-5以上♠♥，要求开叫人无条件叫3♦，之后叫3♦，所叫花色5张以上，5张以上♣，逼局", "links": []},
    ],
    ("3-41", ("3NT",)): [
        {"bids": ["3H", "3S"], "points": "15", "desc": "所叫花色单缺，逼局", "links": []},
        {"bids": ["3NT"], "points": "14~19", "desc": "止叫", "links": []},
    ],
    ("5-33", ("4C", "4D")): [
        {"bids": ["4C", "4D", "4H"], "points": "17~21", "desc": "所叫花色单缺，逼局", "links": []},
        {"bids": ["4S"], "points": "15~19", "desc": "止叫", "links": []},
    ],
    ("7-6", ()): [
        {"bids": ["3D"], "points": "0~3", "desc": "二次示弱，和♦无关", "links": []},
        {"bids": ["3D"], "points": "4~7", "desc": "5张以上♦，逼局", "links": []},
    ],
    # E类：5-35(1S-3S) 的 4C/4D/4H 扣叫行粘合，拆开并把 4D 行挂到 5-39(1S-3S-4D)
    ("5-35", ("4C", "4D", "4H")): [
        {"bids": ["4C"], "points": "18~21", "desc": "扣叫所叫花色，满贯兴趣", "links": []},
        {"bids": ["4D"], "points": "18~21", "desc": "扣叫所叫花色，逼局止叫（表5-39）", "links": ["5-39"]},
        {"bids": ["4H"], "points": "18~21", "desc": "扣叫所叫花色，满贯兴趣", "links": []},
    ],
}

MANUAL_BID_SET = {
    ("2-3", ("1C", "1D")): ["1H", "1S"],
    ("2-6", ("3H", "3D")): ["3H", "3D"],
}

TABLE_SUIT_FIX = {
    "2-5": [("4张以上♦", "4张以上♠")],
}

MANUAL_LINKS = {
    ("2-3", ("1H", "1S")): ["2-4", "2-5"],
    ("2-3", ("2H", "2S")): ["2-54", "2-55"],
    ("2-3", ("1NT",)): ["2-17"],
    ("2-3", ("2NT",)): ["2-57"],
    ("2-3", ("3C",)): ["2-62"],
    ("2-3", ("3D",)): ["2-66"],
    ("2-17", ("2C",)): ["2-18"],
    ("2-17", ("2D",)): ["2-19"],
    ("2-8", ("1S",)): ["2-9"],
    ("2-8", ("1NT",)): ["2-20"],
    ("2-8", ("2S",)): ["2-56"],
    ("2-8", ("3H",)): ["2-67"],
    ("2-13", ("1NT",)): ["2-23"],
    ("2-13", ("2S",)): ["2-15"],
    ("2-13", ("3S",)): ["2-68"],
    ("2-20", ("2C",)): ["2-21"],
    ("2-20", ("2D",)): ["2-22"],
    ("2-23", ("2C",)): ["2-24"],
    ("2-23", ("2D",)): ["2-25"],
    # E类 seq 重复续写表：显式挂载父子关系
    # 注：6-1/8-1 是应叫表（非树根），挂其下的链接无效；6-2 的 2H/2S 多叫品行
    # 走多叫品→多子表分叉时会被 _bid_above_all 整行丢弃，故不用 MANUAL_LINKS 挂 6-6/6-9。
    ("4-3", ("2H",)): ["4-6"],
    ("6-2", ("2D",)): ["6-3"],
    ("6-20", ("2S",)): ["6-21"],
    ("8-2", ("3H", "3S")): ["8-3"],
    ("5-18", ("2NT",)): ["5-20"],
    # E类续写表挂载：1D-1S 开叫人跳叫分叉
    ("3-9", ("2NT",)): ["3-51"],
    ("3-9", ("3D",)): ["3-59"],
    ("3-51", ("3C",)): ["3-52"],
}

MANUAL_REMOVE = {
    ("2-1", "2C", "8~11"),
}

MANUAL_POINTS_FIX = {
    ("2-3", "3D"): "16~18",
    ("2-13", "3C"): "16~18",
}

# C 类点力缺失补全：仅对当前 points 为空的条目生效（避免覆盖 MANUAL_SPLIT 等已有点力）。
# 键 = (table_id, tuple(bids))，支持多叫品行；值 = 点力区间。
MANUAL_POINTS_ADD = {
    # ===== 第2章 1C =====
    ("2-6", ("2H", "2S")): "10~11",
    ("2-6", ("3H", "3D")): "13~15",
    ("2-6", ("4C",)): "13~15",
    ("2-7", ("3H", "3D")): "13~15",
    ("2-9", ("2D",)): "10~12",
    ("2-10", ("2NT",)): "11~12",
    ("2-11", ("2S",)): "10~12",
    ("2-14", ("2D",)): "10~12",
    ("2-14", ("4C",)): "15~17",
    ("2-14", ("4D",)): "15~17",
    ("2-15", ("3C", "3D", "3H")): "10~11",
    ("2-15", ("4C", "4D")): "13~15",
    ("2-17", ("3H", "3D")): "13~15",
    ("2-20", ("2D",)): "13~15",
    ("2-20", ("2S",)): "13~15",
    ("2-20", ("3C",)): "13~15",
    ("2-22", ("2S",)): "12~14",
    ("2-23", ("2D",)): "13~15",
    ("2-23", ("3H",)): "13~15",
    ("2-23", ("3D",)): "13~15",
    ("2-25", ("2D",)): "12~14",
    ("2-34", ("pass",)): "12~15",
    ("2-36", ("pass",)): "12~15",
    ("2-40", ("3C", "3D")): "14~21",
    ("2-42", ("4C",)): "15~17",
    ("2-42", ("4D", "4H", "4S")): "15~17",
    ("2-43", ("4C",)): "15~17",
    ("2-44", ("4C",)): "15~17",
    ("2-56", ("4C",)): "10~12",
    ("2-56", ("4D",)): "10~12",
    ("2-57", ("3C",)): "15~17",
    ("2-57", ("3D",)): "15~17",
    ("2-57", ("3H", "3S")): "16~18",
    ("2-58", ("3D",)): "15~17",
    ("2-58", ("4C",)): "15~17",
    ("2-60", ("3D",)): "15~17",
    ("2-60", ("4C",)): "15~17",
    ("2-62", ("4C",)): "15~17",
    ("2-64", ("4C",)): "15~17",
    ("2-64", ("4D", "4H")): "15~17",
    ("2-67", ("3S",)): "15~17",
    ("2-67", ("4C", "4D")): "15~17",
    ("2-68", ("4C", "4D", "4H")): "15~17",
    # ===== 第3章 1D =====
    ("3-6", ("2S",)): "10~12",
    ("3-6", ("3S",)): "13~15",
    ("3-6", ("4D",)): "13~15",
    ("3-26", ("2S",)): "12~14",
    ("3-26", ("2NT",)): "12~14",
    ("3-26", ("3C",)): "12~14",
    ("3-26", ("3D",)): "12~14",
    ("3-26", ("3H",)): "12~14",
    ("3-26", ("4C",)): "12~14",
    ("3-31", ("3H", "3D")): "13~15",
    ("3-31", ("4C",)): "13~15",
    ("3-36", ("pass",)): "12~15",
    ("3-40", ("4H", "4D")): "14~16",
    ("3-41", ("5D",)): "14~16",
    ("3-43", ("4D",)): "15~17",
    ("3-43", ("4C", "4H", "4D")): "15~17",
    ("3-44", ("4D",)): "15~17",
    ("3-44", ("4C", "4H", "4S")): "15~17",
    ("3-44", ("5D",)): "12~15",
    ("3-45", ("3H",)): "10~12",
    ("3-45", ("4H",)): "13~15",
    ("3-45", ("4D",)): "13~15",
    ("3-49", ("3D",)): "15~17",
    ("3-49", ("4D",)): "15~17",
    ("3-51", ("3D",)): "15~17",
    ("3-51", ("4D",)): "15~17",
    ("3-59", ("4C",)): "15~17",
    # ===== 第4章 1H =====
    ("4-6", ("3C", "3D")): "10~12",
    ("4-6", ("4C", "4D")): "13~15",
    ("4-28", ("3D",)): "12~14",
    ("4-28", ("3C",)): "14~15",
    ("4-28", ("3S",)): "14~15",
    ("4-28", ("4D",)): "12~14",
    ("4-34", ("pass",)): "12~15",
    ("4-43", ("4D",)): "15~17",
    ("4-44", ("4D",)): "15~17",
    ("4-44", ("5D",)): "15~17",
    ("4-49", ("3D",)): "10~12",
    # ===== 第5章 1S =====
    ("5-12", ("2NT",)): "12~14",
    ("5-12", ("3C",)): "12~14",
    ("5-12", ("3D",)): "14~15",
    ("5-20", ("2NT",)): "12~14",
    ("5-20", ("3C",)): "12~14",
    ("5-20", ("3D",)): "12~14",
    ("5-20", ("3S",)): "14~15",
    ("5-20", ("4D",)): "12~14",
    ("5-42", ("4C",)): "15~17",
    ("5-42", ("4D",)): "15~17",
    ("5-43", ("4H",)): "15~17",
    ("5-44", ("4H",)): "15~17",
    ("5-44", ("5S",)): "15~17",
    # ===== 第6章 1NT =====
    ("6-3", ("3C", "3D")): "10~12",
    ("6-3", ("5S", "5D")): "10~14",
    ("6-21", ("3C", "3D")): "10~12",
    ("6-21", ("3H",)): "10~12",
    # ===== 第7章 2C =====
    ("7-2", ("3C", "3D")): "22~24",
    # ===== 第8章 2NT =====
    ("8-3", ("4D",)): "11~12",
    ("8-21", ("3NT",)): "10~12",
    ("8-21", ("4C", "4D")): "10~12",
}

MANUAL_DESC = {
    ("2-1", ("1S",)): "4张以上♠，4-4高花叫1♥，5-5高花叫1♠，可能有更长的低花，逼叫；♠为最长花色，5-5高花叫1♠，逼叫",
    ("2-3", ("1H", "1S")): "1H：4张♥；1S：5张♠或4-4-3-4牌型（表2-4/5），不逼叫",
    ("2-3", ("2D",)): "5张以上♣，4张♦，不逼叫（表2-7）",
    ("2-3", ("2H", "2S")): "5张以上♣，4张所叫花色，跳叫新花逼局（表2-54/55）",
    ("2-3", ("3NT",)): "6张以上坚固♣，高花有止张",
    ("2-4", ("pass",)): "3张♥，愿意打4-3配合",
    ("2-5", ("pass",)): "3张♠，愿意打4-3配合",
    ("2-5", ("3H", "4C")): "4张以上♠，5张以上♦，所叫花色单缺，逼局",
    ("2-5", ("3S",)): "4张以上♠，5张以上♦，逼局",
    ("2-5", ("4S",)): "4张以上♠，5张以上♦，止叫",
    ("2-6", ("2D",)): "6张以上♦，2张以下♣，不逼叫",
    ("2-6", ("3H", "3D")): "4张以上♣，所叫花色单缺，逼局",
    ("2-8", ("1S",)): "4张♠，不逼叫（表2-9）",
    ("2-8", ("2NT",)): "跳叫2NT，可能有4张♠，不逼叫（表2-58）",
    ("2-8", ("3NT",)): "6张以上坚固♣，未叫花色有止张",
    ("2-8", ("4C",)): "6张以上♣，4张♥，逼局",
    ("2-13", ("2NT",)): "跳叫2NT，可能有4张♥，不逼叫（表2-60）",
    ("2-13", ("3S",)): "4张♠，邀请（表2-68）",
    ("2-13", ("3NT",)): "6张以上坚固♣，未叫花色有止张",
    ("2-13", ("4C",)): "6张以上♣，4张♠，逼局",
    ("2-17", ("2C",)): "双路斯泰曼，要求开叫人无条件叫2D，之后弱牌Pass或继续描述",
    ("2-17", ("2D",)): "不符合其他叫品，逼局",
    ("2-18", ("pass",)): "5张以上♦",
    ("2-18", ("3C",)): "5张♣, 5张以上♦，不逼叫",
    ("2-18", ("3D",)): "6张以上好♦套，不逼叫",
    ("2-19", ("3C",)): "5张以上♦",
    ("2-19", ("3D",)): "3张♦带两大牌",
    ("2-21", ("pass",)): "5张以上♦",
    ("2-21", ("2H",)): "5张以上好♥套，不逼叫",
    ("2-21", ("3H",)): "6张以上♥好套，不逼叫",
    ("2-22", ("2H",)): "3张♥",
    ("2-22", ("2S",)): "3张♦，3-1-4-5牌型",
    ("2-22", ("2NT",)): "没有3张♥，均型",
    ("2-24", ("pass",)): "5张以上♦",
    ("2-24", ("2H",)): "5张以上♦，4张♥，不逼叫",
    ("2-24", ("3H",)): "5张以上♦，5张以上♣，不逼叫",
    ("2-24", ("3S",)): "6张以上好♠套，不逼叫",
    ("2-25", ("2H",)): "4张♥",
    ("2-25", ("2S",)): "3张♠",
    ("2-25", ("2NT",)): "没有4张♣，没有3张♠，均型，逼局",
    ("2-25", ("3C",)): "5张以上♠，逼局",
    ("2-25", ("3D",)): "2-2-4-5牌型，逼局",
    ("2-17", ("2C",)): "双路斯泰曼，要求开叫人无条件叫2D，之后弱牌Pass或继续描述",
    ("2-17", ("2D",)): "不符合其他叫品，逼局",
    ("2-20", ("2C",)): "双路斯泰曼，要求开叫人无条件叫2D，之后弱牌Pass或继续描述",
    ("2-20", ("2D",)): "与♦无关，多数进局牌的起步叫品，逼局",
    ("2-23", ("2C",)): "双路斯泰曼，要求开叫人无条件叫2D，之后弱牌Pass或继续描述",
    ("2-23", ("2D",)): "与♦无关，多数进局牌的起步叫品，逼局",
    ("3-14", ("2S",)): "6张以上♠，不逼叫",
    ("3-22", ("pass",)): "不符合其他叫品",
    # E类续写表挂载后，修正被覆盖行残留的 OCR 乱码描述
    ("3-9", ("2NT",)): "跳叫2NT，可能有4张♥，不逼叫（表3-51）",
    ("3-9", ("3D",)): "6张以上♦，没有4张高花，不逼叫（表3-59）",
    ("6-15", ("4NT",)): "小满贯邀请",
    ("8-16", ("5D",)): "止叫",
}

MANUAL_ENTRY_APPEND = {
    "2-3": [
        {"bids": ["3H", "3S"], "points": "18~21", "desc": "斯普林特，所叫花色为单缺，4张♦，逼局", "links": []},
    ],
    "2-13": [
        {"bids": ["3D", "3H"], "points": "18~21", "desc": "4张♠，所叫花色单缺，逼局", "links": []},
    ],
}

SUIT_CHAR = {"C": "♣", "D": "♦", "H": "♥", "S": "♠"}


TABLE_SEQ = {
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

ORDER = {"C": 0, "D": 1, "H": 2, "S": 3, "NT": 4}


def bid_sort_key(bid):
    if bid == "pass":
        return (0, 0, 0)
    if bid in ("X", "XX"):
        return (0, 0, 1)
    m = re.match(r"^([1-7])(C|D|H|S|NT)$", bid)
    return (1, int(m.group(1)), ORDER[m.group(2)]) if m else (2, 0, 0)


def bid_rank(bid):
    m = re.match(r"^([1-7])(C|D|H|S|NT)$", bid)
    if not m:
        return -1
    return (int(m.group(1)) - 1) * 5 + ORDER[m.group(2)]


def next_cheapest_bid(suit, last_bid):
    last_rank = bid_rank(last_bid)
    for lev in range(1, 8):
        b = f"{lev}{suit}"
        if bid_rank(b) > last_rank:
            return b
    return None


def fourth_suit_bid(seq):
    parts = [p for p in seq.split("-") if p not in ("pass", "3rd")]
    if len(parts) < 3:
        return None
    suits = [p[1:] for p in parts[-3:] if re.match(r"^[1-7](C|D|H|S)$", p)]
    if len(suits) < 3 or len(set(suits)) != 3:
        return None
    rest = [s for s in ("C", "D", "H", "S") if s not in suits]
    if not rest:
        return None
    return next_cheapest_bid(rest[0], parts[-1])


def fix_entry_bids(tid, entries):
    seq = TABLE_SEQ.get(tid, "")
    parts = [p for p in seq.split("-") if p not in ("pass", "3rd")]
    last = parts[-1] if parts else ""
    root = parts[0] if parts else ""
    root_suit = root[1:] if re.match(r"^[1-7](C|D|H|S)$", root) else None

    for e in entries:
        if not e["bids"] and e.get("raw"):
            if tid in MANUAL_NOBID_BID and e["raw"].strip(" '") in (".", "3.", "3", "2", "2."):
                v = MANUAL_NOBID_BID[tid]
                e["bids"] = list(v) if isinstance(v, (list, tuple)) else [v]
                e["fixed_bid"] = True
                continue
            m = re.match(r"^([1-7])[•·.]$", e["raw"].strip(" '"))
            if m:
                for suit, ch in SUIT_CHAR.items():
                    if ch in e["desc"]:
                        realiz = f"{m.group(1)}{suit}"
                        if bid_sort_key(realiz) > bid_sort_key(last) or last == "":
                            e["bids"] = [realiz]
                            e["fixed_bid"] = True
                            break

    entries[:] = [e for e in entries
                  if (tid, e["bids"][0] if len(e["bids"]) == 1 else "", e["points"]) not in MANUAL_REMOVE]

    out = []
    seen = set()
    for e in entries:
        if len(e["bids"]) == 1 and (tid, e["bids"][0], e["points"]) in MANUAL_BID_FIX:
            e["bids"] = [MANUAL_BID_FIX[(tid, e["bids"][0], e["points"])]]
            e["fixed_bid"] = True
        set_key = (tid, tuple(e["bids"]))
        manual_set = set_key in MANUAL_BID_SET
        if manual_set:
            e["bids"] = list(MANUAL_BID_SET[set_key])
            e["fixed_bid"] = True
        if "第四花色" in e["desc"] and seq:
            fb = fourth_suit_bid(seq)
            if fb and len(e["bids"]) == 1 and e["bids"][0] not in ("pass", "X", "XX"):
                if bid_rank(e["bids"][0]) <= bid_rank(last) or e["bids"][0] == fb:
                    if e["bids"][0] != fb:
                        e["bids"] = [fb]
                        e["fixed_bid"] = True
        nb = []
        for b in e["bids"]:
            if b in seen and re.match(r"^[1-7](C|D|H|S)$", b) and not manual_set:
                alt = b[0] + WRONG_SUIT.get(b[1], b[1])
                if alt not in seen and SUIT_CHAR.get(alt[1:], "") in e["desc"]:
                    b = alt
                    e["fixed_bid"] = True
            if b not in nb:
                nb.append(b)
        e["bids"] = nb
        seen.update(nb)

        key = (tid, tuple(e["bids"]))
        if key in MANUAL_LINKS:
            e["links"] = list(MANUAL_LINKS[key])
        if key in MANUAL_SPLIT:
            for row in MANUAL_SPLIT[key]:
                row = {**row, "raw": "", "y": e.get("y", 0), "page": e.get("page", 0), "fixed_bid": True}
                out.append(row)
                seen.update(row["bids"])
            continue
        if len(e["bids"]) == 1 and (tid, e["bids"][0]) in MANUAL_POINTS_FIX:
            e["points"] = MANUAL_POINTS_FIX[(tid, e["bids"][0])]
        if not e["points"] and key in MANUAL_POINTS_ADD:
            e["points"] = MANUAL_POINTS_ADD[key]
        if key in MANUAL_DESC:
            e["desc"] = MANUAL_DESC[key]
            e["fixed_bid"] = True
        manual_desc_applied = key in MANUAL_DESC
        if (not manual_desc_applied and root_suit and len(e["bids"]) == 1 and e["bids"][0][1:] == root_suit
                and re.match(r"^[1-7](C|D|H|S)$", e["bids"][0]) and "张以上" in e["desc"]):
            e["desc"] = re.sub(r"(\d+)张以上[♦♥♠♣]", rf"\1张以上{SUIT_CHAR[root_suit]}", e["desc"], count=1)
        for old, new in TABLE_SUIT_FIX.get(tid, []):
            e["desc"] = e["desc"].replace(old, new)
        out.append(e)
    entries[:] = out

    for extra in MANUAL_ENTRY_APPEND.get(tid, []):
        if not any(e["bids"] == extra["bids"] for e in entries):
            entries.append({**extra, "raw": "", "y": 10 ** 6, "page": 0, "fixed_bid": False})


def derive_bids_from_links(e, tid):
    if e["bids"] or not e["links"]:
        return
    cur = TABLE_SEQ.get(tid, "")
    cur_parts = [p for p in cur.split("-") if p not in ("pass", "3rd")]
    derived = []
    for lk in e["links"]:
        seq = TABLE_SEQ.get(lk, "")
        parts = [p for p in seq.split("-") if p not in ("pass", "3rd")]
        if len(parts) == len(cur_parts) + 1:
            b = parts[-1]
            if b not in derived:
                derived.append(b)
    if derived:
        e["bids"] = sorted(set(derived), key=bid_sort_key)
        e["fixed_bid"] = True


def last_bid_of_seq(seq):
    bids = [b for b in seq.split("-") if b not in ("pass", "3rd")]
    return bids[-1] if bids else ""


def filter_links(links, bids):
    if not links or not bids:
        return links
    out = []
    for lk in links:
        seq = TABLE_SEQ.get(lk, "")
        if not seq:
            out.append(lk)
            continue
        tail = seq.split("-")[-1]
        if tail in bids:
            out.append(lk)
    if not out and links:
        return links
    return out


def fix_bid_vs_seq(bid, last):
    if not last or bid in ("pass", "X", "XX"):
        return bid, False
    if bid_sort_key(bid) > bid_sort_key(last):
        return bid, False
    m = re.match(r"^([1-7])(C|D|H|S|NT)$", bid)
    if not m:
        return bid, False
    alt = m.group(1) + WRONG_SUIT.get(m.group(2), m.group(2))
    if bid_sort_key(alt) > bid_sort_key(last):
        return alt, True
    return bid, False


PER_BID_DESC = {
    ("2-3", "1H"): "4张♥，不逼叫",
    ("2-3", "1S"): "5张♠或4-4-3-4牌型，不逼叫",
    ("2-3", "2H"): "5张以上♣，4张♥，跳叫新花逼局",
    ("2-3", "2S"): "5张以上♣，4张♠，跳叫新花逼局",
}


def _bid_above_all(candidate, anchors):
    """候选叫品必须严格高于所有锚叫品（父叫品），否则丢弃。"""
    anchors = [a for a in anchors if bid_rank(a) >= 0 and a not in ("pass", "X", "XX")]
    if not anchors:
        return True
    cr = bid_rank(candidate)
    return cr > max(bid_rank(a) for a in anchors)


def insert_mid_layers(child_nodes, table_id, seq, bids, tables, visited, parsed_cache):
    """若子表 seq 比当前行 seq 多出多余叫品，则插入对应中间层节点包裹 child_nodes。"""
    child_seq = TABLE_SEQ.get(table_id, "")
    if not seq or not child_seq:
        return child_nodes
    cur = [b for b in seq.split("-") if b not in ("pass", "3rd")]
    child = [b for b in child_seq.split("-") if b not in ("pass", "3rd")]
    if len(child) <= len(cur):
        return child_nodes
    extra = child[len(cur):]
    covered = set(bids)
    mid = [b for b in extra if b not in covered and _bid_above_all(b, bids)]
    if not mid:
        return child_nodes
    node = {"bids": mid, "points": "", "desc": "开叫人答叫", "table": table_id,
            "fixed_bid": False, "children": child_nodes}
    return [node]


def _filter_above_anchors(nodes, anchors):
    """递归过滤：仅保留根层叫品严格高于锚叫品的子树，被丢弃的叫品记录到全局 review 列表。"""
    out = []
    for n in nodes:
        if n["bids"] and _bid_above_all(n["bids"][0], anchors):
            out.append(n)
        else:
            BAD_BID_ORDER.append({**n, "_parent": anchors})
    return out


def build_tree_node(table_id, tables, visited, parsed_cache):
    entries = parsed_cache.get(table_id, [])
    seq = TABLE_SEQ.get(table_id, "")
    last = last_bid_of_seq(seq)
    nodes = []
    for e in entries:
        bids, fixed = [], e.get("fixed_bid", False)
        for b in e["bids"]:
            fb, did = fix_bid_vs_seq(b, last)
            fixed = fixed or did
            bids.append(fb)
        bids = sorted(set(bids), key=bid_sort_key)
        links = filter_links(e["links"], bids)
        child_visited = visited | {table_id}
        if len(links) > 1 and len(bids) == len(links):
            for b, lk in zip(bids, links):
                if not _bid_above_all(b, e["bids"]):
                    BAD_BID_ORDER.append({**e, "_parent": e["bids"]})
                    continue
                node = {"bids": [b], "points": e["points"],
                        "desc": PER_BID_DESC.get((table_id, b), e["desc"]),
                        "table": table_id, "fixed_bid": fixed, "children": []}
                if lk in tables and lk not in visited:
                    sub = build_tree_node(lk, tables, child_visited, parsed_cache)
                    node["children"] = insert_mid_layers(sub, lk, seq, [b], tables, visited, parsed_cache)
                nodes.append(node)
            continue
        node = {"bids": bids, "points": e["points"], "desc": e["desc"],
                "table": table_id, "fixed_bid": fixed, "children": []}
        if len(links) == 1:
            lk = links[0]
            if lk in tables and lk not in visited:
                sub = build_tree_node(lk, tables, child_visited, parsed_cache)
                sub = _filter_above_anchors(sub, bids)
                node["children"] = insert_mid_layers(sub, lk, seq, bids, tables, visited, parsed_cache)
        nodes.append(node)
    return nodes


def render_tree_nodes(nodes, depth, lines):
    prefix = "│-----" * depth
    for n in nodes:
        if not n["bids"]:
            continue
        bid_str = "/".join(n["bids"])
        meta = []
        if n["points"]:
            meta.append(n["points"] + "点")
        if n["desc"]:
            meta.append(n["desc"])
        text = bid_str + "：" + ("，".join(meta) if meta else "")
        if n.get("fixed_bid"):
            text += "〔OCR校正〕"
        lines.append(f"{prefix}├{text}")
        render_tree_nodes(n["children"], depth + 1, lines)


def render_response_table(tid, entries):
    lines = [TABLE_SEQ[tid].split("-")[0] + "开叫", f"新睿二盖一体系：1♣开叫后的应叫（表{tid}）"]
    for e in entries:
        if not e["bids"]:
            continue
        bid = e["bids"][0]
        bid_str = f"1C-{bid}"
        meta = []
        if e["points"]:
            meta.append(e["points"] + "点")
        if e["desc"]:
            meta.append(e["desc"])
        mark = "〔OCR校正〕" if e.get("fixed_bid") else ""
        lines.append(f"{bid_str}：{'，'.join(meta)}{mark}")
    for tid2, rows in MANUAL_TABLES.items():
        if TABLE_SEQ.get(tid2, "").startswith("1C-3rd"):
            for e in rows:
                lines.append(f"第三四家开叫1C时：应叫{e['bids'][0]}，{e['points']}点，{e['desc']}（表{tid2}）")
    return lines


def main():
    data = json.loads(TABLES_JSON.read_text(encoding="utf-8"))
    tables = {t["table_id"]: t for t in data}
    parsed = {tid: parse_table(tb) for tid, tb in tables.items()}
    total_before = sum(len(v) for v in parsed.values())

    parsed, dropped = dedup_ownership(parsed)
    total_after = sum(len(v) for v in parsed.values())
    print(f"dedup: entries {total_before} -> {total_after} (dropped {total_before - total_after})")

    for tid in MANUAL_TABLES:
        parsed[tid] = list(MANUAL_TABLES[tid])
    for tid in sorted(tables, key=lambda t: int(t.split("-")[1])):
        for e in parsed.get(tid, []):
            derive_bids_from_links(e, tid)
        fix_entry_bids(tid, parsed.get(tid, []))

    no_bid = [(tid, e) for tid in sorted(parsed) for e in parsed[tid] if not e["bids"]]
    print(f"tables={len(tables)} entries={sum(len(v) for v in parsed.values())} no-bid={len(no_bid)}")
    for tid, e in no_bid[:10]:
        print(f"  no-bid {tid}: raw={e['raw']!r} desc={e['desc'][:30]!r}")

    segs = [ "\n".join(render_response_table("2-1", parsed["2-1"])) ]

    for root_tid, kw in [("2-3", "1C-1D"), ("2-8", "1C-1H"), ("2-13", "1C-1S")]:
        nodes = build_tree_node(root_tid, tables, set(), parsed)
        lines = [kw, f"新睿二盖一体系：{kw} 开叫人再叫及后续（表{root_tid}）"]
        render_tree_nodes(nodes, 0, lines)
        segs.append("\n".join(lines))

    OUT_MD.write_text("\n\n\n".join(segs) + "\n", encoding="utf-8")
    built = {"tables": parsed,
             "trees": {kw: build_tree_node(rt, tables, set(), parsed) for rt, kw in
                       [("2-3", "1C-1D"), ("2-8", "1C-1H"), ("2-13", "1C-1S")]}}
    OUT_JSON.write_text(json.dumps(built, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"saved -> {OUT_MD}")
    print(f"saved -> {OUT_JSON}")


if __name__ == "__main__":
    main()
