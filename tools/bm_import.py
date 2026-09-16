import os, re, json

DESKTOP = os.path.join(os.path.expanduser("~"), "Desktop")
BASE = os.path.join(DESKTOP, "bm2000", "hands")
HCPMAP = {"A": 4, "K": 3, "Q": 2, "J": 1}
MARK = b"st||nt||sk||md|"
NEXT = {"N": "E", "E": "S", "S": "W", "W": "N"}
PURE = re.compile(r"^[A-Z]\d+$")
RK = "AKQJT98765432"
SUIT_CN = {"S": "♠", "H": "♥", "D": "♦", "C": "♣"}
POS_CN = {"S": "南", "W": "西", "N": "北", "E": "东"}

def normalize_bid(b):
    if b in ("p", "P", "pass", "pass "):
        return "pass"
    b = b.strip()
    m = re.match(r"^(\d)([A-Za-z]+)$", b)
    if m:
        level = m.group(1)
        s = m.group(2).upper()
        if s == "NT" or s.startswith("N"):
            strain = "NT"
        elif s == "S":
            strain = "♠"
        elif s == "H":
            strain = "♥"
        elif s == "D":
            strain = "♦"
        elif s == "C":
            strain = "♣"
        else:
            return b
        return f"{level}{strain}"
    bb = b.lower()
    if "double" in bb:
        return "加倍"
    if bb.startswith("d"):
        return "加倍"
    if "redouble" in bb or "redouble".startswith(bb):
        return "再加倍"
    if bb.startswith("r"):
        return "再加倍"
    return b

def contract_and_declarer(mbs):
    final = None
    for k in range(len(mbs) - 1, -1, -1):
        b = mbs[k]
        if b.strip().lower() not in ("p", "pass"):
            mmm = re.match(r"^(\d)([A-Za-z]+)$", b.strip())
            if mmm:
                final = (k, mmm)
                break
    return final

DATS = {lvl: open(os.path.join(BASE, str(lvl), "Data"), "rb").read() for lvl in range(1, 6)}

def all_markers(lvl):
    d = DATS[lvl]
    out = []
    i = 0
    while True:
        j = d.find(MARK, i)
        if j < 0:
            break
        out.append(j)
        i = j + 1
    return out

MARKERS = {lvl: all_markers(lvl) for lvl in range(1, 6)}

def valid_marker(lvl, mpos):
    d = DATS[lvl]
    spos = mpos + len(MARK)
    hpart, _, after = d[spos:spos + 2500].partition(b"|")
    h = hpart.decode("latin1", "replace")
    if len(h) < 1 or h[0] not in "1234w":
        return False
    mbs = re.findall(rb"mb\|([^|]+)\|", after[:2000])
    return len(mbs) >= 3

def valid_markers(lvl):
    return [m for m in MARKERS[lvl] if valid_marker(lvl, m)]

def parse_index(lvl):
    d = open(os.path.join(BASE, str(lvl), "Index"), "rb").read()
    recs = []
    i = 0
    while i < len(d):
        j = d.find(b"\x00", i)
        if j < 0:
            break
        name = d[i:j].decode("latin1")
        o = j + 1
        if o + 3 > len(d):
            break
        off = int.from_bytes(d[o:o + 3], "big")
        nm = name[:-4] if name.endswith(".LIN") else name
        recs.append((nm, off))
        i = o + 3
    return recs

def level_names(lvl):
    recs = parse_index(lvl)
    vm = valid_markers(lvl)
    pure = sorted({nm for nm, off in recs if PURE.match(nm)})
    assign = pure[:len(vm)]
    dead = pure[len(vm):]
    return assign, dead

D2DEALER = {"1": "S", "2": "W", "3": "N", "4": "E", "w": "S"}
ORDER = ["S", "W", "N", "E"]

