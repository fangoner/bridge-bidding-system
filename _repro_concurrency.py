import json
import sys
import threading
import time

import requests

BASE = "http://127.0.0.1:8003"
ROLES = {"南": "ai", "西": "ai", "北": "ai", "东": "ai"}


def post(path, payload, timeout=200):
    r = requests.post(BASE + path, json=payload, timeout=timeout)
    r.raise_for_status()
    return r.json()


def deal():
    return post("/api/deal", {"mode": "free"})["hands"]


def to_hand_dicts(hands):
    return hands


ME = {"run": True, "result": None}


def ai_play_worker(hands, seq, contract, declarer, tag, session_id):
    payload = {
        "hands": hands,
        "contract": contract,
        "declarer": declarer,
        "player_roles": ROLES,
        "bidding_sequence": "".join("({})pass-".format(p) for p in ["南", "西", "北", "东"]),
        "vulnerability": "NV",
        "session_id": session_id,
    }
    init = post("/api/play/init", payload, timeout=60)
    if not init["success"]:
        ME["result"] = (tag, "init_failed", init.get("error"))
        return
    print(f"[{tag}] init ok, current_player={init['state']['current_player']} (session={session_id})")
    # ai-play 内部 DD 计算会 await asyncio.to_thread 让出事件循环，
    # 让另一线程有机会 play_init 覆盖（本次应被会话隔离挡住）。
    res = post("/api/play/ai-play", {
        "play_engine": "dd_alphamu_llm",
        "use_llm_review": False,
        "session_id": session_id,
    }, timeout=200)
    ME["result"] = (tag, res.get("success"), res.get("error"), res.get("card"))
    print(f"[{tag}] ai-play success={res.get('success')} err={res.get('error')} card={res.get('card')}")


def main():
    hands_a = deal()
    hands_b = deal()

    # 故意用明显不同的定约/庄家，方便识别窜到对方牌局
    seq = [{"position": "南", "bid": "pass"}, {"position": "西", "bid": "pass"},
           {"position": "北", "bid": "1S"}, {"position": "东", "bid": "pass"},
           {"position": "南", "bid": "4S"}, {"position": "西", "bid": "pass"},
           {"position": "北", "bid": "pass"}, {"position": "东", "bid": "pass"}]

    # 游戏 A / 游戏 B 使用各自独立的会话
    t = threading.Thread(target=ai_play_worker,
                         args=(hands_a, seq, "4S", "南", "A", "session_A"), daemon=True)
    t.start()

    # 在 A 的 DD 计算窗口期，用 B 的独立会话初始化（不应影响 A）
    time.sleep(0.8)
    print("[B] 覆盖 play_init (游戏 B, session=session_B)")
    post("/api/play/init", {
        "hands": hands_b,
        "contract": "3NT",
        "declarer": "北",
        "player_roles": ROLES,
        "bidding_sequence": "".join("({})pass-".format(p) for p in ["南", "西", "北", "东"]),
        "vulnerability": "NV",
        "session_id": "session_B",
    }, timeout=60)
    print("[B] play_init done")

    t.join(timeout=220)
    print("\nRESULT:", ME["result"])


if __name__ == "__main__":
    main()