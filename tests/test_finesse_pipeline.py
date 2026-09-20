"""介入层管线回归脚本（直接运行，非 pytest）。

v1.84 介入层分支化架构回归：9砸 独立分支（_garrison_lead/_garrison_follow/
_garrison_target）+ 飞牌介入分支（_finesse_lead/_finesse_commit_check）。
覆盖方案 12 用例：
  1-2   9砸 独立扫描命中（缺Q持AK / 缺K持AQ）
  3     稳成线退让（引擎 top1 做成率 ≥85%）
  4     跟牌侧 9砸（间张 → 顶张 A）
  5-7   cash_bank 三态（连拔 K / K 在对侧引小+九砸标记 / 对象已现清除）
  8     接应领出方校验（BUG-2：防守方领出 → None）
  9     九砸超吃后补登记 cash_bank（FIX-10）
  10    A 已砸 K 未现领出 → 无回手/继续飞强制干预（FIX-9）
  11    _top1_make 只取引擎 top1 做成率（2026-09-20 口径；旧为全体候选最高）
  12    探针结构池空 → 9砸 仍命中（独立性回归）
  13    AKQ 在手顶张齐全（对象≤J）→ 不走 9砸（2026-09-18 用户定调）
  26-29 v1.96 三层接应判据：押对方向桶内引擎最优替代牌成率 b_bucket
       ≤0.05 强制接应（6NT 型）/ ≥0.40 退让引擎（B26 型）/ 灰色区与
       数据缺失走 v1.93 兜底

运行: python tests/test_finesse_pipeline.py
"""

import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from bridge.play_types import Card, Contract, PlayState, PlayPhase, Trick
from bridge.play_service import PlayService
from bridge.mcts.dd_search import (_finalize_finesse_probe,
                                   _accumulate_finesse_probe_follow,
                                   _finalize_finesse_probe_follow)


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


def t11_top1_make_semantics():
    """稳成线口径：只取**引擎 top1** 做成率（2026-09-20 用户定调）。

    旧口径（v1.84 FIX-7）取全体候选最高——top1=0.7、另有候选 1.0 时会判稳成；
    新口径只看 top1，故此处期望 0.7（**不再**被那条 1.0 的候选拉高）。
    """
    st = mk_state({"♠": "AK8765"}, {"♠": "432"})
    cands = [cand("♠A", 11.0, scores=[8] * 3 + [7] * 7),   # top1 做成率 0.3
             cand("♥Q", 9.0, scores=[8] * 10)]              # 次选 1.0（不应被采纳）
    got = ps_new()._top1_make(st, cands)
    ok = abs(got - 0.3) < 1e-9
    return ok, (f"只取 top1 做成率（got {got}, 期望 0.3；旧口径会返回 1.0）")


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
    got = ps_new()._finesse_commit_ratio_ok(st, res, "♠8", 0.75,
                                            finesse_struct={"♠": {"对象": 13}})
    return not got, f"榜首♠3间张（<对象K）同花色 → 采信 top1（got {got}, 期望 False）"


def t15_commit_top1_diff_suit():
    st = mk_state({"♠": "AQ86", "♥": "Q32"}, {"♠": "42", "♥": "J54"})
    cands = [cand("♥Q", 2.0), cand("♠3", 0.1)]
    res = mk_result(Card("♥", "Q"), cands)
    # 强制 ♠8 不在候选 → _finesse_ratio_ok 返回 True（动作不在榜，维持强制）
    got = ps_new()._finesse_commit_ratio_ok(st, res, "♠8", 0.75)
    return got is True, f"榜首异花色 → 走比值判定（got {got}, 期望 True）"


def _probe_entry(suit, obj, lead, delta, side="本侧", direction=None, bucket=None):
    return {"花色": suit, "对象": obj, "对象牌": {13: "K", 12: "Q", 11: "J"}.get(obj, "?"),
            "引牌": lead, "Δ": delta, "侧": side, "来源": "probe",
            "方向": direction, "押桶成": bucket,
            "废弃对象": [], "全": []}


