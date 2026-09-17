"""介入层管线回归脚本（直接运行，非 pytest）。

v1.84 介入层分支化架构回归：9砸 独立分支（_garrison_lead/_garrison_follow/
_garrison_target）+ 飞牌介入分支（_finesse_lead/_finesse_commit_check）。
覆盖方案 12 用例：
  1-2   9砸 独立扫描命中（缺Q持AK / 缺K持AQ）
  3     稳成线退让（另一候选做成率 1.0）
  4     跟牌侧 9砸（间张 → 顶张 A）
  5-7   cash_bank 三态（连拔 K / K 在对侧引小+九砸标记 / 对象已现清除）
  8     接应领出方校验（BUG-2：防守方领出 → None）
  9     九砸超吃后补登记 cash_bank（FIX-10）
  10    A 已砸 K 未现领出 → 无回手/继续飞强制干预（FIX-9）
  11    _stable_make 全体候选最高做成率口径（FIX-7）
  12    探针结构池空 → 9砸 仍命中（独立性回归）
  13    AKQ 在手顶张齐全（对象≤J）→ 不走 9砸（2026-09-18 用户定调）

运行: python tests/test_finesse_pipeline.py
"""

import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from bridge.play_types import Card, Contract, PlayState, PlayPhase, Trick
from bridge.play_service import PlayService


def ps_new():
    return PlayService.__new__(PlayService)


def mk_hand(spec):
    out = []
    for suit, ranks in spec.items():
        for r in ranks:
            out.append(Card(suit, r))
    return out


def mk_state(south, north, east=None, west=None, current="南",
             tricks=None, trick_cards=None, declarer="南"):
    hands = {"南": mk_hand(south), "北": mk_hand(north),
             "东": mk_hand(east or {}), "西": mk_hand(west or {})}
    contract = Contract(level=2, suit="NT", declarer=declarer,
                        doubled=False, redoubled=False)
    st = PlayState(contract=contract, hands=hands)
    st.tricks = tricks or []
    st.current_trick = Trick(trump="NT")
    for pos, card in (trick_cards or []):
        st.current_trick.add_card(pos, card)
    st.current_player = current
    st.phase = PlayPhase.PLAYING
    st.declarer_tricks = 0
    st.defender_tricks = 0
    return st


def cand(card, val=1.0, scores=None):
    if scores is None:
        scores = [6] * 10
    return {"card": card, "scoring_val": val, "avg_tricks": val, "scores": scores}


def mk_result(card, candidates):
    return {"card": card, "reasoning": "",
            "full_output": {"mcts_stats": {"candidates": candidates}}}


def t01_garrison_scan_hit():
    st = mk_state({"♠": "AK8765", "♥": "Q32"}, {"♠": "432", "♥": "J54"})
    cands = [cand("♥Q", 11.0), cand("♠A", 10.0), cand("♠8", 9.0), cand("♥J", 9.0)]
    res = mk_result(Card("♥", "Q"), cands)
    out = ps_new()._garrison_lead(st, res)
    bank = getattr(st, "nine_cash_bank", None)
    ok = (out is not None and str(out["card"]) == "♠A"
          and bank == {"♠": {"obj": 12, "rv": 13}})
    got = str(out["card"]) if out else None
    return ok, f"9砸扫描命中：♠AK8765/432 缺Q → 改♠A+登记连拔（got {got}, bank={bank}）"


def t02_garrison_scan_aq_case():
    st = mk_state({"♠": "AQ8765", "♥": "Q32"}, {"♠": "432", "♥": "J54"})
    cands = [cand("♥Q", 11.0), cand("♠A", 10.0)]
    res = mk_result(Card("♥", "Q"), cands)
    out = ps_new()._garrison_lead(st, res)
    bank = getattr(st, "nine_cash_bank", None)
    ok = (out is not None and str(out["card"]) == "♠A" and not bank)
    got = str(out["card"]) if out else None
    return ok, f"缺K持AQ：改♠A、不登记连拔（got {got}, bank={bank}）"


def t03_garrison_stable():
    st = mk_state({"♠": "AK8765", "♥": "Q32"}, {"♠": "432", "♥": "J54"})
    cands = [cand("♥Q", 11.0, scores=[8] * 10), cand("♠A", 10.0)]
    res = mk_result(Card("♥", "Q"), cands)
    out = ps_new()._garrison_lead(st, res)
    return out is None, f"稳成线（某候选做成率1.0）→ 9砸 退让（got {out is not None}）"