def decode_hands_full(md_part):
    if md_part[0] not in D2DEALER:
        return None
    parts = md_part[1:].split(",")
    hands = {}
    for i, p in enumerate(parts[:4]):
        cur = None
        hh = {}
        for ch in p:
            if ch.upper() in "SHDC":
                cur = ch.upper()
                hh.setdefault(cur, set())
            elif cur is not None:
                hh[cur].add(ch.upper())
        hands[ORDER[i]] = hh
    given = set()
    for h in hands.values():
        for s, rks in h.items():
            for r in rks:
                given.add((s, r))
    if len(parts) < 4:
        mh = {}
        for s in "SHDC":
            for r in "AKQJT98765432":
                if (s, r) not in given:
                    mh.setdefault(s, set()).add(r)
        hands[ORDER[len(parts)]] = mh
        return hands
    short = [p for p in ORDER if p in hands and sum(len(v) for v in hands[p].values()) < 13]
    if len(short) == 1:
        p = short[0]
        for s in "SHDC":
            for r in "AKQJT98765432":
                if (s, r) not in given:
                    hands[p].setdefault(s, set()).add(r)
    return hands

def extract_lead(hands, leader, after_md):
    lh = hands.get(leader, {})
    def ok(t):
        if len(t) != 2:
            return None
        su, rk = t[0].upper(), t[1].upper()
        if su in "SHDC" and rk in "AKQJT98765432" and rk in lh.get(su, set()):
            return (su, rk)
        return None
    cr_pos = after_md.rfind(b"cr|")
    head = after_md[cr_pos:] if cr_pos >= 0 else after_md
    at_pos = head.find(b"at|")
    pre_at = head[:at_pos] if at_pos >= 0 else head[:200]
    for tok in re.findall(rb"(?:hc|pc)\|([A-Za-z0-9]{2})\|", pre_at):
        r = ok(tok.decode("latin1"))
        if r:
            return (1, r)
    fp = re.search(rb"pc\|([A-Za-z0-9]{1,2})\|", after_md[:6000])
    if fp:
        t = fp.group(1).decode("latin1")
        if len(t) == 2:
            r = ok(t)
            if r:
                return (2, r)
        else:
            su = t.upper()
            if su in "SHDC":
                rks = lh.get(su, set())
                if len(rks) == 1:
                    return (3, (su, list(rks)[0]))
    return None

def bids_from_after(after_md):
    cut = after_md.find(b"ha|")
    seg = after_md[:cut] if cut >= 0 else after_md
    mbs = [m.decode("latin1") for m in re.findall(rb"mb\|([^|]+)\|", seg)]
    end = len(mbs)
    seen = False
    for j, b in enumerate(mbs):
        if b.strip().lower() not in ("p", "pass"):
            seen = True
        elif seen and j + 2 < len(mbs) and mbs[j + 1].strip().lower() in ("p", "pass") and mbs[j + 2].strip().lower() in ("p", "pass"):
            end = j + 3
            break
    return mbs[:end]

def render_from_marker(level, lvl, mpos):
    d = DATS[lvl]
    spos = mpos + len(MARK)
    end = len(d)
    for m in MARKERS[lvl]:
        if m > mpos:
            end = m
            break
    seg = d[spos:end]
    hpart, _, after_md = seg.partition(b"|")
    md_str = hpart.decode("latin1")
    hands = decode_hands_full(md_str)
    if hands is None:
        return None
    mbs = bids_from_after(after_md)
    return render_deal(level, hands, mbs, after_md, D2DEALER[md_str[0]])