def t16_partner_overhand_fail_back_to_local():
    st = mk_state({"♣": "A2", "♥": "Q"}, {"♣": "43"})
    cands = [cand("♥Q", 0.5), cand("♣2", 0.48)]
    base = {"♣": [_probe_entry("♣", 13, "♣2", 0.5),
                  _probe_entry("♣", 13, "♣9", 0.9, side="伙伴侧")]}
    res = mk_result(Card("♥", "Q"), cands)
    got = ps_new()._probe_lead_finesse_prefer(st, base, cands, 0.75, res)
    ok = (got is not None and got[0] == "♣2"
          and st.finesse_flow.get("♣") == 13)
    return ok, (f"过手失败弹栈→回退本侧直飞♣2+登记（got {got}, flow={st.finesse_flow}）")


def t17_all_rejected():
    st = mk_state({"♣": "A2", "♥": "Q"}, {"♣": "43"})
    cands = [cand("♥A", 0.9), cand("♣2", 0.4)]
    base = {"♣": [_probe_entry("♣", 13, "♣2", 0.5)]}
    res = mk_result(Card("♥", "A"), cands)
    got = ps_new()._probe_lead_finesse_prefer(st, base, cands, 0.75, res)
    return got is None, f"全被否（0.44<0.70）→ 尊重引擎（got {got}）"


def t18_multi_action_final_select():
    st = mk_state({"♣": "A2", "♦": "Q3", "♥": "Q"}, {"♣": "43", "♦": "65"})
    cands = [cand("♥Q", 0.5), cand("♣2", 0.5), cand("♦2", 0.49)]
    base = {"♣": [_probe_entry("♣", 13, "♣2", 0.4)],
            "♦": [_probe_entry("♦", 11, "♦2", 0.2)]}
    res = mk_result(Card("♥", "Q"), cands)
    got = ps_new()._probe_lead_finesse_prefer(st, base, cands, 0.75, res)
    ok = (got is not None and got[0] == "♣2"
          and st.finesse_flow.get("♣") == 13)
    return ok, f"两花色均过闸→终选引擎判据选♣2 登记♣（got {got}, flow={st.finesse_flow}）"


def t19_stable_exit_no_touch():
    st = mk_state({"♣": "A2", "♥": "Q3"}, {"♣": "43", "♥": "J4"})
    cands = [cand("♥3", 1.0, scores=[8] * 10), cand("♣2", 0.9, scores=[8] * 10)]
    res = mk_result(Card("♥", "3"), cands)
    res["full_output"]["finesse_probe"] = {
        "♣": {"对象": "K", "Δ": 0.5, "引牌": "♣2",
              "全": [{"对象": "K", "Δ": 0.5, "引牌": "♣2"}]}}
    out = ps_new()._finesse_lead(st, res, 0.75)
    fo = out.get("full_output") or {}
    ok = (str(out["card"]) == "♥3"
          and not getattr(st, "finesse_flow", {})
          and "提前退让" in (fo.get("领出飞牌", {}).get("说明") or ""))
    return ok, (f"稳成≥95%→提前退让不登记（card={out['card']}, "
                f"flow={getattr(st, 'finesse_flow', None)}, 说明={fo.get('领出飞牌', {}).get('说明')}）")


def t20_stable_but_engine_leading_finesse():
    st = mk_state({"♣": "A2", "♥": "Q3"}, {"♣": "43", "♥": "J4"})
    cands = [cand("♣2", 0.9, scores=[8] * 10), cand("♥3", 1.0, scores=[8] * 10)]
    res = mk_result(Card("♣", "2"), cands)
    res["full_output"]["finesse_probe"] = {
        "♣": {"对象": "K", "Δ": 0.5, "引牌": "♣2",
              "全": [{"对象": "K", "Δ": 0.5, "引牌": "♣2"}]}}
    out = ps_new()._finesse_lead(st, res, 0.75)
    fo = out.get("full_output") or {}
    ok = (str(out["card"]) == "♣2"
          and st.finesse_flow.get("♣") == 13
          and fo.get("领出飞牌", {}).get("引发") is True)
    return ok, f"稳成但引擎在飞牌花色→仍登记接应（flow={st.finesse_flow}）"