def t04_garrison_follow():
    trick_cards = [("西", Card("♠", "2"))]
    st = mk_state({"♠": "AQJ86", "♥": "Q32"}, {"♠": "75432", "♥": "J54"},
                  current="南", trick_cards=trick_cards)
    cands = [cand("♠J", 11.0)]
    res = mk_result(Card("♠", "J"), cands)
    out = ps_new()._garrison_follow(st, res)
    got = str(out["card"]) if out else None
    return (out is not None and got == "♠A"), f"跟牌9砸：间张J → 改♠A（got {got}）"


def t05_cash_bank_pull():
    st = mk_state({"♠": "K85", "♥": "Q32"}, {"♥": "J54"})
    st.nine_cash_bank = {"♠": {"obj": 12, "rv": 13}}
    cands = [cand("♥Q", 11.0), cand("♠K", 10.0), cand("♠8", 9.0)]
    res = mk_result(Card("♥", "Q"), cands)
    out = ps_new()._garrison_lead(st, res)
    got = str(out["card"]) if out else None
    ok = (out is not None and got == "♠K" and not st.nine_cash_bank)
    return ok, f"连拔：登记在、K 在手、对象未现 → 拔♠K 清登记（got {got}）"


def t06_cash_bank_k_opposite():
    st = mk_state({"♠": "853", "♥": "Q32"}, {"♠": "K2", "♥": "J54"})
    st.nine_cash_bank = {"♠": {"obj": 12, "rv": 13}}
    cands = [cand("♥Q", 11.0), cand("♠8", 10.0), cand("♠5", 9.0), cand("♠3", 8.0)]
    res = mk_result(Card("♥", "Q"), cands)
    out = ps_new()._garrison_lead(st, res)
    got = str(out["card"]) if out else None
    extra = getattr(st, "finesse_flow_extra", None) or {}
    ok = (out is not None and got == "♠3"
          and st.finesse_flow.get("♠") == 12
          and isinstance(extra.get("♠"), dict) and extra["♠"].get("九砸")
          and not st.nine_cash_bank)
    return ok, f"K 在对侧：引♠3+九砸标记（got {got}, flow={st.finesse_flow}, extra={extra}）"


def t07_cash_bank_obj_shown():
    hist = Trick(trump="NT")
    hist.add_card("东", Card("♠", "Q"))
    hist.add_card("南", Card("♠", "A"))
    hist.add_card("西", Card("♦", "2"))
    hist.add_card("北", Card("♦", "3"))
    st = mk_state({"♠": "K85", "♥": "Q32"}, {"♥": "J54"}, tricks=[hist])
    st.nine_cash_bank = {"♠": {"obj": 12, "rv": 13}}
    cands = [cand("♥Q", 11.0), cand("♠K", 10.0)]
    res = mk_result(Card("♥", "Q"), cands)
    out = ps_new()._garrison_lead(st, res)
    ok = (out is None and not st.nine_cash_bank)
    return ok, f"对象已现：清登记不干预（got {out is not None}, bank={st.nine_cash_bank}）"


def t08_respond_defender_lead():
    trick_cards = [("西", Card("♠", "3")), ("北", Card("♠", "2")),
                   ("东", Card("♠", "5"))]
    st = mk_state({"♠": "AQ86", "♥": "Q32"}, {"♠": "42", "♥": "J54"},
                  current="南", trick_cards=trick_cards)
    st.finesse_flow = {"♠": 13}
    fs = {"♠": {"对象": 13, "对象牌": "K", "废弃对象": []}}
    got = ps_new()._finesse_commit_check(st, fs)
    return got is None, f"防守方领出 → 接应 None（BUG-2，got {got}）"


def t09_respond_overcall_bank():
    trick_cards = [("南", Card("♠", "2")), ("东", Card("♠", "5"))]
    st = mk_state({"♠": "K8", "♥": "Q32"}, {"♠": "A43", "♥": "J54"},
                  current="北", trick_cards=trick_cards)
    st.finesse_flow = {"♠": 12}
    st.finesse_flow_extra = {"♠": {"九砸": True}}
    fs = {"♠": {"对象": 12, "对象牌": "Q", "废弃对象": []}}
    got = ps_new()._finesse_commit_check(st, fs)
    bank = getattr(st, "nine_cash_bank", None)
    ok = (got is not None and got[0] == "♠A"
          and bank == {"♠": {"obj": 12, "rv": 13}})
    return ok, f"九砸超吃：出♠A+补登记连拔（got {got}, bank={bank}）"


