import argparse
import json
import os
import sys
import time

import requests

BASE = {"url": "http://127.0.0.1:8003"}
POSITIONS = ["南", "西", "北", "东"]
ROLES = {"南": "ai", "西": "ai", "北": "ai", "东": "ai"}
DEFAULT_DEAL_SYSTEM = "2D/2H/2S：自然阻击"

def post(path, payload, timeout=320):
    r = requests.post(BASE["url"] + path, json=payload, timeout=timeout)
    r.raise_for_status()
    return r.json()

def deal(mode):
    data = post("/api/deal", {"mode": mode})
    return data["hands"], data["dealer"]

def next_pos(pos):
    return POSITIONS[(POSITIONS.index(pos) + 1) % 4]

def is_bidding_complete(seq):
    if len(seq) < 4:
        return False
    if not any(b["bid"] != "pass" for b in seq):
        return False
    return all(b["bid"] == "pass" for b in seq[-3:])

def final_contract(seq):
    level = None
    declarer = None
    for b in seq:
        if b["bid"][:1].isdigit():
            level = b["bid"]
            declarer = b["position"]
    return level, declarer

def do_bidding(hands, dealer, deal_system):
    seq = []
    history = ""
    pos = dealer
    for _ in range(60):
        if is_bidding_complete(seq):
            break
        hand = hands[pos]
        payload = {
            "hand": hand,
            "bidding_sequence": seq,
            "position": pos,
            "deal_system": deal_system,
            "bid_history": history,
        }
        try:
            res = post("/api/bid", payload, timeout=180)
        except Exception as e:
            print("  bid error:", pos, e)
            res = {"bid": "pass", "meaning": "ai error"}
        bid = res.get("bid") or "pass"
        meaning = res.get("meaning") or ""
        if res.get("full_output", {}).get("暂停叫牌"):
            bid = "pass"
        seq.append({"position": pos, "bid": bid})
        history += "({}){}：{}\n".format(pos, bid, meaning)
        print("  {} {}  {}".format(pos, bid, meaning[:30]))
        pos = next_pos(pos)
    contract, declarer = final_contract(seq)
    return seq, history, contract, declarer

def do_play(hands, seq, history, contract, declarer, engine, vulnerability, session_id="default"):
    if not contract:
        return None
    payload = {
        "hands": hands,
        "contract": contract,
        "declarer": declarer,
        "player_roles": ROLES,
        "bidding_sequence": "".join("({}){}".format(b["position"], b["bid"]) + "-" for b in seq),
        "bid_history": history,
        "bid_meanings": history,
        "vulnerability": vulnerability,
        "session_id": session_id,
    }
    init = post("/api/play/init", payload, timeout=60)
    if not init["success"]:
        print("  play init error:", init.get("error"))
        return None
    for _ in range(60):
        state = init["state"]
        if state.get("phase") == "complete":
            return state
        res = post("/api/play/ai-play", {
            "play_engine": engine,
            "use_llm_review": False,
            "session_id": session_id,
        })
        if not res.get("success"):
            print("  ai-play error:", res.get("error"))
            return None
        state = res["state"]
        if state.get("phase") == "complete":
            return state
    return state

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--mode", default="free", choices=["free", "game", "slam"])
    ap.add_argument("--num", type=int, default=20)
    ap.add_argument("--engine", default="dd_alphamu_llm")
    ap.add_argument("--deal-system", default=DEFAULT_DEAL_SYSTEM)
    ap.add_argument("--vul", default="NV", choices=["NV", "NS", "EW", "All"])
    ap.add_argument("--url", default="http://127.0.0.1:8003")
    ap.add_argument("--outdir", default="")
    args = ap.parse_args()

    global BASE
    BASE["url"] = args.url
    outdir = args.outdir or os.path.join(os.environ.get("TEMP", "."), "trae", "headless_game")
    os.makedirs(outdir, exist_ok=True)

    results = []
    for board in range(1, args.num + 1):
        print("=== BOARD {} ===".format(board))
        rec = {"board": board, "start": time.strftime("%Y-%m-%d %H:%M:%S")}
        try:
            hands, dealer = deal(args.mode)
            seq, history, contract, declarer = do_bidding(hands, dealer, args.deal_system)
            rec["dealer"] = dealer
            rec["bidding_seq"] = seq
            rec["contract"] = contract
            rec["declarer"] = declarer
            print("  CONTRACT:", contract, "by", declarer)
            state = do_play(hands, seq, history, contract, declarer, args.engine, args.vul,
                            session_id="headless_board_{}".format(board))
            if state:
                rec["declarer_tricks"] = state.get("declarer_tricks")
                rec["defender_tricks"] = state.get("defender_tricks")
                rec["result"] = state.get("result")
                print("  RESULT: 庄{} 防{}".format(state.get("declarer_tricks"), state.get("defender_tricks")))
            else:
                rec["result"] = "play_failed"
            rec["ok"] = True
        except Exception as e:
            rec["ok"] = False
            rec["error"] = str(e)
            print("  ERROR:", e)
        rec["end"] = time.strftime("%Y-%m-%d %H:%M:%S")
        results.append(rec)
        with open(os.path.join(outdir, "board_%02d.json" % board), "w", encoding="utf-8") as f:
            json.dump(rec, f, ensure_ascii=False, indent=2)
        time.sleep(1)

    with open(os.path.join(outdir, "results.json"), "w", encoding="utf-8") as f:
        json.dump(results, f, ensure_ascii=False, indent=2)
    print("DONE ALL BOARDS")

if __name__ == "__main__":
    main()