def t21_delta_not_in_select():
    st = mk_state({"♣": "AQ2", "♥": "Q"}, {"♣": "43"})
    cands = [cand("♥Q", 0.5), cand("♣2", 0.48), cand("♣5", 0.47)]
    base = {"♣": [_probe_entry("♣", 13, "♣2", 0.3),
                  _probe_entry("♣", 12, "♣5", 0.9)]}
    res = mk_result(Card("♥", "Q"), cands)
    got = ps_new()._probe_lead_finesse_prefer(st, base, cands, 0.75, res)
    ok = (got is not None and got[0] == "♣2")
    return ok, f"Δ只当门票：Δ0.9 的♣5 未胜出，引擎判据选价值高的♣2（got {got}）"


def t22_vote_switch_off():
    st = mk_state({"♠": "AK", "♥": "Q3"}, {"♠": "32", "♥": "J4"})
    cands = [cand("♠A", 0.6, scores=[6] * 10), cand("♥Q", 0.4, scores=[4] * 5 + [8] * 5)]
    res = mk_result(Card("♠", "A"), cands)
    got = ps_new()._dd_maybe_majority_vote(st, res, Card("♠", "A"))
    return got is None, f"DD_MAJORITY_VOTES=1（默认关）→ 不触发票选（got {got}）"


def t23_commit_topcard_top1_falls_to_ratio():
    st = mk_state({"♠": "AQJ6", "♥": "Q32"}, {"♠": "42", "♥": "K54"})
    fs = {"♠": {"对象": 12}}
    cands_keep = [cand("♠A", 2.0, scores=[8] * 10),
                  cand("♠J", 1.0, scores=[8, 8, 8, 8, 8, 8, 8, 8, 2, 2]),
                  cand("♥Q", 1.5)]
    res_keep = mk_result(Card("♠", "A"), cands_keep)
    got_keep = ps_new()._finesse_commit_ratio_ok(st, res_keep, "♠J", 0.75,
                                                 finesse_struct=fs)
    cands_drop = [cand("♠A", 2.0, scores=[8] * 10),
                  cand("♠J", 1.0, scores=[8, 8, 8, 8, 8, 2, 2, 2, 2, 2]),
                  cand("♥Q", 1.5)]
    res_drop = mk_result(Card("♠", "A"), cands_drop)
    got_drop = ps_new()._finesse_commit_ratio_ok(st, res_drop, "♠J", 0.75,
                                                 finesse_struct=fs)
    ok = got_keep is True and got_drop is False
    return ok, (f"榜首♠A顶张（≥对象Q）落比值退让：0.8≥0.75 维持强制"
                f"（got {got_keep}），0.5<0.75 退让（got {got_drop}）")


def t24_reverse_route_duel():
    st = mk_state({"♦": "T42", "♠": "A2", "♥": "Q"}, {"♦": "AJ", "♠": "K5"})
    cands = [cand("♥Q", 0.49, scores=[8] * 5 + [6] * 5),
             cand("♠2", 0.45, scores=[6] * 10),
             cand("♦4", 0.20, scores=[6] * 10)]
    base = {"♦": [_probe_entry("♦", 12, "♦4", 0.30, direction="西", bucket=0.553),
                  _probe_entry("♦", 12, "♦J", 0.20, side="伙伴侧",
                               direction="东", bucket=0.405)]}
    res = mk_result(Card("♥", "Q"), cands)
    got = ps_new()._probe_lead_finesse_prefer(st, base, cands, 0.75, res)
    ok = (got is not None and got[0] == "♦4"
          and st.finesse_flow.get("♦") == 12)
    return ok, (f"反向路线对决：押西0.553>押东0.405 → 淘汰押东派（过手♠2），"
                f"南直飞♦4（got {got}, flow={st.finesse_flow}）")


