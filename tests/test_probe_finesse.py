"""探针"引牌测试"回归脚本（直接运行，非 pytest）。

验证 _probe_finesse_ok 的判定：把探针指出的引牌打出，缺失对象分别放防家两侧，
对该花色做单套双明手推演，庄家方赢墩不同 = 真飞（保留探针）；相同 = 不能飞（废弃）。

用例期望由桥牌语义与已校准推演给出：
  - 核心例：南♥AQ2 / 北♥43 / 对象K（北引4/3 构成飞 → 保留；南引2/A 无效 → 废弃）
  - 出 Q 也是飞牌：Qx 对 AJx，南引Q（对象K）→ 保留
  - 无 Q 间张飞不动 K（AJ 对 K）；引 A 对象可躲 → 废弃
  - K 在手时对象必被抓（AKJT98/32 缺Q）→ 废弃

运行: python tests/test_probe_finesse.py
"""

import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from bridge.play_types import Card, PlayState, PlayPhase
from bridge.play_service import PlayService


def _r2v():
    return PlayService._FINESSE_R2V


def hand(s_str, suit='♠'):
    r2v = _r2v()
    v2r = {v: k for k, v in r2v.items()}
    out = []
    for ch in s_str:
        out.append(Card(suit, v2r.get(r2v.get(ch, 2), '2')))
    return out


def build_state(s_str, n_str, suit):
    hands = {
        "南": hand(s_str, suit),
        "北": hand(n_str, suit),
        "东": [],
        "西": [],
    }
    contract = type("C", (), {"declarer": "南", "dummy": "北", "suit": "NT",
                              "level": 2, "tricks_needed": 8,
                              "doubled": False, "redoubled": False})()
    st = PlayState(contract=contract, hands=hands, dummy="北")
    st.tricks = []
    st.current_trick = type("T", (), {"cards": []})()
    st.current_player = "南"
    st.phase = PlayPhase.PLAYING
    st.declarer_tricks = 0
    st.defender_tricks = 0
    return st


CASES = [
    # (名称, 南该花色, 北该花色, 对象, 引牌, 引牌侧, 期望: 是否飞结构)
    # ── 核心例：南♥AQ2 / 北♥43 / 对象K ──
    ("例1 伙伴引4",           "AQ2", "43",  "K", "♥4", "伙伴侧", True),
    ("例1 伙伴引3",           "AQ2", "43",  "K", "♥3", "伙伴侧", True),
    ("例1 本侧引2(无效)",      "AQ2", "43",  "K", "♥2", "本侧", False),
    ("例1 本侧引A(对象可躲)",  "AQ2", "43",  "K", "♥A", "本侧", False),
    # ── 用户例：庄K567 / 明234 / 明手引2 / 对象A（对侧K可比A小且盖住防家余牌）──
    ("K对A 明手引2",           "K567", "234", "A", "♥2", "伙伴侧", True),
    # ── 出 Q 也是飞牌：Qx 对 AJx，对象K（对侧J 盖住防家余牌）──
    ("Qx对AJx 本侧引Q(真飞)",  "Q3",  "AJ6", "K", "♥Q", "本侧", True),
    # ── 无间张/盖不住 → 不飞 ──
    ("AJ对K 伙伴引2(无Q)",     "AJ",  "982", "K", "♠2", "伙伴侧", False),
    ("AKJT98对32 缺Q(对侧有J)", "AKJT98", "32", "Q", "♥3", "伙伴侧", True),
]


def main():
    ps = PlayService.__new__(PlayService)
    r2v = _r2v()
    ok = bad = 0
    print(f"{'#':<3}{'样例':<24}{'引牌侧':<6}{'判定':<8}{'期望':<8}{'结果'}")
    for i, (name, s, n, obj_r, lead, side, expect) in enumerate(CASES, 1):
        st = build_state(s, n, lead[0])
        info = {"对象": r2v[obj_r], "引牌": lead, "侧": side}
        got = ps._probe_finesse_ok(st, lead[0], info)
        match = (got == expect)
        ok += match
        bad += (not match)
        print(f"{i:<3}{name:<24}{side:<6}"
              f"{'保留' if got else '废弃':<8}{'保留' if expect else '废弃':<8}"
              f"{'OK' if match else '!! 误判'}")
    print(f"\n通过 {ok}/{len(CASES)}，误判 {bad}")
    sys.exit(1 if bad else 0)


if __name__ == '__main__':
    main()