def t10_exit_after_cash():
    hist = Trick(trump="NT")
    hist.add_card("南", Card("♠", "A"))
    hist.add_card("西", Card("♠", "9"))
    hist.add_card("北", Card("♠", "4"))
    hist.add_card("东", Card("♠", "T"))
    st = mk_state({"♠": "Q876", "♥": "Q32"}, {"♠": "53", "♥": "J54"},
                  tricks=[hist])
    res = mk_result(Card("♥", "3"), [cand("♥3", 11.0)])
    res["full_output"]["finesse_probe"] = {}
    out = ps_new()._finesse_lead(st, res, 0.6)
    fo = out.get("full_output") or {}
    ok = (str(out["card"]) == "♥3"
          and fo.get("领出飞牌", {}).get("说明") == "无飞牌结构"
          and "9砸回手" not in fo and "继续飞牌" not in fo)
    return ok, (f"A已砸K未现领出：无强制干预（got {str(out['card'])}, "
                f"说明={fo.get('领出飞牌', {}).get('说明')}）")


def t11_stable_make():
    st = mk_state({"♠": "AK8765"}, {"♠": "432"})
    cands = [cand("♠A", 11.0, scores=[8] * 3 + [7] * 7),
             cand("♥Q", 9.0, scores=[8] * 10)]
    got = ps_new()._stable_make(st, cands)
    return got == 1.0, f"全体候选最高做成率（got {got}, 期望 1.0 非榜首 0.7）"


def t12_probe_empty_garrison_still_works():
    st = mk_state({"♠": "AK8765", "♥": "Q32"}, {"♠": "432", "♥": "J54"})
    cands = [cand("♥Q", 11.0), cand("♠A", 10.0)]
    res = mk_result(Card("♥", "Q"), cands)
    probe_absent = "finesse_probe" not in (res.get("full_output") or {})
    out = ps_new()._garrison_lead(st, res)
    ok = probe_absent and out is not None and str(out["card"]) == "♠A"
    return ok, f"探针空（蹭线失败模拟）→ 9砸 仍命中（probe_absent={probe_absent}）"


def t13_akq_no_garrison():
    st = mk_state({"♠": "AKQ876", "♥": "Q32"}, {"♠": "543", "♥": "J54"})
    cands = [cand("♥Q", 11.0), cand("♠A", 10.0)]
    res = mk_result(Card("♥", "Q"), cands)
    out = ps_new()._garrison_lead(st, res)
    bank = getattr(st, "nine_cash_bank", None)
    ok = out is None and not bank
    return ok, f"AKQ在手顶张齐全（对象=J）→ 不走9砸（got {out is not None}, bank={bank}）"


def t14_commit_top1_same_suit():
    st = mk_state({"♠": "AQ86", "♥": "Q32"}, {"♠": "42", "♥": "J54"})
    cands = [cand("♠3", 0.1), cand("♥Q", 2.0)]
    res = mk_result(Card("♠", "3"), cands)
    got = ps_new()._finesse_commit_ratio_ok(st, res, "♠8", 0.75)
    return not got, f"引擎榜首♠3 与强制♠8 同花色 → 退让采信 top1（got {got}, 期望 False）"


def t15_commit_top1_diff_suit():
    st = mk_state({"♠": "AQ86", "♥": "Q32"}, {"♠": "42", "♥": "J54"})
    cands = [cand("♥Q", 2.0), cand("♠3", 0.1)]
    res = mk_result(Card("♥", "Q"), cands)
    # 强制 ♠8 不在候选 → _finesse_ratio_ok 返回 True（动作不在榜，维持强制）
    got = ps_new()._finesse_commit_ratio_ok(st, res, "♠8", 0.75)
    return got is True, f"榜首异花色 → 走比值判定（got {got}, 期望 True）"


CASES = [
    t01_garrison_scan_hit,
    t02_garrison_scan_aq_case,
    t03_garrison_stable,
    t04_garrison_follow,
    t05_cash_bank_pull,
    t06_cash_bank_k_opposite,
    t07_cash_bank_obj_shown,
    t08_respond_defender_lead,
    t09_respond_overcall_bank,
    t10_exit_after_cash,
    t11_stable_make,
    t12_probe_empty_garrison_still_works,
    t13_akq_no_garrison,
    t14_commit_top1_same_suit,
    t15_commit_top1_diff_suit,
]


def main():
    ok = bad = 0
    for fn in CASES:
        try:
            passed, msg = fn()
        except Exception as exc:
            passed, msg = False, f"异常: {type(exc).__name__}: {exc}"
        ok += passed
        bad += (not passed)
        print(f"[{'OK' if passed else '!!'}] {fn.__name__}: {msg}")
    print(f"\n通过 {ok}/{len(CASES)}，失败 {bad}")
    sys.exit(1 if bad else 0)


if __name__ == "__main__":
    main()