def t25_local_bucket_molecule():
    st = mk_state({"♣": "A2", "♥": "Q"}, {"♣": "43"})
    cands = [cand("♥Q", 1.0, scores=[8] * 10),
             cand("♣2", 0.5, scores=[6] * 10)]
    base = {"♣": [_probe_entry("♣", 13, "♣2", 0.3, direction="西", bucket=0.8)]}
    res = mk_result(Card("♥", "Q"), cands)
    got = ps_new()._probe_lead_finesse_prefer(st, base, cands, 0.75, res)
    ok = (got is not None and got[0] == "♣2"
          and st.finesse_flow.get("♣") == 13)
    return ok, (f"本侧分子=押桶成0.8：0.8≥0.70 过闸启动（旧口径引擎值0.5"
                f"会退让；got {got}）")


def _mk_follow_state(direction="西"):
    st = mk_state({"♦": "AJ2", "♠": "Q32"}, {"♦": "43"})
    st.finesse_flow = {"♦": 12}
    st.finesse_flow_extra = {"♦": {"方向": direction}}
    return st


def _mk_follow_result(cands, west_bucket, east_bucket=None, card=Card("♦", "A")):
    res = mk_result(card, cands)
    res["full_output"]["finesse_probe_follow"] = {
        "♦": {"对象": 12, "东": east_bucket or {}, "西": west_bucket}}
    return res


def t26_follow_tier_force_6nt():
    st = mk_state({"♦": "AJ2", "♠": "Q32"}, {"♦": "43"})
    ps_new()._register_finesse_flow(st, "♦", 12, {"方向": "西"})
    reg_ok = (st.finesse_flow.get("♦") == 12
              and (getattr(st, "finesse_flow_extra", {}).get("♦") or {}).get("方向") == "西")
    cands = [cand("♦A", 0.254, scores=[6] * 10), cand("♦J", 0.167, scores=[5] * 10),
            cand("♠Q", 0.2, scores=[4] * 10)]
    res = _mk_follow_result(cands, {"♦A": 0.0, "♦J": 0.353})
    got = ps_new()._finesse_commit_ratio_ok(st, res, "♦J", 0.75,
                                            finesse_struct={"♦": {"对象": 12}})
    ok = reg_ok and got is True
    return ok, (f"6NT型：押西桶榜首♦A成0（不飞即死）→ 强制♦J"
                f"（登记方向={reg_ok}, got {got}, 期望 True）")


def t27_follow_tier_defer_b26():
    st = _mk_follow_state()
    cands = [cand("♦A", 0.542, scores=[6] * 10), cand("♦Q", 1.0, scores=[5] * 10)]
    res = _mk_follow_result(cands, {"♦A": 0.542, "♦Q": 1.0})
    got = ps_new()._finesse_commit_ratio_ok(st, res, "♦Q", 0.75,
                                            finesse_struct={"♦": {"对象": 12}})
    return got is False, (f"B26型：押西桶榜首♦A成0.542≥0.40（定约不依赖"
                          f"飞牌）→ 退让引擎♦A（got {got}, 期望 False）")


def t28_follow_gray_zone_v193():
    st = _mk_follow_state()
    fs = {"♦": {"对象": 12}}
    cands_keep = [cand("♦A", 0.35), cand("♦J", 0.30)]
    res_keep = _mk_follow_result(cands_keep, {"♦A": 0.2, "♦J": 0.25})
    got_keep = ps_new()._finesse_commit_ratio_ok(st, res_keep, "♦J", 0.75,
                                                 finesse_struct=fs)
    cands_drop = [cand("♦A", 0.35), cand("♦J", 0.23)]
    res_drop = _mk_follow_result(cands_drop, {"♦A": 0.2, "♦J": 0.25})
    got_drop = ps_new()._finesse_commit_ratio_ok(st, res_drop, "♦J", 0.75,
                                                 finesse_struct=fs)
    ok = got_keep is True and got_drop is False
    return ok, (f"灰色区（b=0.2）走 v1.93 比值：0.857≥0.75 维持强制"
                f"（got {got_keep}），0.657<0.75 退让（got {got_drop}）")


