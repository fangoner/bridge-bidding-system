"""介入层管线回归脚本（直接运行，非 pytest）。

2026-09-22（v2.07）移除 9砸 分支：_garrison_lead/_garrison_follow/
_garrison_target、nine_cash_bank、FINESSE_EIGHT_NINE_ENABLE 全部删除——
DD 做成率口径的段2 无损清将 + 段4 飞牌介入已覆盖抓 Q/顶张兑现，规则式
9砸 属受限式修正被卸除（项目铁律；9砸 曾为"差距大也照砸"的静态规则）。
剩余用例覆盖：
  · 段4 飞牌介入：启动/过手/终选/比值退让/稳成退让
  · 接应退让判据（2026-09-25 两步，删 0.05 强制分支与同花色①②分流）：
    第一步 b_押注 ≥0.50 且 ≥非押注桶 → 退让引擎（B26 型）；
    不满足 → 第二步 flyer/top_alt 比值 0.75（≥0.75 强制）
  · 多数投票默认关；_top1_make 只取引擎 top1 做成率
运行: python tests/test_finesse_pipeline.py
"""

import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from bridge.play_types import Card, Contract, PlayState, PlayPhase, Trick
from bridge.play_service import PlayService
from bridge.mcts.dd_search import (_finalize_finesse_probe,
                                   _accumulate_finesse_probe,
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


def t08_respond_defender_lead():
    trick_cards = [("西", Card("♠", "3")), ("北", Card("♠", "2")),
                   ("东", Card("♠", "5"))]
    st = mk_state({"♠": "AQ86", "♥": "Q32"}, {"♠": "42", "♥": "J54"},
                  current="南", trick_cards=trick_cards)
    st.finesse_flow = {"♠": 13}
    fs = {"♠": {"对象": 13, "对象牌": "K", "废弃对象": []}}
    got = ps_new()._finesse_commit_check(st, fs)
    return got is None, f"防守方领出 → 接应 None（BUG-2，got {got}）"


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


def t14_commit_ratio_keeps_flyer_not_in_cands():
    st = mk_state({"♠": "AQ86", "♥": "Q32"}, {"♠": "42", "♥": "J54"})
    ps_new()._register_finesse_flow(st, "♠", 13, {"方向": "西"})
    cands = [cand("♠3", 0.1), cand("♥Q", 2.0)]
    res = mk_result(Card("♠", "3"), cands)
    res["full_output"]["finesse_probe_follow"] = {
        "♠": {"对象": 13, "西": {"♠3": 0.10, "♠8": 0.30},
              "东": {"♠3": 0.20, "♠8": 0.40}}}
    got = ps_new()._finesse_commit_ratio_ok(st, res, "♠8", 0.75,
                                            finesse_struct={"♠": {"对象": 13}})
    return got is True, f"第一步 b_押注=0.10<0.50 不触发 → 第二步比值，flyer♠8 不在候选 → 维持强制（got {got}, 期望 True）"


def t15_commit_ratio_diff_suit_keeps():
    st = mk_state({"♠": "AQ86", "♥": "Q32"}, {"♠": "42", "♥": "J54"})
    ps_new()._register_finesse_flow(st, "♠", 13, {"方向": "西"})
    cands = [cand("♥Q", 2.0), cand("♠3", 0.1)]
    res = mk_result(Card("♥", "Q"), cands)
    res["full_output"]["finesse_probe_follow"] = {
        "♠": {"对象": 13, "西": {"♥Q": 0.20, "♠3": 0.10},
              "东": {"♥Q": 0.30, "♠3": 0.20}}}
    # 强制 ♠8 不在候选 → 比值无法评估动作 → 维持强制
    got = ps_new()._finesse_commit_ratio_ok(st, res, "♠8", 0.75,
                                            finesse_struct={"♠": {"对象": 13}})
    return got is True, f"榜首异花色走第二步比值，flyer♠8 不在候选 → 维持强制（got {got}, 期望 True）"


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
    # 真飞结构：南♣A3 / 北♣Q2，防家 ♣K(对象)+J，对侧 G=北 Q=12
    # 满足 K(13) > Q(12) > max_enemy J(11) — 过 _probe_finesse_ok 确认
    st = mk_state({"♣": "A3", "♥": "Q3"}, {"♣": "Q2", "♥": "J4"})
    cands = [cand("♣3", 0.9, scores=[8] * 10), cand("♥3", 1.0, scores=[8] * 10)]
    res = mk_result(Card("♣", "3"), cands)
    res["full_output"]["finesse_probe"] = {
        "♣": {"对象": "K", "Δ": 0.5, "引牌": "♣3",
              "全": [{"对象": "K", "Δ": 0.5, "引牌": "♣3"}]}}
    out = ps_new()._finesse_lead(st, res, 0.75)
    fo = out.get("full_output") or {}
    ok = (str(out["card"]) == "♣3"
          and st.finesse_flow.get("♣") == 13
          and fo.get("领出飞牌", {}).get("引发") is True)
    return ok, f"稳成且引擎在已确认飞牌花色→登记接应（flow={st.finesse_flow}）"


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
    ps_new()._register_finesse_flow(st, "♠", 12, {"方向": "西"})
    fs = {"♠": {"对象": 12}}
    cands_keep = [cand("♠A", 2.0, scores=[8] * 10),
                  cand("♠J", 1.0, scores=[8, 8, 8, 8, 8, 8, 8, 8, 2, 2]),
                  cand("♥Q", 1.5)]
    res_keep = mk_result(Card("♠", "A"), cands_keep)
    res_keep["full_output"]["finesse_probe_follow"] = {
        "♠": {"对象": 12, "西": {"♠A": 0.30, "♠J": 0.25},
              "东": {"♠A": 0.45, "♠J": 0.40}}}
    got_keep = ps_new()._finesse_commit_ratio_ok(st, res_keep, "♠J", 0.75,
                                                 finesse_struct=fs)
    cands_drop = [cand("♠A", 2.0, scores=[8] * 10),
                  cand("♠J", 1.0, scores=[8, 8, 8, 8, 8, 2, 2, 2, 2, 2]),
                  cand("♥Q", 1.5)]
    res_drop = mk_result(Card("♠", "A"), cands_drop)
    res_drop["full_output"]["finesse_probe_follow"] = {
        "♠": {"对象": 12, "西": {"♠A": 0.30, "♠J": 0.25},
              "东": {"♠A": 0.45, "♠J": 0.40}}}
    got_drop = ps_new()._finesse_commit_ratio_ok(st, res_drop, "♠J", 0.75,
                                                 finesse_struct=fs)
    ok = got_keep is True and got_drop is False
    return ok, (f"榜首♠A顶张（≥对象Q）：第一步 b_押注=0.30<0.50 不触发 → "
                f"第二步比值 vs top_alt♠A：0.8≥0.75 维持强制（got {got_keep}），"
                f"0.5<0.75 退让（got {got_drop}）")


def t24_reverse_route_duel():
    st = mk_state({"♦": "T42", "♠": "A2", "♥": "Q"}, {"♦": "AJ", "♠": "K5"})
    cands = [cand("♥Q", 0.49, scores=[8] * 5 + [6] * 5),
             cand("♠2", 0.45, scores=[6] * 10),
             cand("♦4", 0.45, scores=[8] * 5 + [6] * 5)]
    base = {"♦": [_probe_entry("♦", 12, "♦4", 0.30, direction="西", bucket=0.553),
                  _probe_entry("♦", 12, "♦J", 0.20, side="伙伴侧",
                               direction="东", bucket=0.405)]}
    res = mk_result(Card("♥", "Q"), cands)
    got = ps_new()._probe_lead_finesse_prefer(st, base, cands, 0.75, res)
    ok = (got is not None and got[0] == "♦4"
          and st.finesse_flow.get("♦") == 12)
    return ok, (f"反向路线对决（v2.13 全样本分子）：押西0.553>押东0.405 "
                f"→ 淘汰押东派（过手♠2）；♦4 全样本0.5 ≥ 0.85×榜首0.5 过闸"
                f"，南直飞♦4（got {got}, flow={st.finesse_flow}）")


def t25_local_bucket_molecule():
    """v2.13 门控分子改全样本做成率（用户定调）：能否启动视**全样本**比值，
    押桶成只用于启动后的路线排序。高分动作（全样本0.9=榜首1.0 的0.9倍）过闸；
    对照：全样本 low（0）但押桶成假高0.8 的动作被拒。"""
    st = mk_state({"♣": "A2", "♥": "Q"}, {"♣": "43"})
    cands = [cand("♥Q", 1.0, scores=[8] * 10),
             cand("♣2", 0.9, scores=[8] * 9 + [6])]
    base = {"♣": [_probe_entry("♣", 13, "♣2", 0.3, direction="西", bucket=0.8)]}
    res = mk_result(Card("♥", "Q"), cands)
    got = ps_new()._probe_lead_finesse_prefer(st, base, cands, 0.75, res)
    ok = (got is not None and got[0] == "♣2"
          and st.finesse_flow.get("♣") == 13)
    # 对照：全样本 low（0）但押桶成仍 0.8 → 退让尊重引擎（独立 state）
    st_bad = mk_state({"♣": "A2", "♥": "Q"}, {"♣": "43"})
    cands_bad = [cand("♥Q", 1.0, scores=[8] * 10),
                 cand("♣2", 0.5, scores=[6] * 10)]
    res_bad = mk_result(Card("♥", "Q"), cands_bad)
    got_bad = ps_new()._probe_lead_finesse_prefer(st_bad, base, cands_bad, 0.75, res_bad)
    ok = ok and got_bad is None and not st_bad.finesse_flow
    return ok, (f"门控分子=全样本：♣2 全样本0.9≥0.85×榜首1.0 过闸启动；"
                f"对照全样本0（押桶成假高0.8）被拒（got高分={got}, "
                f"got对照={got_bad}）")


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


def t26_follow_6nt_dead_ratio_keeps():
    st = mk_state({"♦": "AJ2", "♠": "Q32"}, {"♦": "43"})
    ps_new()._register_finesse_flow(st, "♦", 12, {"方向": "西"})
    reg_ok = (st.finesse_flow.get("♦") == 12
              and (getattr(st, "finesse_flow_extra", {}).get("♦") or {}).get("方向") == "西")
    cands = [cand("♦A", 0.40, scores=[7] * 10), cand("♦J", 0.32, scores=[6] * 10),
            cand("♠Q", 0.2, scores=[4] * 10)]
    res = _mk_follow_result(cands, {"♦A": 0.0, "♦J": 0.353}, east_bucket={"♦A": 0.7, "♦J": 0.6})
    got = ps_new()._finesse_commit_ratio_ok(st, res, "♦J", 0.75,
                                            finesse_struct={"♦": {"对象": 12}})
    ok = reg_ok and got is True
    return ok, (f"6NT型（押西桶拔A成0不飞即死）：b_押注=0<0.50 → 退让判据"
                f"不触发，落比值兜底 0.32/0.40=0.80≥0.75 保留强制♦J"
                f"（登记方向={reg_ok}, got {got}, 期望 True）")


def t27_follow_tier_defer_b26():
    st = _mk_follow_state()
    cands = [cand("♦A", 0.542, scores=[6] * 10), cand("♦Q", 1.0, scores=[5] * 10)]
    res = _mk_follow_result(cands, {"♦A": 0.542, "♦Q": 1.0}, east_bucket={"♦A": 0.45, "♦Q": 0.9})
    got = ps_new()._finesse_commit_ratio_ok(st, res, "♦Q", 0.75,
                                            finesse_struct={"♦": {"对象": 12}})
    return got is False, (f"B26型：押西桶榜首♦A成0.542≥0.50 且≥非押注桶0.45"
                          f"（定约不依赖飞牌）→ 退让引擎♦A（got {got}, 期望 False）")


def t28_follow_gray_zone_v193():
    st = _mk_follow_state()
    fs = {"♦": {"对象": 12}}
    cands_keep = [cand("♦A", 0.35), cand("♦J", 0.30)]
    res_keep = _mk_follow_result(cands_keep, {"♦A": 0.2, "♦J": 0.25},
                                 east_bucket={"♦A": 0.45, "♦J": 0.40})
    got_keep = ps_new()._finesse_commit_ratio_ok(st, res_keep, "♦J", 0.75,
                                                 finesse_struct=fs)
    cands_drop = [cand("♦A", 0.35), cand("♦J", 0.23)]
    res_drop = _mk_follow_result(cands_drop, {"♦A": 0.2, "♦J": 0.25},
                                 east_bucket={"♦A": 0.45, "♦J": 0.40})
    got_drop = ps_new()._finesse_commit_ratio_ok(st, res_drop, "♦J", 0.75,
                                                 finesse_struct=fs)
    ok = got_keep is True and got_drop is False
    return ok, (f"灰色区（b=0.2<0.50 退让判据不触发）走 v1.93 比值："
                f"0.857≥0.75 维持强制（got {got_keep}），"
                f"0.657<0.75 退让（got {got_drop}）")


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


def t32_follow_severe_bucket_top1_is_forced():
    st = mk_state({"♠": "AT98", "♥": "Q32"}, {"♠": "43", "♥": "J54"})
    ps_new()._register_finesse_flow(st, "♠", 13, {"方向": "东", "废弃对象": ["Q"]})
    eq = [6] * 10
    cands = [cand("♠8", 0.656, scores=eq), cand("♠T", 0.656, scores=eq),
             cand("♠9", 0.656, scores=eq), cand("♠A", 0.641, scores=[7] * 10)]
    res = mk_result(Card("♠", "A"), cands)
    res["full_output"]["finesse_probe_follow"] = {
        "♠": {"对象": 13,
              "东": {"♠A": 0.745, "♠8": 0.91, "♠T": 0.91},
              "东·全中": {"♠A": 0.0, "♠8": 0.353},
              "西·全中": {"♠A": 0.6, "♠8": 0.7}}}
    got = ps_new()._finesse_commit_ratio_ok(st, res, "♠8", 0.75,
                                            finesse_struct={"♠": {"对象": 13}})
    return got is True, (f"双飞KQ同东：全中桶♠A成0（Q干扰剔除）b_押注<0.50 → "
                         f"退让判据不触发，比值兜底 ♠8/♠T=1.0≥0.75 → 强制♠8"
                         f"（榜首即强制牌，实际仍出♠8；旧口径普通桶top_alt=♠T"
                         f"成0.91误判退让（got {got}, 期望 True））")


def t33_follow_severe_missing_falls_back():
    st = mk_state({"♠": "AT98", "♥": "Q32"}, {"♠": "43", "♥": "J54"})
    ps_new()._register_finesse_flow(st, "♠", 13, {"方向": "东", "废弃对象": ["Q"]})
    eq = [6] * 10
    cands = [cand("♠8", 0.6, scores=eq), cand("♠A", 0.542, scores=[7] * 10)]
    res = mk_result(Card("♠", "A"), cands)
    res["full_output"]["finesse_probe_follow"] = {
        "♠": {"对象": 13, "东": {"♠A": 0.542, "♠8": 1.0},
              "西": {"♠A": 0.45, "♠8": 0.9}}}
    got = ps_new()._finesse_commit_ratio_ok(st, res, "♠8", 0.75,
                                            finesse_struct={"♠": {"对象": 13}})
    return got is False, (f"Q异侧（K东Q西）：全中桶空落回普通东桶，"
                          f"♠A成0.542≥0.50 且≥非押注西桶0.45 → 退让引擎"
                          f"（got {got}, 期望 False）")


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
    ok = (list((same.get("♠") or {}).keys()) == ["对象", "东·全中"]
          and same["♠"]["东·全中"].get("♠A") == [10]
          and same["♠"]["东·全中"].get("♠8") == [11]
          and list((opp.get("♠") or {}).keys()) == ["对象", "东"]
          and list((solo.get("♠") or {}).keys()) == ["对象", "东"])
    fin = _finalize_finesse_probe_follow(same, 11)
    ok = ok and fin.get("♠", {}).get("东·全中") == {"♠A": 0.0, "♠8": 1.0}
    return ok, (f"全中子桶键判定：KQ同东记'东·全中'、Q异侧记'东'、"
                f"单飞无废弃对象记'东'；finalize输出全中成率"
                f"（same={same.get('♠')}, fin={fin.get('♠')}）")


def t35_final_select_bucket_rank():
    st = mk_state({"♣": "A2", "♦": "QJ2", "♥": "Q"}, {"♣": "43"})
    cands = [cand("♥Q", 0.5, scores=[8] * 10),
             cand("♦2", 0.85, scores=[8] * 8 + [6] * 2),
             cand("♦J", 0.95, scores=[8] * 9 + [6])]
    base = {"♦": [_probe_entry("♦", 13, "♦2", 0.9, direction="西", bucket=0.75),
                  _probe_entry("♦", 13, "♦J", 0.9, direction="西", bucket=0.85)]}
    res = mk_result(Card("♥", "Q"), cands)
    got = ps_new()._probe_lead_finesse_prefer(st, base, cands, 0.75, res)
    ok = (got is not None and got[0] == "♦J"
          and st.finesse_flow.get("♦") == 13)
    return ok, (f"终选押桶成排序（v2.13 全样本门控）：♦J 押桶0.85>♦2 的0.75 胜出，"
                f"且 ♦J 全样本0.9≥0.85×榜首1.0 过闸（♦2 全样本0.8<0.85 顺延被拒；"
                f"got {got}, flow={st.finesse_flow}）")


def t36_engine_already_leading_finesse_register():
    """早退分支已删（v2.00 简化）：引擎 top1 恰为本侧引牌时同样落入全局
    押桶成榜首决策——榜首（♦Q）过门控即登记，与"引擎在飞"旧分支同结果。"""
    st = mk_state({"♦": "Q32", "♥": "Q5"}, {"♦": "AJ6", "♥": "J4"})
    cands = [cand("♦Q", 0.4, scores=[6] * 10), cand("♥Q", 0.5, scores=[7] * 5 + [9] * 5)]
    res = mk_result(Card("♦", "Q"), cands)
    res["full_output"]["finesse_probe"] = {
        "♦": {"对象": "K", "Δ": 0.5, "引牌": "♦Q", "方向": "东", "押桶成": 0.9,
              "全": [{"对象": "K", "Δ": 0.5, "引牌": "♦Q", "方向": "东",
                      "押桶成": 0.9}]}}
    out = ps_new()._finesse_lead(st, res, 0.75)
    fo = out.get("full_output") or {}
    ws = fo.get("窗口期启动") or {}
    ok = (str(out["card"]) == "♦Q"
          and st.finesse_flow.get("♦") == 13
          and "押桶成" in (ws.get("说明") or "")
          and ws.get("花色") == "♦")
    return ok, (f"引擎已在飞牌花色（非稳成）：全局押桶成榜首保留引擎引牌+登记"
                f"（card={out['card']}, flow={st.finesse_flow}, "
                f"窗口期启动={ws.get('说明')}）")


def t37_global_top_bucket_wins():
    """v2.13 简化（全样本门控）：动作按押桶成排序逐动作过全样本门控。
    两花色各有结构，榜首 ♦J（押桶0.85，全样本0.9≥0.85×榜首1.0）过闸登记，
    ♣2（押桶0.80）顺延未及，Δ 只当门票不参与裁决。"""
    st = mk_state({"♣": "A2", "♦": "QJ2", "♥": "Q"}, {"♣": "43", "♦": "75"})
    cands = [cand("♥Q", 0.5, scores=[8] * 10),
             cand("♦J", 0.95, scores=[8] * 9 + [6]), cand("♣2", 0.90, scores=[8] * 9 + [6])]
    base = {"♦": [_probe_entry("♦", 13, "♦J", 0.2, direction="西", bucket=0.85)],
            "♣": [_probe_entry("♣", 13, "♣2", 0.9, direction="西", bucket=0.80)]}
    res = mk_result(Card("♥", "Q"), cands)
    got = ps_new()._probe_lead_finesse_prefer(st, base, cands, 0.75, res)
    ok = (got is not None and got[0] == "♦J"
          and st.finesse_flow.get("♦") == 13 and "♣" not in st.finesse_flow)
    return ok, (f"全局押桶成排序（v2.13 全样本门控）：♦J押桶0.85胜过Δ0.9的♣2"
                f"（押桶0.80）→ ♦J 全样本0.9 过闸登记♦（got {got}, flow={st.finesse_flow}）")


def t38_lead_full_hit_bucket():
    """领出端全中桶（押注桶统一口径，"严峻"名废弃）：被飞对象都在押注方向
    （=领出者下家）记单键"全中"。南领出（下家西=押注方向）；K9 都在西 →
    K 记"西"+"全中"；东侧无对象不记东。"""
    st = mk_state({"♠": "A", "♦": "J32", "♥": "Q"}, {"♠": "K", "♦": "AQ654", "♥": "J"})
    st.hands["东"] = mk_hand({"♠": "2", "♦": "87", "♥": "2"})
    st.hands["西"] = mk_hand({"♠": "3", "♦": "K9", "♥": "3"})
    st.current_player = "南"  # 下家=西（押注方向）
    score_map = {("♦", "J"): 8, ("♦", "3"): 8, ("♦", "2"): 5, ("♠", "A"): 7}
    playable = [Card("♦", "J"), Card("♦", "3"), Card("♦", "2"), Card("♠", "A")]
    probe = {}
    _accumulate_finesse_probe(score_map, playable, st, st.hands, probe, 12, True)
    k_keys = list((probe.get("♦") or {}).get("K", {}).keys())
    nine_keys = list((probe.get("♦") or {}).get("9", {}).keys())
    ok = "西" in k_keys and "全中" in k_keys and "东" not in k_keys
    debug = f"K 子桶={k_keys}, 9 子桶={nine_keys}"
    return ok, f"K9都在西（下家=押注方向）→ K 记西+全中（{debug}）"


def t39_full_hit_bucket_passes_to_finalize():
    """押注桶统一口径（v2.02，"严峻"名废弃）：全中=被飞对象都在押注方向
    （=领出下家西，几何）。K 普通西桶 0.70（K 在西所有世界）/全中桶 0.40
    （K9 都在西）——合并后 ♦J 押桶成读全中 0.40；全中桶无数据/单飞 →
    回退普通押桶成。"""
    def bucket(rate, n=20):
        return [10] * int(rate * n) + [9] * (n - int(rate * n))
    probe = {"♦": {
        "K": {"东": {"J": bucket(0.30)}, "西": {"J": bucket(0.70)},
              "全中": {"J": bucket(0.40)}},
        "9": {"东": {"J": bucket(0.10)}, "西": {"J": bucket(0.35)},
              "全中": {"J": bucket(0.40)}},
    }}
    out = _finalize_finesse_probe(probe, 10)
    info = out.get("♦") or {}
    all_e = info.get("全") or []
    ok = (info.get("对象") == "K" and len(all_e) == 1
          and all_e[0].get("押桶成") == 0.4
          and all_e[0].get("废弃对象") == ["9"])
    fallback = _finalize_finesse_probe({"♦": {"K": probe["♦"]["K"]}}, 10)
    f_e = ((fallback.get("♦") or {}).get("全") or [])[0]
    ok = ok and f_e.get("押桶成") == 0.7  # 单飞无废弃对象 → 回退普通
    return ok, (f"K普通西0.70/全中0.40 → 合并后0.40"
                f"（got {all_e[0].get('押桶成') if all_e else None}）；"
                f"单飞回退普通0.7（got {f_e.get('押桶成')}）")


def t40_combo_big_lead_on_saturated():
    """双飞组合·本侧·较大被飞对象（K）未现 → 较大领出牌优先（♦J）。

    复现实局：双飞 K/9 对象、三候选引牌 ♦3/♦J/♦2 的全中桶押桶成全部饱和 1.0，
    blended 亦无法分层。v2.03 定调：押桶成平局之后，偏好"领出牌 牌点
    > 较小飞牌对象"（min(对象K=13, 废弃9) = 9；♦J=11 > 9）的较大牌，即 ♦J。
    v2.13：三引牌全样本均 0.9 ≥ 0.85×榜首0.6，全过闸后仍按押桶排序取 ♦J。
    """
    st = mk_state({"♠": "A", "♥": "Q", "♦": "J32", "♣": "K"},
                  {"♠": "2", "♣": "A"})
    cands = [cand("♥Q", 0.5, scores=[8] * 6 + [2] * 4),
             cand("♦J", 0.9, scores=[8] * 9 + [6]),
             cand("♦3", 0.9, scores=[8] * 9 + [6]),
             cand("♦2", 0.9, scores=[8] * 9 + [6])]
    def combo(lead):
        e = _probe_entry("♦", 13, lead, 0.5, side="本侧", direction="西",
                         bucket=1.0)
        e["组合飞"] = True
        e["废弃对象"] = [9]
        return e
    base = {"♦": [combo("♦3"), combo("♦J"), combo("♦2")]}
    res = mk_result(Card("♥", "Q"), cands)
    got = ps_new()._probe_lead_finesse_prefer(st, base, cands, 0.75, res)
    ok = (got is not None and got[0] == "♦J"
          and st.finesse_flow.get("♦") == 13)
    return ok, (f"组合双飞全中饱和：三引牌押桶成均1.0平票 → 较大领出♦J"
                f"（got {str(got[0]) if got else None}, flow={st.finesse_flow}）")


def t41_follow_double_finesse_press_discard():
    """保Q废T双飞：废弃对象 T(10) 是敌方实牌，接应必须压过它 → 选♠J。
    回归：2026-09-25 前废弃对象被剔除出威胁，威胁算低导致错选 ♠9/♠8/♠3，
    被敌方 T 吃墩破坏飞 Q。K 已现身（北手牌），敌方剩余威胁=T。"""
    st = mk_state({"♠": "AJ983", "♥": "Q32"}, {"♠": "K4", "♥": "J54"},
                  current="南", trick_cards=[("北", Card("♠", "4"))])
    fs = {"♠": {"对象": 12, "废弃对象": ["T"]}}
    got = ps_new()._finesse_commit_check(st, fs)
    return got is not None and got[0] == "♠J", (
        f"保Q废T双飞：威胁=T(10) → 接应选♠J 压T（got {got}, 期望 ('♠J', ...)）")


CASES = [
    t08_respond_defender_lead,
    t10_exit_after_cash,
    t11_top1_make_semantics,
    t14_commit_ratio_keeps_flyer_not_in_cands,
    t15_commit_ratio_diff_suit_keeps,
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
    t26_follow_6nt_dead_ratio_keeps,
    t27_follow_tier_defer_b26,
    t28_follow_gray_zone_v193,
    t29_follow_data_missing_fallback,
    t30_combo_merge_strong_signal,
    t31_combo_confirm_and_continuation,
    t32_follow_severe_bucket_top1_is_forced,
    t33_follow_severe_missing_falls_back,
    t34_accumulate_follow_severe_key,
    t35_final_select_bucket_rank,
    t36_engine_already_leading_finesse_register,
    t37_global_top_bucket_wins,
    t38_lead_full_hit_bucket,
    t39_full_hit_bucket_passes_to_finalize,
    t40_combo_big_lead_on_saturated,
    t41_follow_double_finesse_press_discard,
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