def render_deal(level, hands, mbs, after_md, dealer):
    if not mbs:
        return None
    fb = contract_and_declarer(mbs)
    if fb is None:
        return None
    k, mm = fb
    strain = mm.group(2).upper()
    su = "NT" if strain.startswith("N") else {"S": "♠", "H": "♥", "D": "♦", "C": "♣"}.get(strain)
    if su is None:
        return None
    seq = [dealer]
    s = dealer
    for _ in range(3):
        s = NEXT[s]
        seq.append(s)
    seats = [seq[i % 4] for i in range(len(mbs))]
    cd = seats[k]
    partner = NEXT[NEXT[cd]]
    dec = None
    for bi in range(k + 1):
        bb = mbs[bi].strip()
        mm2 = re.match(r"^(\d)([A-Za-z]+)$", bb)
        if mm2 and mm2.group(2).upper() == strain and seats[bi] in (cd, partner):
            dec = seats[bi]
            break
    if dec is None:
        dec = cd
    nl = extract_lead(hands, NEXT[dec], after_md)
    lead = nl[1] if nl else None
    d = dealer
    r = {"level": level}
    sx = {}
    for p in ["N", "E", "S", "W"]:
        h = hands[p]
        sx[POS_CN[p]] = {"spades": "", "hearts": "", "diamonds": "", "clubs": ""}
        for sname, sletter in [("spades", "S"), ("hearts", "H"), ("diamonds", "D"), ("clubs", "C")]:
            sx[POS_CN[p]][sname] = "".join(sorted(h.get(sletter, set()), key=lambda x: -RK.index(x)))
    r["hands"] = sx
    r["contract_level"] = int(mm.group(1))
    r["contract_suit"] = su
    r["declarer"] = POS_CN[dec]
    r["dealer"] = POS_CN[d]
    tail = mbs[k + 1:]
    r["doubled"] = any(x.strip().lower().startswith("d") and not x.strip().startswith("r") for x in tail)
    r["redoubled"] = any(x.strip().lower().startswith("r") for x in tail)
    parts = []
    for bi, b in enumerate(mbs):
        parts.append(f"({POS_CN[seats[bi]]}){normalize_bid(b)}")
    r["bidding_sequence"] = "-".join(parts) + "-"
    if lead:
        lsu, lrk = lead
        r["opening_lead"] = f"{POS_CN[NEXT[dec]]}:{lrk}{SUIT_CN[lsu]}"
    return r

def build_library():
    lib = {}
    order = []
    skipped = []
    for level in range(1, 6):
        vm = valid_markers(level)
        assign, dead = level_names(level)
        for name in dead:
            skipped.append((f"{level}-{name}", "dead-name"))
        for vi, name in enumerate(assign):
            r = render_from_marker(level, level, vm[vi])
            if not r:
                skipped.append((f"{level}-{name}", "render-fail"))
                continue
            for pos in ["南", "西", "北", "东"]:
                hand = r["hands"][pos]
                total = 0
                for sname in ["spades", "hearts", "diamonds", "clubs"]:
                    total += sum(HCPMAP.get(ch, 0) for ch in hand.get(sname, ""))
                hand["hcp"] = total
            deal_id = f"{level}-{name}"
            r["id"] = deal_id
            lib[deal_id] = r
            order.append(deal_id)
    return {"order": order, "deals": lib, "skipped": skipped}

if __name__ == "__main__":
    lib = build_library()
    out = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "bm_deals.json")
    with open(out, "w", encoding="utf-8") as f:
        json.dump(lib, f, ensure_ascii=False, indent=2)
    print(f"总计 {len(lib['deals'])} 副 -> {out} (跳过 {len(lib['skipped'])})")
    for lv in ["1", "2", "3", "4", "5"]:
        print(f"  Level {lv}: {sum(1 for k in lib['deals'] if k.startswith(lv + '-'))} 副")
    fails = [s for s in lib["skipped"] if s[1] == "render-fail"]
    print(f"渲染失败: {len(fails)} {fails[:8]}")
    no_lead = [k for k, v in lib["deals"].items() if not v.get("opening_lead")]
    print(f"缺首攻: {len(no_lead)} {no_lead[:8]}")
    bad_hcp = [k for k, v in lib["deals"].items() if sum(v["hands"][p]["hcp"] for p in "南西北东") != 40]
    print(f"HCP!=40: {len(bad_hcp)} {bad_hcp[:5]}")
    for key in ["2-B20", "2-B21", "1-A1", "4-A15", "2-B29", "5-A19", "2-C9", "3-C9", "4-C9", "5-B9"]:
        x = lib["deals"].get(key)
        if x:
            print(f"[{key}] 定约 {x['contract_level']}{x['contract_suit']} 庄家{x['declarer']} 首攻{x.get('opening_lead')}")
        else:
            print(f"[{key}] 未找到")