def t29_follow_data_missing_fallback():
    st = _mk_follow_state()
    fs = {"♦": {"对象": 12}}
    cands = [cand("♦A", 0.254), cand("♦J", 0.167)]
    res_none = mk_result(Card("♦", "A"), cands)
    got_none = ps_new()._finesse_commit_ratio_ok(st, res_none, "♦J", 0.75,
                                                 finesse_struct=fs)
    res_zero = _mk_follow_result(cands, {"♦A": 0.0, "♦J": 0.0})
    got_zero = ps_new()._finesse_commit_ratio_ok(st, res_zero, "♦J", 0.75,
                                                 finesse_struct=fs)
    ok = got_none is False and got_zero is False
    return ok, (f"数据缺失/双零死局 → v1.93 兜底比值 0.657<0.75 退让"
                f"（无探针 got {got_none}, 双零 got {got_zero}, 期望均 False）")


def t30_combo_merge_strong_signal():
    def bucket(rate, n=20):
        return [10] * int(rate * n) + [9] * (n - int(rate * n))
    probe = {"♠": {
        "K": {"东": {"2": bucket(0.40)}, "西": {"2": bucket(0.70)}},
        "Q": {"东": {"3": bucket(0.35)}, "西": {"3": bucket(0.60)}},
    }}
    out = _finalize_finesse_probe(probe, 10)
    info = out.get("♠") or {}
    all_e = info.get("全") or []
    ok = (info.get("对象") == "K" and abs(info.get("Δ", 0) - 0.55) < 1e-6
          and len(all_e) == 1 and all_e[0].get("组合飞") is True
          and all_e[0].get("废弃对象") == ["Q"])
    single = _finalize_finesse_probe({"♠": {"K": probe["♠"]["K"]}}, 10)
    s_all = (single.get("♠") or {}).get("全") or []
    ok = ok and len(s_all) == 1 and not s_all[0].get("组合飞")
    return ok, (f"强信号双飞合并：K Δ0.30 + Q Δ0.25 单条均达标 → 保K废弃Q、"
                f"Δ=加和0.55、组合飞标记（对象={info.get('对象')}, "
                f"Δ={info.get('Δ')}, 全={all_e}）；单对象不合并"
                f"（对照组合飞={s_all[0].get('组合飞')}）")


def t31_combo_confirm_and_continuation():
    st = mk_state({"♠": "AT98", "♥": "Q32"}, {"♠": "J32", "♥": "J54"},
                  east={"♥": "K87"}, west={"♥": "T96"})
    merged = {"侧": "本侧", "对象": 13, "对象牌": "K", "引牌": "♠8",
              "废弃对象": ["Q"]}
    solo = {"侧": "本侧", "对象": 13, "对象牌": "K", "引牌": "♠8",
            "废弃对象": []}
    ok_merged = ps_new()._probe_finesse_ok(st, "♠", dict(merged))
    ok_solo = ps_new()._probe_finesse_ok(st, "♠", dict(solo))
    hist = Trick(trump="NT")
    hist.add_card("东", Card("♠", "K"))
    hist.add_card("南", Card("♠", "9"))
    hist.add_card("西", Card("♠", "7"))
    hist.add_card("北", Card("♠", "3"))
    st2 = mk_state({"♠": "AT98", "♥": "Q32"}, {"♠": "J32", "♥": "J54"},
                   east={"♥": "K87"}, west={"♥": "T96"}, tricks=[hist])
    nxt = {"侧": "本侧", "对象": 12, "对象牌": "Q", "引牌": "♠8",
           "废弃对象": []}
    ok_cont = ps_new()._probe_finesse_ok(st2, "♠", dict(nxt))
    ok = (ok_merged is True and ok_solo is False and ok_cont is True)
    return ok, (f"双缺KQ确认链：南♠AT98+北♠J32，合并条目（废弃Q）确认"
                f"（got {ok_merged}），不合并双判废（got {ok_solo}），"
                f"K出后续飞Q自动确认（got {ok_cont}）")


def t32_follow_severe_bucket_force():
    st = mk_state({"♠": "AT98", "♥": "Q32"}, {"♠": "43", "♥": "J54"})
    ps_new()._register_finesse_flow(st, "♠", 13, {"方向": "东", "废弃对象": ["Q"]})
    eq = [6] * 10
    cands = [cand("♠8", 0.656, scores=eq), cand("♠T", 0.656, scores=eq),
             cand("♠9", 0.656, scores=eq), cand("♠A", 0.641, scores=[7] * 10)]
    res = mk_result(Card("♠", "A"), cands)
    res["full_output"]["finesse_probe_follow"] = {
        "♠": {"对象": 13,
              "东": {"♠A": 0.745, "♠8": 0.91, "♠T": 0.91},
              "东·严峻": {"♠A": 0.0, "♠8": 0.353}}}
    got = ps_new()._finesse_commit_ratio_ok(st, res, "♠8", 0.75,
                                            finesse_struct={"♠": {"对象": 13}})
    return got is True, (f"双飞KQ同东：严峻桶引擎最优♠A成0（Q干扰剔除）"
                         f"→ 强制接应♠8（旧口径普通桶top_alt=♠T成0.91"
                         f"误判退让；got {got}, 期望 True）")


def t33_follow_severe_missing_falls_back():
    st = mk_state({"♠": "AT98", "♥": "Q32"}, {"♠": "43", "♥": "J54"})
    ps_new()._register_finesse_flow(st, "♠", 13, {"方向": "东", "废弃对象": ["Q"]})
    eq = [6] * 10
    cands = [cand("♠8", 0.6, scores=eq), cand("♠A", 0.542, scores=[7] * 10)]
    res = mk_result(Card("♠", "A"), cands)
    res["full_output"]["finesse_probe_follow"] = {
        "♠": {"对象": 13, "东": {"♠A": 0.542, "♠8": 1.0}}}
    got = ps_new()._finesse_commit_ratio_ok(st, res, "♠8", 0.75,
                                            finesse_struct={"♠": {"对象": 13}})
    return got is False, (f"Q异侧（K东Q西）：严峻桶空落回普通东桶，"
                          f"♠A成0.542≥0.40 → 退让引擎（got {got}, 期望 False）")


def t34_accumulate_follow_severe_key():
    def run(east, west, disc):
        st = mk_state({"♠": "AT98", "♥": "Q32"}, {"♠": "43", "♥": "J54"})
        st.finesse_flow = {"♠": 13}
        st.finesse_flow_extra = {"♠": {"废弃对象": disc}} if disc else {}
        st.hands["东"] = mk_hand(east)
        st.hands["西"] = mk_hand(west)
        pf = {}
        _accumulate_finesse_probe_follow({("♠", "A"): 10, ("♠", "8"): 11},
                                         [Card("♠", "A"), Card("♠", "8")],
                                         st, st.hands, pf, 12, True)
        return pf

    same = run({"♠": "KQ", "♥": "2"}, {"♠": "6", "♥": "3"}, ["Q"])
    opp = run({"♠": "K", "♥": "2"}, {"♠": "Q6", "♥": "3"}, ["Q"])
    solo = run({"♠": "K", "♥": "2"}, {"♠": "Q6", "♥": "3"}, [])
    ok = (list((same.get("♠") or {}).keys()) == ["对象", "东·严峻"]
          and same["♠"]["东·严峻"].get("♠A") == [10]
          and same["♠"]["东·严峻"].get("♠8") == [11]
          and list((opp.get("♠") or {}).keys()) == ["对象", "东"]
          and list((solo.get("♠") or {}).keys()) == ["对象", "东"])
    fin = _finalize_finesse_probe_follow(same, 11)
    ok = ok and fin.get("♠", {}).get("东·严峻") == {"♠A": 0.0, "♠8": 1.0}
    return ok, (f"严峻子桶键判定：KQ同东记'东·严峻'、Q异侧记'东'、"
                f"单飞无废弃对象记'东'；finalize输出严峻成率"
                f"（same={same.get('♠')}, fin={fin.get('♠')}）")


def t35_final_select_bucket_rank():
    st = mk_state({"♣": "A2", "♦": "QJ2", "♥": "Q"}, {"♣": "43"})
    cands = [cand("♥Q", 0.5, scores=[8] * 10),
             cand("♦2", 0.48), cand("♦J", 0.473)]
    base = {"♦": [_probe_entry("♦", 13, "♦2", 0.9, direction="西", bucket=0.75),
                  _probe_entry("♦", 13, "♦J", 0.9, direction="西", bucket=0.85)]}
    res = mk_result(Card("♥", "Q"), cands)
    got = ps_new()._probe_lead_finesse_prefer(st, base, cands, 0.75, res)
    ok = (got is not None and got[0] == "♦J"
          and st.finesse_flow.get("♦") == 13)
    return ok, (f"终选押桶成主排序：♦J押桶0.85>♦2的0.75 胜出（引擎混合值"
                f"♦2 0.48>♦J 0.473，旧口径选♦2；got {got}, flow={st.finesse_flow}）")


def t36_engine_already_leading_finesse_register():
    """早退分支（v1.99+）：引擎 top1 恰为本侧引牌且未稳成时，不再无条件服从，
    走 _subset_select 押桶成终选后登记。单条目场景=尊重引擎引牌+登记接应。"""
    st = mk_state({"♦": "Q32", "♥": "Q5"}, {"♦": "AJ6", "♥": "J4"})
    cands = [cand("♦Q", 0.4, scores=[6] * 10), cand("♥Q", 0.5, scores=[7] * 5 + [9] * 5)]
    res = mk_result(Card("♦", "Q"), cands)
    res["full_output"]["finesse_probe"] = {
        "♦": {"对象": "K", "Δ": 0.5, "引牌": "♦Q", "方向": "东", "押桶成": 0.9,
              "全": [{"对象": "K", "Δ": 0.5, "引牌": "♦Q", "方向": "东",
                      "押桶成": 0.9}]}}
    out = ps_new()._finesse_lead(st, res, 0.75)
    fo = out.get("full_output") or {}
    ok = (str(out["card"]) == "♦Q"
          and st.finesse_flow.get("♦") == 13
          and fo.get("领出飞牌", {}).get("引发") is True
          and "押桶成" in (fo.get("领出飞牌", {}).get("说明") or ""))
    return ok, (f"引擎已在飞牌花色（非稳成）：押桶成终选保留引擎引牌+登记接应"
                f"（card={out['card']}, flow={st.finesse_flow}, "
                f"说明={fo.get('领出飞牌', {}).get('说明')}）")


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
    t11_top1_make_semantics,
    t12_probe_empty_garrison_still_works,
    t13_akq_no_garrison,
    t14_commit_top1_same_suit,
    t15_commit_top1_diff_suit,
    t16_partner_overhand_fail_back_to_local,
    t17_all_rejected,
    t18_multi_action_final_select,
    t19_stable_exit_no_touch,
    t20_stable_but_engine_leading_finesse,
    t21_delta_not_in_select,
    t22_vote_switch_off,
    t23_commit_topcard_top1_falls_to_ratio,
    t24_reverse_route_duel,
    t25_local_bucket_molecule,
    t26_follow_tier_force_6nt,
    t27_follow_tier_defer_b26,
    t28_follow_gray_zone_v193,
    t29_follow_data_missing_fallback,
    t30_combo_merge_strong_signal,
    t31_combo_confirm_and_continuation,
    t32_follow_severe_bucket_force,
    t33_follow_severe_missing_falls_back,
    t34_accumulate_follow_severe_key,
    t35_final_select_bucket_rank,
    t36_engine_already_leading_finesse_register,
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
