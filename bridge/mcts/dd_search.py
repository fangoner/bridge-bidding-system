"""纯蒙特卡洛 + 双明手评估搜索 (Phase 0b: DirectDDS)。

均匀采样未知手牌，批量 DDS 求解候选出牌的期望赢墩。
"""

import itertools
import math
import os
import time
from typing import Dict, List, Optional

from config import BASE_DIR
import config as _dd_config
from bridge.play_types import Card, PlayState, PlayPhase, POSITION_ORDER, PARTNERS
from bridge.mcts.state_utils import (
    get_current_trick_state,
)
from bridge.mcts.sampler import DealSampler, ALL_CARDS
from bridge.mcts.belief import collect_voids

_DEBUG_LOG = os.path.join(BASE_DIR, "dd_debug.log")

RANK_ORDER = {"A": 14, "K": 13, "Q": 12, "J": 11, "T": 10,
              "9": 9, "8": 8, "7": 7, "6": 6, "5": 5, "4": 4, "3": 3, "2": 2}


def _card_rank_val(card_str: str) -> int:
    """从牌张字符串（如 '♦2'）提取 rank 数值，用于平局时小牌优先排序。"""
    if not card_str:
        return 0
    return RANK_ORDER.get(card_str[-1], 0)


def _compare_candidates(a_val, a_scores, a_rank_val, b_val, b_scores, b_rank_val, is_declarer_side):
    """比较两个候选牌，完全交给概率决定。

    a_val, b_val: 用于决策方向的值（如 blended 或 avg）
    a_scores, b_scores: 保留用作扩展（当前不参与决定）

    返回: 1 if a 优于 b, -1 if b 优于 a, 0 if 等价。
    决胜规则（庄家方取高，防守方取低）：
    - 完全按 val 方向决定，不做小牌优先保留大牌结构
    """
    diff = a_val - b_val
    if is_declarer_side:
        if diff > 0:
            return 1
        if diff < 0:
            return -1
    else:
        if diff < 0:
            return 1
        if diff > 0:
            return -1
    return 0


# ── 计分制决策辅助：把各 world 的庄家方总赢墩换算为决策值 ──
# 约定：所有决策值均从"庄家方越优数值越高"的视角计算，_compare_candidates 按 is_declarer_side 取方向。
_IMP_TABLE = [0, 20, 50, 80, 130, 200, 300, 500, 750, 1000, 1300, 1600, 2000, 2400,
              3000, 3600, 4200, 4900, 5900, 7000, 8000, 9000, 10000, 11000, 12000]


def _raw_to_imp(raw):
    sign = 1 if raw >= 0 else -1
    a = abs(raw)
    k = 0
    for kk in range(len(_IMP_TABLE) - 1, -1, -1):
        if a >= _IMP_TABLE[kk]:
            k = kk
            break
    return sign * k


def _doubled_down_total(down, vul_decl):
    total = 0
    for i in range(1, down + 1):
        total += (100 + 200 * (i - 1)) if not vul_decl else (200 + 300 * (i - 1))
    return total


def _declarer_side_vulnerable(declarer, vul):
    if not vul or vul == "NV":
        return False
    if vul == "All":
        return True
    if vul == "NS":
        return declarer in ("北", "南")
    if vul == "EW":
        return declarer in ("东", "西")
    return False


def _contract_score(decl_total, contract, vul_decl):
    """庄家方取得 decl_total 墩的原始分（正=庄家得分，负=庄家宕分）。"""
    needed = contract.tricks_needed
    suit = contract.suit
    if suit == "NT":
        base = 40 + 30 * (contract.level - 1)
        trick_val = 30
    elif suit in ("♠", "♥"):
        base = 30 * contract.level
        trick_val = 30
    else:
        base = 20 * contract.level
        trick_val = 20
    if decl_total >= needed:
        overtricks = decl_total - needed
        score = base
        if contract.redoubled:
            score += overtricks * (400 if vul_decl else 200)
        elif contract.doubled:
            score += overtricks * (200 if vul_decl else 100)
        else:
            score += overtricks * trick_val
        if base >= 100:
            score += 500 if vul_decl else 300
        else:
            score += 50
        if contract.level == 6:
            score += 750 if vul_decl else 500
        elif contract.level == 7:
            score += 1500 if vul_decl else 1000
        if contract.redoubled:
            score += 100
        elif contract.doubled:
            score += 50
    else:
        down = needed - decl_total
        if contract.redoubled:
            score = -2 * _doubled_down_total(down, vul_decl)
        elif contract.doubled:
            score = -_doubled_down_total(down, vul_decl)
        else:
            score = -(50 + 50 * vul_decl) * down
    return score


def _expected_imp_value(scores, contract, vul_decl):
    if not scores:
        return 0.0
    return sum(_raw_to_imp(_contract_score(t, contract, vul_decl)) for t in scores) / len(scores)


def _make_rate_value(scores, tricks_needed):
    if not scores:
        return 0.0
    return sum(1 for t in scores if t >= tricks_needed) / len(scores)


def _subset_metrics(vals, contract, vul_decl, mode, is_declarer_side):
    """子集样本统计：赢墩均值 / IMP / 做成率 + 方向归一的决策值（排序/条宽用）。

    vals: 该子集（全赢/临界/全输/全部）内该候选的庄家方总赢墩列表。
    val 越大越优（防守方视角取负），前端直接降序排序。
    """
    n = len(vals)
    if n == 0:
        return {"n": 0, "tricks": None, "imp": None, "rate": None, "val": None,
                "mn": None, "mx": None}
    avg = sum(vals) / n
    imp = _expected_imp_value(vals, contract, vul_decl)
    rate = _make_rate_value(vals, contract.tricks_needed)
    raw = {"imp": imp, "make_rate": rate, "avg_tricks": avg}.get(mode, avg)
    val = raw if is_declarer_side else -raw
    return {"n": n, "tricks": round(avg, 2), "imp": round(imp, 3),
            "rate": round(rate, 3), "val": round(val, 3),
            "mn": min(vals), "mx": max(vals)}


def _has_duplicates(hands: Dict[str, List[Card]]) -> bool:
    """检测采样手牌中是否存在同一张牌出现在多个位置的情况。"""
    seen = set()
    for pos, cards in hands.items():
        for c in cards:
            key = (c.suit, c.rank)
            if key in seen:
                return True
            seen.add(key)
    return False

# Phase 0b: DirectDDS — ctypes 直调 DDS C 库（dds.dll 随 endplay 包分发）
from bridge.mcts.direct_dds import solve_all_boards_raw, is_dds_available

# 兼容导出：play_service 和 alpha_mu 依赖此标志判断 DDS 是否可用
# P0-6 修复：真实探测（endplay 不在 requirements.txt，缺失时不能再硬编码 True）
ENDPLAY_AVAILABLE = is_dds_available()


# Phase 0b fix: DDS suit/rank maps with equals bitmask parsing
_DDS_SUIT = {0: '♠', 1: '♥', 2: '♦', 3: '♣'}
_DDS_RANK = {14: 'A', 13: 'K', 12: 'Q', 11: 'J', 10: 'T', 9: '9',
              8: '8', 7: '7', 6: '6', 5: '5', 4: '4', 3: '3', 2: '2'}
def _dds_result_to_score_map(solved, exclude_cards=None):
    """DDS 结果 → {(suit, rank): score}，含 equals bitmask 展开。

    DDS equals bitmask: 某位=1 表示该 rank 的牌与结果中的牌等效。
    例如 ♠A 得分=5, equals bit 含 ♠K → ♠K 也得 5。
    """
    score_map = {}
    exclude = exclude_cards or set()
    for suit_id, rank_bit, equals, score in solved:
        s = _DDS_SUIT.get(suit_id)
        if not s:
            continue
        # 主牌
        r = _DDS_RANK.get(rank_bit)
        if r and (s, r) not in exclude:
            score_map[(s, r)] = score
        # equals 展开
        for rb in range(2, 15):
            if equals & (1 << rb):
                r2 = _DDS_RANK.get(rb)
                if r2 and (s, r2) not in exclude:
                    score_map[(s, r2)] = score
    return score_map


# 类别 → 过滤统计短键（与 eval_stats / 展示代码保持一致）
_dropped_keys = {"sure_win": "dropped_win", "sure_lose": "dropped_lose", "critical": "dropped_crit"}


def _accumulate_world_totals(score_map, playable, state, curplayer_is_declarer,
                             remaining_tricks, weight, card_scores, stats=None):
    """累计一个世界的各候选总分到 card_scores，返回是否保留（True=保留）。

    每世界按"所有候选出牌相对所需墩"分三类：全赢/全输/临界。
    按 config 的 DD_KEEP_* 三开关决定该类别是否参与评分（默认全保留）；
    取消某类别=把该类世界排除出期望聚合。stats 统计各类别计数。
    """
    decl_tricks = state.declarer_tricks
    tricks_needed = state.contract.tricks_needed
    totals = []
    for card in playable:
        key = (card.suit, card.rank)
        target_tricks = score_map.get(key, 0)
        if curplayer_is_declarer:
            decl_side_tricks = target_tricks
        else:
            decl_side_tricks = remaining_tricks - target_tricks
        totals.append(decl_tricks + decl_side_tricks)
    all_win = all(t >= tricks_needed for t in totals)
    all_lose = all(t < tricks_needed for t in totals)
    if all_win:
        cls = "sure_win"
    elif all_lose:
        cls = "sure_lose"
    else:
        cls = "critical"
    if stats is not None:
        stats[cls] += 1
    keep = {
        "sure_win": _dd_config.DD_KEEP_SURE_WIN,
        "critical": _dd_config.DD_KEEP_CRITICAL,
        "sure_lose": _dd_config.DD_KEEP_SURE_LOSE,
    }.get(cls, True)
    if not keep:
        if stats is not None:
            stats[_dropped_keys.get(cls, "dropped_" + cls)] += 1
        return False
    _bucket = {"sure_win": "win", "critical": "crit", "sure_lose": "lose"}[cls]
    for total, card in zip(totals, playable):
        card_stats = card_scores[str(card)]
        card_stats["weighted_sum"] += total * weight
        card_stats["total_weight"] += weight
        card_stats["scores"].append(total)
        card_stats["scores_" + _bucket].append(total)
        card_stats["mn"] = min(card_stats["mn"], total)
        card_stats["mx"] = max(card_stats["mx"], total)
    if stats is not None:
        stats["kept"] += 1
    return True


# ── 飞牌后果敏感性探针（分桶统计，零额外 DDS）────────────────────────
# 复用 search() 现有采样世界：每个世界已知四家手牌，因此对每个"缺失大牌
# M"（庄家+明手+已打出未现的 A/K/Q/J/T/9/8），可确定 M 落在东家还是西家。
# 按此分桶累计"候选出牌在该花色"的整手赢墩均值的桶间差 Δ；
# 探针监控窗口（2026-09-22 用户定调）：2 张滑动窗口，AK 起步、出一个向下补一个，
# 逐次下移至 AKQJT98（最低 8），不一次性全包。任何花色统一滑动——残局阶段
# 才能识别飞 J/T/9/8 的低位间张结构（如 T7 对防家 95 → 飞 9）。
# 窗口 3→2 依据：A/K/Q 同时为对象的三飞局面在桥牌中基本不存在——A 缺时
# 通常有 K 对 A 飞（对象=A、G=K）；窗口 2 张天然覆盖"对象+间张"所需的
# 前两个缺失大牌，省约 1/3 探针分桶计算。
# 注意：A 缺失時也是有效对象（K 对 A 飞：obj=A=14 > G=K=13 > max_enemy），
# 窗口必须从 A 起步——绝不能从 K 起步跳过 A。
# 下限 8：9/8 仍有飞牌意义，7/6 及以下（7/6...）位置敏感假阳性风险高，不做。
_FINESSE_WINDOW_BASE = ["A", "K", "Q", "J", "T", "9", "8"]


def _honor_missing_of_state(state):
    """返回 {花色: [缺失大牌...]}：庄家方现手未持有的监控窗口大牌。

    每个花色单独维护 2 张滑动窗口（持久于 state.finesse_windows，AK 起步）：
    每次检测探针时更新——先剔除"己方现手持有"的大牌（己方手里的大牌不是
    可飞对象，不占窗口名额，窗口自然下移），再取 AKQJT98 中该花色
    "未打出"的前 2 张（出一个向下补一个，下限 8，不全包），各花色互不干扰。
    对象 = 窗口内 ⇒ 未打出且不在我方手中 ⇒ 必在防守方（东/西），分桶依据。
    """
    known = set()
    for pos in (state.contract.declarer, state.dummy):
        if pos:
            for c in state.hands.get(pos, []):
                known.add((c.suit, c.rank))
    played = {}
    for t in state.tricks:
        for _, c in t.cards:
            if c:
                known.add((c.suit, c.rank))
                played.setdefault(c.suit, set()).add(c.rank)
    for _, c in state.current_trick.cards:
        if c:
            known.add((c.suit, c.rank))
            played.setdefault(c.suit, set()).add(c.rank)
    windows = getattr(state, "finesse_windows", None)
    if windows is None:
        windows = {}
        setattr(state, "finesse_windows", windows)
    missing = {}
    for suit in ("♠", "♥", "♦", "♣"):
        unplayed = [h for h in _FINESSE_WINDOW_BASE if h not in played.get(suit, set())]
        cands = [h for h in unplayed if (suit, h) not in known]
        window = cands[:2]
        windows[suit] = window
        if window:
            missing[suit] = window
    return missing


def _accumulate_finesse_probe(score_map, playable, state, hands,
                              probe, remaining_tricks, curplayer_is_declarer,
                              actual_turn=None):
    """把一个世界的候选赢墩按缺失大牌 M 的位置分桶累加进 probe。

    probe: {花色: {M: {"东": {card_str: [tricks]}, "西": {...}}}}。
    score_map: {(suit, rank_char): 该候选打出后出牌方阵营的剩余赢墩}。
    """
    try:
        missing = _honor_missing_of_state(state)
        if not missing:
            return
        east_has = {c.suit: set() for c in hands.get("东", [])}
        for c in hands.get("东", []):
            east_has.setdefault(c.suit, set()).add(c.rank)
        west_has = {c.suit: set() for c in hands.get("西", [])}
        for c in hands.get("西", []):
            west_has.setdefault(c.suit, set()).add(c.rank)
        decl_tricks = state.declarer_tricks
        # 押注方向（几何常数，用户定调）：引牌侧=引牌者的**下家**（南→西、
        # 北→东）。伙伴侧探测（过手）actual_turn=partner，用实际出牌人而非
        # state.current_player 推导。押注桶=被飞对象全部命中押注方向的世界
        # 做成率（单飞=对象在下家；双飞=两对象都在下家）。全中（原"严峻"
        # 名已废弃）以单键记入。
        _down = None
        _cp = actual_turn or getattr(state, "current_player", None)
        if _cp == "南":
            _down = "西"
        elif _cp == "北":
            _down = "东"
        for suit, miss_list in missing.items():
            side_of = {}
            for m in miss_list:
                if m in east_has.get(suit, set()):
                    side_of[m] = "东"
                elif m in west_has.get(suit, set()):
                    side_of[m] = "西"
                else:
                    continue  # 此世界 M 不在东西（不该发生，防御）
            if not side_of:
                continue
            # 全中世界（用户定义）：同花色**所有**被飞对象都在押注方向侧——飞牌
            # 前提成立、押注命中的世界，双飞等处所有决胜以该桶做成率为依据。
            full = bool(_down) and all(s == _down for s in side_of.values())
            for card in playable:
                if card.suit != suit:
                    continue
                target = score_map.get((card.suit, card.rank))
                if target is None:
                    continue
                total = decl_tricks + (target if curplayer_is_declarer
                                       else remaining_tricks - target)
                for m, side in side_of.items():
                    entry = probe.setdefault(suit, {}).setdefault(m, {})
                    bucket = entry.setdefault(side, {})
                    bucket.setdefault(str(card), []).append(total)
                    if full:
                        entry.setdefault("全中", {}).setdefault(
                            str(card), []).append(total)
    except Exception:
        pass


def _accumulate_finesse_probe_follow(score_map, playable, state, hands,
                                      probe_follow, remaining_tricks,
                                      curplayer_is_declarer):
    """跟牌接应探针（v1.96）：按本墩登记的飞牌对象位置分桶，
    累加全部候选牌的整手总墩到对应侧桶。

    probe_follow: {花色: {"对象": obj, "东": {card_str: [total]},
    "西": {card_str: [total]}, 可选 "{side}·全中": {card_str: [total]}}}。
    对象取自 state.finesse_flow（领出方启动飞牌时登记）；对象已现身的世界其
    不在东/西余手 → 该花色自然无数据。全部候选牌（不限飞牌花色）都累计
    ——消费端要读"引擎榜首替代牌"在押注方向桶内的做成率，榜首可能是
    任意花色的牌。
    押注桶统一口径（v2.02，"严峻"名废弃）：接应侧押注方向=接应者的**上家**
    （南领出北大时=西，几何常数），与引牌侧"领出者下家"是同一位置。双飞
    场景读 {side}·全中——废弃对象与登记对象同侧（即两对象都在押注方向）
    的世界；出A后双威胁同侧存活各拿一墩必宕的正是这些世界，Q 异侧（被迫
    跌落/被A顺吃）的意外收益不再稀释桶值。单飞无废弃对象零影响。
    """
    try:
        flow = getattr(state, "finesse_flow", None) or {}
        if not flow:
            return
        extra = getattr(state, "finesse_flow_extra", None) or {}
        east_ranks = set()
        for c in hands.get("东", []):
            east_ranks.add((c.suit, RANK_ORDER.get(c.rank)))
        west_ranks = set()
        for c in hands.get("西", []):
            west_ranks.add((c.suit, RANK_ORDER.get(c.rank)))
        decl_tricks = state.declarer_tricks
        for suit, obj in flow.items():
            if not isinstance(obj, int):
                continue
            if (suit, obj) in east_ranks:
                side = "东"
                side_ranks = east_ranks
            elif (suit, obj) in west_ranks:
                side = "西"
                side_ranks = west_ranks
            else:
                continue
            key = side
            e_suit = extra.get(suit)
            disc = e_suit.get("废弃对象") if isinstance(e_suit, dict) else None
            if disc:
                for d in disc:
                    dv = RANK_ORDER.get(d) if isinstance(d, str) else d
                    if dv is not None and (suit, dv) in side_ranks:
                        key = f"{side}·全中"
                        break
            entry = probe_follow.setdefault(suit, {"对象": obj})
            bucket = entry.setdefault(key, {})
            for card in playable:
                target = score_map.get((card.suit, card.rank))
                if target is None:
                    continue
                total = decl_tricks + (target if curplayer_is_declarer
                                       else remaining_tricks - target)
                bucket.setdefault(str(card), []).append(total)
    except Exception:
        pass


def _full_hit_rate(probe, suit, keep_m, discard, lead_str,
                   tricks_needed, fallback):
    """合并后押桶成优先读全中桶（押注桶子键，用户定调"严峻"名废弃）。

    押注桶（统一口径）：被飞对象全部命中押注方向的世界的做成率——引牌侧
    押注方向=领出者下家；单飞=对象在下家，双飞=登记与废弃两对象都在押注
    方向。_accumulate_finesse_probe 已把这类世界以单键 "全中" 记入每个
    对象；此处优先读该桶做成率。全中桶空（被飞对象不全在押注方向）或引牌
    无数据 → 回退普通押桶成。单飞（无废弃对象）直接回退。
    """
    if not discard or not lead_str:
        return fallback
    keep_sides = probe.get(suit, {}).get(keep_m, {}) if probe else {}
    totals = (keep_sides.get("全中") or {}).get(lead_str) or []
    if not totals:
        return fallback
    return round(sum(1 for t in totals if t >= tricks_needed) / len(totals), 3)


def _finalize_finesse_probe(probe, tricks_needed, lead_direction=None):
    """把分桶原始计数转成 play_service 可消费的结构。

    返回 {花色: {"对象": M, "Δ": 桶间做成率差, "方向": 押哪侧, "引牌": card_str,
    "全": [对象探针全列表]}}；"全" 按 Δ 降序列出该花色所有达标探针
    （K/Q/J 等缺失大牌各算一条），供界面完整展示"过手必要性"；
    play_service 只读 对象/Δ/引牌，兼容。
    Δ 口径（v1.92）：缺失大牌在东/西两桶的做成率差（整手总墩 ≥ tricks_needed
    的世界占比），替代赢墩均值差——赢墩口径信号上限 = 做成率差 × 生死线墩差，
    临界定约（满贯生死线常 1 墩）在赢墩口径必失明；Δ 取幅值（进池门票/
    结构排序沿用敏感性语义）。"方向"= 押注侧（v2.03 几何定调，用户确认）：
    押注方向=引牌者下家=当前位置下家（南→西、北→东，几何常数），不再是
    "哪侧桶做成率高押哪侧"（旧 v1.92 动态估计会让同花色多对象方向矛盾，
    如 K 押西/9 押东）；lead_direction 由 search() 按 current_player 推导。
    押桶成 = 押注侧桶做成率（单飞读几何侧半桶；双飞合并后读全中桶）。
    无有效分桶数据时返回 {}。
    """
    out = {}
    for suit, by_m in probe.items():
        entries = []
        raw = []
        for m, sides in by_m.items():
            east = sides.get("东") or {}
            west = sides.get("西") or {}
            for card_str in set(list(east.keys()) + list(west.keys())):
                ev = east.get(card_str) or []
                wv = west.get(card_str) or []
                if not ev or not wv:
                    # 单侧缺失（2026-09-22 用户定调）：对象只在约束世界集的一侧
                    # 出现（另一侧 n=0）。位置敏感度公式 Δ=|p东−p西| 缺一侧无法
                    # 直接求，退化为**该侧做成率**作 Δ（= |p·n − 0*0| / n 的
                    # 归一化形式，即这条飞牌线在约束世界集内的实际做成率）。
                    # 门票阈值 + 确认层（_probe_finesse_ok）+ 门控照常裁决。
                    one = ev or wv
                    p = sum(1 for t in one if t >= tricks_needed) / len(one)
                    direction = lead_direction or "西"
                    print(
                        f"[探针原始] {suit} 对象{m} 引牌{card_str} "
                        f"单侧缺失(n东{len(ev)}/n西{len(wv)})→Δ={round(p, 3)}(侧成) "
                        f"{'达标' if p >= _dd_config.FINESSE_PROBE_DELTA else '未达标'}")
                    raw_entry = {"对象": m, "Δ": round(p, 3), "引牌": card_str,
                                 "方向": direction, "押桶成": round(p, 3)}
                    raw.append(raw_entry)
                    if p >= _dd_config.FINESSE_PROBE_DELTA:
                        entries.append(dict(raw_entry))
                    continue
                east_rate = sum(1 for t in ev if t >= tricks_needed) / len(ev)
                west_rate = sum(1 for t in wv if t >= tricks_needed) / len(wv)
                signed = east_rate - west_rate
                delta = abs(signed)
                # 押注方向=几何下家（用户定调）；lead_direction 缺省（测试
                # 直调）时回退旧动态估计，实局由 search() 恒传几何下家。
                direction = lead_direction or ("东" if signed > 0 else "西")
                bet_rate = east_rate if direction == "东" else west_rate
                print(
                    f"[探针原始] {suit} 对象{m} 引牌{card_str} "
                    f"东成{round(east_rate, 3)}(n{len(ev)}) "
                    f"西成{round(west_rate, 3)}(n{len(wv)}) "
                    f"Δ{round(delta, 3)} 押{direction} "
                    f"{'达标' if delta >= _dd_config.FINESSE_PROBE_DELTA else '未达标'}")
                raw_entry = {"对象": m, "Δ": round(delta, 3), "引牌": card_str,
                             "方向": direction, "押桶成": round(bet_rate, 3)}
                raw.append(raw_entry)
                if delta >= _dd_config.FINESSE_PROBE_DELTA:
                    entries.append(dict(raw_entry))
        if not entries:
            # 双飞探测门（v1.90，用户定调）：桥牌不存在同花色"三飞"——组合
            # 飞语义就是双飞（一次引牌可同时飞两个缺失大牌，如 KQ/QJ/AQ 双飞）
            # 只取 Δ 最大的两个对象加和：多个互相独立的弱信号叠加≠真双墩敏感
            # （如 A/K/Q 三个 ~0.15 噪声堆出 0.44 的假结构），而 KQ 分家/同家
            # 加总显著才是双飞的真实敏感。保 rank 较高者（AQ 双飞保 A、KQ 保 K），
            # 另一个记废弃对象供 _probe_finesse_ok 威胁计算排除。
            per_obj = {}
            for e in raw:
                prev = per_obj.get(e["对象"])
                if prev is None or e["Δ"] > prev["Δ"]:
                    per_obj[e["对象"]] = e
            if len(per_obj) >= 2:
                top2 = sorted(per_obj.items(), key=lambda kv: -kv[1]["Δ"])[:2]
                total = top2[0][1]["Δ"] + top2[1][1]["Δ"]
                if total >= _dd_config.FINESSE_PROBE_DELTA:
                    keep_m = max([m for m, _ in top2],
                                 key=lambda r: RANK_ORDER.get(r, 0))
                    discard = sorted(m for m, _ in top2 if m != keep_m)
                    combined = round(total, 3)
                    print(f"[双飞探测] {suit} 对象[{('/'.join(m for m, _ in top2))}] "
                          f"Δ加和={combined}（单条均<阈值），保留较高对象"
                          f"{keep_m}，Δ改为{combined}，废弃{discard}")
                    # 保留 keep_m 的全部引牌候选（不折叠成单条）——终选按
                    # 押桶成主排序，同 Δ 引牌（如 ♦3/2/J）必须全体进池
                    entries = []
                    for e in [en for en in raw if en["对象"] == keep_m]:
                        ne = dict(e, Δ=combined, 组合飞=True, 废弃对象=discard)
                        ne["押桶成"] = _full_hit_rate(
                            probe, suit, keep_m, discard, ne.get("引牌"),
                            tricks_needed, ne.get("押桶成"))
                        entries.append(ne)
        elif len({e["对象"] for e in entries}) >= 2:
            # 双飞合并·强信号（v1.97，用户定调）：做成率口径下单对象 Δ 普遍
            # 达标（v1.92 改口径的后果），上方"单条均<阈值"弱信号门很少触发，
            # 双缺 KQ 局面以两条独立单飞形态出现——_probe_finesse_ok 单对象
            # 威胁判定中大对象压着小对象的 G 判定（判 K 时 Q 在敌，判 Q 时
            # K 在敌），必然双双判废。同花色 ≥2 达标对象同样合并：保大对象
            # 先飞（K），小对象记废弃（供威胁计算排除），Δ 取加和（双飞总
            # 敏感，排序压过普通单飞）；G 判定不过仍照常判废，不会误启动。
            orig_entries = list(entries)
            per_obj = {}
            for e in entries:
                prev = per_obj.get(e["对象"])
                if prev is None or e["Δ"] > prev["Δ"]:
                    per_obj[e["对象"]] = e
            top2 = sorted(per_obj.items(), key=lambda kv: -kv[1]["Δ"])[:2]
            # 单侧缺失对象 Δ=侧做成率（接近 1），加和与双侧差量纲混加可能 >1 ——
            # 门票/排序语义封顶 1.0
            total = round(min(top2[0][1]["Δ"] + top2[1][1]["Δ"], 1.0), 3)
            keep_m = max([m for m, _ in top2],
                         key=lambda r: RANK_ORDER.get(r, 0))
            discard = sorted(m for m, _ in top2 if m != keep_m)
            print(f"[双飞合并] {suit} 对象[{('/'.join(m for m, _ in top2))}] "
                  f"Δ加和={total}（单条均≥阈值），保留较高对象"
                  f"{keep_m}，Δ改为{total}，废弃{discard}")
            # 保留 keep_m 的全部达标引牌候选（不折叠成单条）——per_obj 只留
            # Δ 最大一条，同 Δ 引牌会被严格 > 砍掉（♦3/2/J Δ 全等仅剩 ♦3）；
            # 终选按押桶成主排序，全体引牌必须进池
            entries = []
            for e in [en for en in orig_entries if en["对象"] == keep_m]:
                ne = dict(e, Δ=total, 组合飞=True, 废弃对象=discard)
                ne["押桶成"] = _full_hit_rate(probe, suit, keep_m, discard,
                                                    ne.get("引牌"),
                                                    tricks_needed,
                                                    ne.get("押桶成"))
                entries.append(ne)
        if entries:
            # 终选口径打印：各引牌候选的押桶成（v2.02 押注桶统一口径——
            # 双飞合并后=全中桶做成率，普通单飞=押注方向半桶）
            dbg = "; ".join(f"{e['引牌']}押{e.get('押桶成')}"
                            f"({'组合' if e.get('组合飞') else '单'})"
                            for e in entries)
            print(f"[探针终选] {suit} {dbg}")
            entries.sort(key=lambda e: e["Δ"], reverse=True)
            best = entries[0]
            out[suit] = {
                "对象": best["对象"], "Δ": best["Δ"], "引牌": best["引牌"],
                "方向": best.get("方向"), "全": entries,
            }
    return out


def _finalize_finesse_probe_follow(probe_follow, tricks_needed):
    """跟牌接应探针汇总（v1.96）：把各侧桶原始总墩转成做成率。

    返回 {花色: {"对象": obj, "东": {牌: 成率}, "西": {牌: 成率},
    可选 "东·全中"/"西·全中": {牌: 成率}}}；两侧均无数据的花色剔除
    （对象已现身/登记被清的世界集）。全中子键（v2.02，原"严峻"名废弃）
    = 双飞废弃对象与登记对象同在押注方向（接应上家）的世界子集，
    消费端三层判据优先读取。
    """
    out = {}
    for suit, entry in probe_follow.items():
        finalized = {"对象": entry.get("对象")}
        for side in ("东", "西", "东·全中", "西·全中"):
            finalized[side] = {}
            for card_str, totals in (entry.get(side) or {}).items():
                if not totals:
                    continue
                rate = sum(1 for t in totals if t >= tricks_needed) / len(totals)
                finalized[side][card_str] = round(rate, 3)
        if any(finalized[s] for s in ("东", "西", "东·全中", "西·全中")):
            out[suit] = finalized
    return out


def _dd_eval_one_world(world, all_played, trick_cards, trick_leader,
                       playable, state, perspective, actual_turn, declarer, dummy,
                       trump, card_scores, weight, sample_idx, stats=None,
                       finesse_probe=None, finesse_probe_follow=None):
    """Phase 0b: DirectDDS 单世界求解，累加加权分到 card_scores。"""
    _DD_POS = {'北': 0, '东': 1, '南': 2, '西': 3}
    try:
        hands, t, first_p, tc = _build_dds_data(world, all_played, trick_cards,
                                                  trick_leader, perspective, actual_turn, trump)
        if hands is None:
            return
        solved_list = solve_all_boards_raw([(hands, t, first_p, tc)])
        if not solved_list or solved_list[0] is None:
            return
        solved = solved_list[0]
        score_map = _dds_result_to_score_map(solved)
        total_played = state.declarer_tricks + state.defender_tricks
        remaining_tricks = 13 - total_played
        cur_p = (_DD_POS.get(first_p, 0) + len(tc)) % 4
        curplayer_is_declarer = cur_p in (_DD_POS.get(declarer, 2), _DD_POS.get(dummy, 0))
        _accumulate_world_totals(score_map, playable, state, curplayer_is_declarer,
                                 remaining_tricks, weight, card_scores, stats)
        if finesse_probe is not None:
            _accumulate_finesse_probe(score_map, playable, state, hands,
                                      finesse_probe, remaining_tricks,
                                      curplayer_is_declarer, actual_turn)
        if finesse_probe_follow is not None:
            _accumulate_finesse_probe_follow(score_map, playable, state, hands,
                                             finesse_probe_follow,
                                             remaining_tricks,
                                             curplayer_is_declarer)
    except Exception:
        pass


def _build_dds_data(world, all_played, trick_cards, trick_leader,
                      perspective, actual_turn, trump):
    """从 world 构建 DirectDDS 输入数据。

    Phase 0b: 直接返回 (hands, trump, first_player, trick_cards)，
    无需 PBN/Deal 中间层。

    返回: (hands, trump, first, trick_cards) 或 (None, None, None, None)
    """
    # 深拷贝 world
    sampled = {pos: [Card(suit=c.suit, rank=c.rank) for c in hand]
               for pos, hand in world.items()}
    # 1. 移除所有已出牌（包括已完成墩和当前墩）
    #    注意：采样世界中的牌位置可能与实际出牌位置不同，
    #    所以需要从所有位置中查找并移除。
    all_played_set = set()
    for pos, card in all_played:
        all_played_set.add((card.suit, card.rank))
    for pos in list(sampled.keys()):
        sampled[pos] = [c for c in sampled[pos]
                        if (c.suit, c.rank) not in all_played_set]
    # 2. 检测重复牌
    if _has_duplicates(sampled):
        return None, None, None, None
    # 3. 不把当前墩牌加回手牌：DDS 通过 currentTrickSuit/Rank 知道已出牌，
    #    手牌中不应包含已出牌张。
    # 4. 确定 first player
    if trick_cards:
        first = trick_leader
    else:
        first = actual_turn
    return sampled, trump, first, trick_cards


def _solve_batch(samples, all_played, trick_cards, trick_leader,
                 playable, state, perspective, actual_turn, declarer, dummy,
                 trump, card_scores, time_limit, start_time, stats=None,
                 finesse_probe=None, finesse_probe_follow=None):
    """Phase 0b: DirectDDS 批量求解，ctypes 直调 DDS，无 PBN/Deal 转换。

    返回 (samples_done, solve_times_list, solve_total, solve_max)。
    """
    from bridge.mcts.direct_dds import MAXNOOFBOARDS, _POS_TO_PLAYER as DD_POS_TO_PLAYER
    import time as _time

    # 1. 构建 DirectDDS 原始数据
    dds_data = []  # [(hands, trump, first, trick_cards), ...]
    for world in samples:
        if _time.time() - start_time > time_limit:
            break
        hands, t, first, tc = _build_dds_data(world, all_played, trick_cards,
                                                trick_leader, perspective, actual_turn, trump)
        if hands is not None:
            dds_data.append((hands, t, first, tc))

    if not dds_data:
        return 0, [], 0.0, 0.0

    total_played = state.declarer_tricks + state.defender_tricks
    remaining_tricks = 13 - total_played
    solve_times = []
    solve_total = 0.0
    solve_max = 0.0
    samples_done = 0

    # 2. DDS position mapping (same as direct_dds._POS_TO_PLAYER: 北=0,东=1,南=2,西=3)
    _DD_POS = {'北': 0, '东': 1, '南': 2, '西': 3}

    # 3. 分批求解（每批 ≤ 200）
    for batch_start in range(0, len(dds_data), MAXNOOFBOARDS):
        if _time.time() - start_time > time_limit:
            break
        batch_end = min(batch_start + MAXNOOFBOARDS, len(dds_data))
        batch = dds_data[batch_start:batch_end]
        _t_batch = _time.time()
        solved_list = None
        try:
            solved_list = solve_all_boards_raw(batch)
        except Exception:
            solved_list = None
        _dt_batch = _time.time() - _t_batch
        solve_total += _dt_batch
        _per_deal = _dt_batch / max(len(batch), 1)
        if _per_deal > solve_max:
            solve_max = _per_deal
        if solved_list is not None:
            # 累加结果
            for i, solved in enumerate(solved_list):
                if solved is None:
                    continue
                _hands, _trump_str, first_p, _tc = batch[i]
                # score_map: {(suit, rank_char): side_tricks}
                score_map = _dds_result_to_score_map(solved)

                # curplayer: (first + len(trick_cards)) % 4
                cur_p = (_DD_POS.get(first_p, 0) + len(_tc)) % 4
                curplayer_is_declarer = cur_p in (_DD_POS.get(declarer, 2), _DD_POS.get(dummy, 0))

                _accumulate_world_totals(score_map, playable, state, curplayer_is_declarer,
                                                remaining_tricks, 1.0, card_scores, stats)
                if finesse_probe is not None:
                    _accumulate_finesse_probe(score_map, playable, state, _hands,
                                              finesse_probe, remaining_tricks,
                                              curplayer_is_declarer, actual_turn)
                if finesse_probe_follow is not None:
                    _accumulate_finesse_probe_follow(score_map, playable, state, _hands,
                                                     finesse_probe_follow,
                                                     remaining_tricks,
                                                     curplayer_is_declarer)
                samples_done += 1
                solve_times.append(_per_deal)
        else:
            with open(_DEBUG_LOG, "a", encoding="utf-8") as _f:
                _f.write(f"[BATCH_FAIL_DD] batch_start={batch_start} "
                         f"size={len(batch)}\n")
            # 降级到逐个求解
            for hands, t, first_p, tc in batch:
                if _time.time() - start_time > time_limit:
                    break
                _t_s = _time.time()
                try:
                    solved_list = solve_all_boards_raw([(hands, t, first_p, tc)])
                except Exception:
                    continue
                _dt_s = _time.time() - _t_s
                solve_total += _dt_s
                if _dt_s > solve_max:
                    solve_max = _dt_s
                if not solved_list or solved_list[0] is None:
                    continue
                solved = solved_list[0]
                score_map = _dds_result_to_score_map(solved)
                cur_p = (_DD_POS.get(first_p, 0) + len(tc)) % 4
                curplayer_is_declarer = cur_p in (_DD_POS.get(declarer, 2), _DD_POS.get(dummy, 0))
                _accumulate_world_totals(score_map, playable, state, curplayer_is_declarer,
                                                remaining_tricks, 1.0, card_scores, stats)
                if finesse_probe is not None:
                    _accumulate_finesse_probe(score_map, playable, state, hands,
                                              finesse_probe, remaining_tricks,
                                              curplayer_is_declarer, actual_turn)
                if finesse_probe_follow is not None:
                    _accumulate_finesse_probe_follow(score_map, playable, state, hands,
                                                     finesse_probe_follow,
                                                     remaining_tricks,
                                                     curplayer_is_declarer)
                samples_done += 1
                solve_times.append(_dt_s)

    return samples_done, solve_times, solve_total, solve_max


def _hand_violates_void(hands: Dict[str, List[Card]], voids: Dict[str, set]) -> bool:
    """手牌是否违反已知 void 硬事实（某位置某花色已垫过牌，不可能再有该花色）。"""
    for pos, hand in hands.items():
        s = voids.get(pos)
        if s and any(c.suit in s for c in hand):
            return True
    return False


class DDSearch:

    def __init__(self, sampler: DealSampler = None, num_samples: int = 100,
                 min_samples: int = 15, time_limit: float = 5.0,
                 endgame_card_threshold: int = 4, max_enumerations: int = 5000,
                 scoring_mode: Optional[str] = None):
        self.sampler = sampler or DealSampler()
        self.num_samples = num_samples
        self.min_samples = min_samples
        self.time_limit = time_limit
        self.endgame_card_threshold = endgame_card_threshold
        self.max_enumerations = max_enumerations
        self.last_worlds = None
        if scoring_mode is None:
            from config import DD_SCORING_MODE
            scoring_mode = DD_SCORING_MODE
        self.scoring_mode = scoring_mode

    def _decision_value(self, scores: List[int], state: PlayState):
        """按计分制返回决策值（从庄家方越优数值越高的视角）。
        imp/make_rate/avg_tricks 返回各自决策值；返回 None 表示走既有 avg/regret 逻辑。"""
        mode = self.scoring_mode
        if mode == "imp":
            vul_decl = _declarer_side_vulnerable(state.contract.declarer,
                                                 getattr(state, "vulnerability", "NV"))
            return _expected_imp_value(scores, state.contract, vul_decl)
        if mode == "make_rate":
            return _make_rate_value(scores, state.contract.tricks_needed)
        if mode == "avg_tricks":
            # 纯平均赢墩（MP 思路）：不混合 min，避免 maximin 的保守惩罚
            return sum(scores) / len(scores) if scores else 0.0
        return None

    def _fmt_score(self, s: dict) -> str:
        """按计分制格式化候选分数（search 与残局枚举共用同一输出口径）。"""
        mode = s.get("scoring_mode", "avg_tricks")
        if mode == "imp":
            return f"{s.get('scoring_val', 0):+.3f}IMP"
        elif mode == "make_rate":
            return f"{s.get('scoring_val', 0)*100:.1f}%"
        else:
            return f"{s['avg_tricks']}[{s['min_tricks']}-{s['max_tricks']}]"

    def _finalize_decision(self, card_scores, state, playable, is_declarer_side, elapsed):
        """选牌汇总与排序，search（采样）与残局枚举共用同一决策口径。

        card_scores: {str(card): {"weighted_sum", "total_weight", "scores", "mn", "mx"}}
        两种路径唯一区别是样本来源（随机采样 vs 穷举世界），
        计分制决策（_decision_value）、差值比较（_compare_candidates）、
        排序与输出格式（_fmt_score）完全一致。
        """
        obj_map = {str(c): c for c in playable}
        best_card = None
        best_blended = None
        best_scores = None
        best_rank_val = None
        child_stats = []
        blended_map = {}
        scores_map = {}
        _vul_decl = _declarer_side_vulnerable(
            state.contract.declarer, getattr(state, "vulnerability", "NV"))
        for card_str, stats in card_scores.items():
            scores = stats["scores"]
            w_sum = stats["weighted_sum"]
            w_total = stats["total_weight"]
            # 加权平均（纯约束模式下所有 weight=1.0，退化为普通平均）
            w_avg = w_sum / w_total if w_total > 0 else 0.0
            mn = stats["mn"] if stats["mn"] != float("inf") else 0
            mx = stats["mx"] if stats["mx"] != -float("inf") else 0
            child_stats.append({
                "card": card_str,
                "samples": len(scores),
                "avg_tricks": round(w_avg, 2),
                "min_tricks": mn,
                "max_tricks": mx,
                "scores": scores,
                "scoring_val": None,
                "scoring_mode": self.scoring_mode,
                "imp_val": round(_expected_imp_value(scores, state.contract, _vul_decl), 3),
                "make_rate_val": round(_make_rate_value(scores, state.contract.tricks_needed), 3),
                "subsets": {
                    sk: _subset_metrics(vals, state.contract, _vul_decl,
                                        self.scoring_mode, is_declarer_side)
                    for sk, vals in (
                        ("all", scores),
                        ("win", stats.get("scores_win") or []),
                        ("crit", stats.get("scores_crit") or []),
                        ("lose", stats.get("scores_lose") or []),
                    )
                },
            })

            rank_val = _card_rank_val(card_str)

            scoring_val = self._decision_value(scores, state)
            if scoring_val is not None:
                if self.scoring_mode == "make_rate":
                    # 成约率制（2026-09-13）：做成率主、超额赢墩 avg_tricks 决胜——
                    # ♣A 9墩 与 ♣5 10墩 同 100% 时，选赢墩多的候选（避免
                    # 平局任意排序选中浪费顶张的那个）。10000 权重远大于赢墩
                    # 幅度（≤13），做成率差 <0.001 时才由赢墩主宰（几乎平）。
                    blended = scoring_val * 10000.0 + w_avg
                else:
                    blended = scoring_val
                child_stats[-1]["scoring_val"] = round(scoring_val, 3)
            else:
                blended = w_avg

            blended_map[card_str] = blended
            scores_map[card_str] = scores

            # 配对差值检验：同 world 配对差值的样本标准差决定显著性阈值
            if best_card is None or _compare_candidates(blended, scores, rank_val, best_blended, best_scores, best_rank_val, is_declarer_side) > 0:
                best_card = obj_map[card_str]
                best_blended = blended
                best_scores = scores
                best_rank_val = rank_val

        from functools import cmp_to_key
        child_stats.sort(key=cmp_to_key(
            lambda a, b: -_compare_candidates(
                blended_map[a["card"]], scores_map[a["card"]], _card_rank_val(a["card"]),
                blended_map[b["card"]], scores_map[b["card"]], _card_rank_val(b["card"]),
                is_declarer_side
            )
        ))

        top_plays_str = ", ".join(
            f"{s['card']}({self._fmt_score(s)})"
            for s in child_stats[:5]
        )
        return {
            "best_card": best_card,
            "child_stats": child_stats,
            "top_plays_str": top_plays_str,
            "blended_map": blended_map,
            "scores_map": scores_map,
            "best_blended": best_blended,
            "best_scores": best_scores,
            "best_rank_val": best_rank_val,
        }

    def _solve_worlds(self, worlds, all_played, trick_cards, trick_leader,
                      playable, state, perspective, actual_turn, declarer, dummy,
                      trump, card_scores, eval_stats, finesse_probe,
                      start_time, mode_note="", finesse_probe_follow=None):
        """批量求解 + 串行降级 + 耗时统计，search（采样）与残局枚举共用。

        worlds 是两张路径的唯一区别：sample_n 的随机采样 vs 穷举世界。
        返回 (samples_done, solve_times, solve_total, solve_max)。
        """
        samples_done = 0
        _solve_total = 0.0
        _solve_max = 0.0
        _solve_count = 0
        _solve_times = []
        _batch_used = False
        time_limit = self.time_limit
        if worlds:
            _t_batch_total = time.time()
            _bd, _bt, _bs_tot, _bs_max = _solve_batch(
                worlds, all_played, trick_cards, trick_leader,
                playable, state, perspective, actual_turn, declarer, dummy,
                trump, card_scores, time_limit, start_time, eval_stats,
                finesse_probe=finesse_probe,
                finesse_probe_follow=finesse_probe_follow)
            if _bd > 0:
                _batch_used = True
                samples_done = _bd
                _solve_times = _bt
                _solve_total = _bs_tot
                _solve_max = _bs_max
                _solve_count = _bd
                with open(_DEBUG_LOG, "a", encoding="utf-8") as _f:
                    _f.write(f"[DD] 批量求解完成: {_bd}世界 batch_total={_bs_tot:.2f}s\n")
            else:
                # 批量失败：降级到串行（等权）
                with open(_DEBUG_LOG, "a", encoding="utf-8") as _f:
                    _f.write(f"[DD] 批量求解失败，降级到串行\n")
                for world in worlds:
                    if time.time() - start_time > time_limit:
                        break
                    samples_done += 1
                    _t_s0 = time.time()
                    _dd_eval_one_world(world, all_played, trick_cards, trick_leader,
                                       playable, state, perspective, actual_turn, declarer, dummy,
                                       trump, card_scores, 1.0, samples_done, eval_stats,
                                       finesse_probe=finesse_probe,
                                       finesse_probe_follow=finesse_probe_follow)
                    _dt_solve = time.time() - _t_s0
                    _solve_times.append(_dt_solve)
                    _solve_total += _dt_solve
                    _solve_count += 1
                    if _dt_solve > _solve_max:
                        _solve_max = _dt_solve
                    if _solve_count <= 3:
                        with open(_DEBUG_LOG, "a", encoding="utf-8") as _f:
                            _f.write(f"[DD]   sample#{_solve_count} solve={_dt_solve:.3f}s\n")
                    if _dt_solve > 0.1:
                        with open(_DEBUG_LOG, "a", encoding="utf-8") as _f:
                            _f.write(f"[DD_SLOW] sample#{_solve_count} solve={_dt_solve:.3f}s\n")
            # 输出耗时分布统计
            if _solve_times:
                _st_sorted = sorted(_solve_times)
                _n = len(_st_sorted)
                _p50 = _st_sorted[int(_n * 0.5)]
                _p90 = _st_sorted[int(_n * 0.9)]
                _p99 = _st_sorted[min(int(_n * 0.99), _n - 1)]
                _avg = sum(_st_sorted) / _n
                _mode = "BATCH" if _batch_used else "SERIAL"
                with open(_DEBUG_LOG, "a", encoding="utf-8") as _f:
                    _f.write(f"[DD_STATS] mode={_mode} n={_n} avg={_avg*1000:.1f}ms p50={_p50*1000:.1f}ms "
                             f"p90={_p90*1000:.1f}ms p99={_p99*1000:.1f}ms max={_solve_max*1000:.1f}ms "
                             f"total={_solve_total:.2f}s\n")
        elapsed = time.time() - start_time
        _solve_avg = (_solve_total / _solve_count) if _solve_count > 0 else 0.0
        print(f"[DD] 全量模式完成: {samples_done} 世界, {elapsed:.1f}s"
              f"{mode_note} solve_avg={_solve_avg:.3f}s solve_max={_solve_max:.3f}s "
              f"solve_total={_solve_total:.1f}s")
        with open(_DEBUG_LOG, "a", encoding="utf-8") as _f:
            _f.write(f"[DD] 完成: {samples_done}世界 {elapsed:.1f}s "
                     f"solve_avg={_solve_avg:.3f}s solve_max={_solve_max:.3f}s "
                     f"solve_total={_solve_total:.1f}s\n")
        return samples_done, _solve_times, _solve_total, _solve_max

    def _generate_worlds(self, state: PlayState, perspective: str,
                         remaining_tricks: int, num_samples: Optional[int] = None):
        """样本来源选择（唯一分叉）+ 独立计时（DD 与 αμ 共用）。

        残局（剩余墩≤endgame_card_threshold）优先穷举未知分布；枚举不可行
        （数量超限/一致性失败）或非残局落回均匀采样。生成阶段独立计时
        （gen_time），不计入求解 time_limit 预算。
        num_samples=None 时按剩余墩自适应（DD 用它）；传入具体值则用该值
        采样（αμ 用它——αμ 的世界数按牌数自适应，与 DD 样本数不同）。
        返回 (worlds, source, gen_time)：source 仅用于日志与展示，不参与
        后续求解/决策的任何分支。
        """
        gen_start = time.time()
        worlds = None
        source = "均匀采样"
        if remaining_tricks <= self.endgame_card_threshold:
            enum = self._enumerate_endgame_worlds(state, perspective)
            if enum is not None:
                worlds = enum
                source = "残局枚举"
        if worlds is None:
            if num_samples is None:
                ratio = max(0, remaining_tricks / 13)
                num_samples = int(self.min_samples + (self.num_samples - self.min_samples) * ratio)
                num_samples = max(self.min_samples, min(self.num_samples, num_samples))
            worlds = self.sampler.sample_n(num_samples, state, perspective)
        gen_time = time.time() - gen_start
        return worlds, source, gen_time

    def search(self, state: PlayState, perspective: str = None,
               actual_turn: str = None,
               preset_worlds: Optional[List] = None) -> dict:
        # perspective/actual_turn 可覆盖（顶张侧过手探测用队友侧视角，
        # 见 play_service._apply_lead_transfer）；默认取当前出牌方。
        # preset_worlds 非空时跳过采样/枚举直接复用（两侧探针统一样本，
        # 见 play_service._probe_partner_finesse_struct）。
        perspective = perspective or state.current_player
        actual_turn = actual_turn or state.current_player
        declarer = state.contract.declarer
        dummy = state.dummy
        # 明手不做决策：搜索视角改为庄家
        if perspective == dummy:
            perspective = declarer
        playable = state.get_playable_cards(actual_turn)

        if len(playable) == 1:
            self.last_worlds = None
            return {
                "card": playable[0],
                "reasoning": "唯一选择",
                "full_output": {"推荐出牌": str(playable[0])},
            }

        trump = state.contract.suit
        is_declarer_side = perspective in (declarer, dummy)

        # 残局判定：用剩余墩数（=每手牌数），与模式无关
        remaining_tricks = 13 - (state.declarer_tricks + state.defender_tricks)

        # 样本来源选择（唯一分叉）+ 独立计时：残局优先穷举未知分布，不可行/
        # 非残局落回均匀采样。生成耗时单独统计，不计入求解 time_limit 预算。
        # preset_worlds 非空时直接复用（伙伴侧探针与主搜索统一样本）。
        if preset_worlds is not None:
            worlds, source, gen_time = list(preset_worlds), "复用主搜索世界", 0.0
        else:
            worlds, source, gen_time = self._generate_worlds(
                state, perspective, remaining_tricks)
        self.last_worlds = worlds
        _has_constraints = bool(self.sampler.constraints)
        _constraint_count = len(self.sampler.constraints) if self.sampler.constraints else 0
        print(f"[DD] {source}: {len(worlds)} 样本, "
              f"gen={gen_time:.2f}s, "
              f"constraints={_has_constraints}({_constraint_count}), "
              f"remaining_tricks={remaining_tricks}")
        with open(_DEBUG_LOG, "a", encoding="utf-8") as _f:
            _f.write(f"[DD] trick={13-remaining_tricks+1} source={source} samples={len(worlds)} "
                     f"gen={gen_time:.2f}s "
                     f"constraints={_has_constraints}({_constraint_count}) "
                     f"remaining_tricks={remaining_tricks}\n")

        card_scores = {str(c): {"weighted_sum": 0.0, "total_weight": 0.0,
                          "scores": [], "scores_win": [], "scores_crit": [],
                          "scores_lose": [], "mn": float("inf"), "mx": -float("inf")}
               for c in playable}

        # 当前墩信息（补回手牌 + 写入 Deal 当前墩）
        trick_state = get_current_trick_state(state)
        trick_cards = trick_state["cards"]  # [(pos, Card), ...]
        trick_leader = trick_state.get("leader")

        # 收集所有已出牌（已完成墩 + 当前墩），按出牌顺序
        all_played = []
        for trick in state.tricks:
            all_played.extend(trick.cards)
        all_played.extend(trick_cards)

        # ── 求解与决策：此后采样/枚举共用同一份代码，无任何来源区分 ──
        # P1-4 修复：时间预算从求解开始计时（样本生成已独立计时，不再挤占预算）
        start_time = time.time()
        samples_done = 0
        eval_stats = {"kept": 0, "sure_win": 0, "critical": 0, "sure_lose": 0,
                      "dropped_win": 0, "dropped_crit": 0, "dropped_lose": 0}
        # 飞牌后果敏感性探针：按缺失大牌位置分桶，零额外 DDS。
        # 门控（2026-09-09 修正）：仅"本家正在领出"才探测——跟牌/垫牌时探针
        # 会因滑动窗口下移发明新对象（如飞Q时Q刚出，探针滑到"飞T"），把本应
        # 放小的接应误判成必须盖T。领出方为庄/明手才探测（对方领出不探测）。
        # DD 介入总开关（DD_INTERVENE_ENABLE=False）时探测一并关闭，输出空。
        _probe_ok = (not trick_cards) and (actual_turn in (declarer, dummy))
        finesse_probe = {} if (_probe_ok and _dd_config.DD_INTERVENE_ENABLE) else None
        # 跟牌接应探针（v1.96）：本墩我方领出且已登记飞牌流程（领出方启动
        # 飞牌）时，按登记对象在东/西的位置分桶累计全部候选的桶内做成率，
        # 供接应端三层判据读取"引擎榜首替代牌在押注方向桶的成率"。
        _flow = getattr(state, "finesse_flow", None) or {}
        _lead_suits = {c.suit for _, c in trick_cards if c}
        _follow_ok = (bool(trick_cards) and bool(_flow)
                      and any(s in _flow for s in _lead_suits)
                      and actual_turn in (declarer, dummy)
                      and trick_leader in (declarer, dummy))
        finesse_probe_follow = {} if (_follow_ok and _dd_config.DD_INTERVENE_ENABLE) else None

        samples_done, _solve_times, _solve_total, _solve_max = self._solve_worlds(
            worlds, all_played, trick_cards, trick_leader,
            playable, state, perspective, actual_turn, declarer, dummy,
            trump, card_scores, eval_stats, finesse_probe, start_time,
            mode_note=f" ({source})", finesse_probe_follow=finesse_probe_follow)
        elapsed = time.time() - start_time

        # 统一有效性检查（来源无关）：所有世界求解失败时兜底，避免
        # _finalize_decision 拿到空 card_scores 返回 card=None。
        if not any(cs["scores"] for cs in card_scores.values()):
            return {
                "card": playable[0],
                "reasoning": "DD: 全部世界求解失败，兜底",
                "full_output": {"推荐出牌": str(playable[0])},
            }

        _sel = self._finalize_decision(card_scores, state, playable, is_declarer_side, elapsed)
        best_card = _sel["best_card"]
        child_stats = _sel["child_stats"]
        top_plays_str = _sel["top_plays_str"]
        _dropped_parts = []
        if eval_stats["dropped_win"]:
            _dropped_parts.append(f"全赢{eval_stats['dropped_win']}")
        if eval_stats["dropped_crit"]:
            _dropped_parts.append(f"临界{eval_stats['dropped_crit']}")
        if eval_stats["dropped_lose"]:
            _dropped_parts.append(f"全输{eval_stats['dropped_lose']}")
        _dropped_note = f"（过滤{'·'.join(_dropped_parts)}）" if _dropped_parts else ""
        reasoning = (
            f"DD-{source}: 评分样本{eval_stats['kept']}/{samples_done} in {elapsed:.1f}s"
            f"{_dropped_note}. "
            f"Top plays: {top_plays_str}"
        )

        return {
            "card": best_card,
            "reasoning": reasoning,
            "full_output": {
                "推荐出牌": str(best_card),
                "核心逻辑": reasoning,
                "候选对比": str(child_stats),
                # 结构化统计（供飞牌拖延等策略读取，避免解析文本）：
                # sure_win = 该候选出牌在所有样本中都 ≥ 所需墩的样本数（全赢）
                # critical = 成约与否依赖出牌的样本数（临界）
                # sure_lose = 所有出牌都 < 所需墩的样本数（全输）
                "dd_stats": {
                    "samples": samples_done,
                    "sure_win": eval_stats["sure_win"],
                    "critical": eval_stats["critical"],
                    "sure_lose": eval_stats["sure_lose"],
                },
                # 飞牌后果敏感性探针：{花色: {对象, Δ, 方向, 引牌}}，缺失大牌
                # 位置分桶的做成率差；play_service 依此判定飞牌结构。
                # 全中桶（v2.02 押注桶统一口径，"严峻"名废弃）在 accumulate 内
                # 按领出者几何方位写入单键"全中"（被飞对象全在押注方向=下家）。
                # 押注方向（v2.03 用户定调）=引牌者下家（几何）：本侧=当前出牌
                # 人下家，伙伴侧（过手探测 actual_turn=partner）=伙伴下家；
                # 用 actual_turn 推导，不再动态估计。
                "finesse_probe": _finalize_finesse_probe(
                    finesse_probe or {}, state.contract.tricks_needed,
                    {"南": "西", "北": "东"}.get(actual_turn)),
                "finesse_probe_follow": _finalize_finesse_probe_follow(
                    finesse_probe_follow or {}, state.contract.tricks_needed),
                "mcts_stats": {
                    "iterations": samples_done,
                    "time_sec": round(elapsed, 2),
                    "iters_per_sec": round(samples_done / elapsed, 1) if elapsed > 0 else 0,
                    "adaptive_cap": self.num_samples,
                    "remaining_cards": remaining_tricks * 4,
                    "valid_distributions": len(worlds) if source == "残局枚举" else None,
                    "source": source,
                    "candidates": child_stats,
                },
            },
        }

    def _enumerate_endgame_worlds(self, state: PlayState, perspective: str) -> Optional[List[Dict[str, List[Card]]]]:
        """残局完备世界枚举：穷举未知牌的所有可能分布，返回完整四家手牌列表。

        只负责世界生成（枚举替代采样），不做 DDS 求解与决策；
        供 αμ 引擎以完备世界集运行与采样路径一致的 αμ 决策算法。
        不可行（数量超限/一致性失败/未知位置数异常）返回 None。
        """
        known_positions = {perspective}
        if state.dummy and state.phase != PlayPhase.LEAD:
            known_positions.add(state.dummy)
        if state.dummy and perspective in (state.contract.declarer, state.dummy):
            known_positions.add(state.contract.declarer)

        # void 硬事实（同采样路径 collect_voids）：已出牌中垫过牌的花色，
        # 该位置剩余手牌不可能再出现，枚举阶段同样过滤掉违反的分布。
        voids = collect_voids(state)

        unknown_positions = [p for p in POSITION_ORDER if p not in known_positions]
        if len(unknown_positions) not in (2, 3):
            return None

        # 收集已知牌
        known_card_set = set()
        for pos in known_positions:
            known_card_set.update(state.hands.get(pos, []))
        for trick in state.tricks:
            for _, card in trick.cards:
                known_card_set.add(card)
        for _, card in state.current_trick.cards:
            known_card_set.add(card)

        # 未知牌池（排序确保确定性）
        pool = sorted(
            [c for c in ALL_CARDS if c not in known_card_set],
            key=lambda c: (c.suit, ["A","K","Q","J","T","9","8","7","6","5","4","3","2"].index(c.rank))
        )

        # 每个未知位置还需出多少张牌
        remaining_counts = {}
        for pos in unknown_positions:
            played = sum(1 for t in state.tricks for p, _ in t.cards if p == pos)
            played += sum(1 for p, _ in state.current_trick.cards if p == pos)
            remaining_counts[pos] = 13 - played

        total_needed = sum(remaining_counts.values())
        if total_needed != len(pool):
            # 一致性检查失败
            return None

        # 估算枚举总数
        counts = [remaining_counts[p] for p in unknown_positions]
        est = 1
        rem = len(pool)
        for c in counts[:-1]:  # 最后一个位置拿剩余全部
            est *= math.comb(rem, c)
            rem -= c
        if est > self.max_enumerations:
            print(f"[DD] Enumeration count {est} > max {self.max_enumerations}, "
                  f"falling back to sampling")
            return None

        # 残局枚举直接对真实剩余牌池穷举所有分布，无需用叫牌约束过滤。
        # 叫牌约束（如整手16HCP）针对发牌时13张手牌，残局剩余1-2张必然不满足，
        # 若在此验证会导致所有分布被过滤、枚举返回None，进而回退到同样错误的采样。
        all_played = []
        for trick in state.tricks:
            all_played.extend(trick.cards)
        all_played.extend(state.current_trick.cards)

        n_pool = len(pool)
        indices = list(range(n_pool))
        n1 = remaining_counts[unknown_positions[0]]
        worlds: List[Dict[str, List[Card]]] = []

        for combo1_idx in itertools.combinations(indices, n1):
            cards1 = [pool[i] for i in combo1_idx]
            combo1_set = set(combo1_idx)
            remaining_idx = [i for i in indices if i not in combo1_set]

            if len(unknown_positions) == 2:
                cards2 = [pool[i] for i in remaining_idx]
                distributions = [{unknown_positions[0]: cards1,
                                  unknown_positions[1]: cards2}]
            else:
                n2 = remaining_counts[unknown_positions[1]]
                distributions = []
                for combo2_idx in itertools.combinations(remaining_idx, n2):
                    combo2_set = set(combo2_idx)
                    cards2 = [pool[i] for i in combo2_idx]
                    cards3 = [pool[i] for i in remaining_idx if i not in combo2_set]
                    distributions.append({unknown_positions[0]: cards1,
                                          unknown_positions[1]: cards2,
                                          unknown_positions[2]: cards3})

            for dist in distributions:
                hands = {}
                for pos in known_positions:
                    hands[pos] = list(state.hands.get(pos, []))
                for pos, cards in dist.items():
                    hands[pos] = list(cards)

                # 安全网清除已出牌（只从打出位置移除）
                for pos, card in all_played:
                    if pos in hands:
                        hands[pos] = [c for c in hands[pos]
                                      if not (c.suit == card.suit and c.rank == card.rank)]
                if _has_duplicates(hands):
                    continue
                # void 硬事实过滤：已出牌中某位置垫过牌的花色（collect_voids），
                # 该位置剩余手牌不可能再出现该花色，命中即不可能分布，剔除。
                if _hand_violates_void(hands, voids):
                    continue
                worlds.append(hands)

        return worlds if worlds else None

    def search_perfect(self, state: PlayState) -> dict:
        """全知双明手搜索：AI 知道四家手牌，一次 DirectDDS 得所有候选精确分。

        与 search() 不同，此方法不采样，直接使用 state.hands 中的全部手牌。
        """
        # DirectDDS 总是可用（ctypes 直调 dds.dll，无 Python 端依赖）

        perspective = state.current_player
        actual_turn = state.current_player
        declarer = state.contract.declarer
        dummy = state.dummy
        # 明手不做决策：搜索视角改为庄家
        if perspective == dummy:
            perspective = declarer
        playable = state.get_playable_cards(actual_turn)

        if len(playable) == 1:
            return {
                "card": playable[0],
                "reasoning": "唯一选择",
                "full_output": {"推荐出牌": str(playable[0])},
            }

        trump = state.contract.suit
        is_declarer_side = perspective in (declarer, dummy)

        trick_state = get_current_trick_state(state)
        trick_cards = trick_state["cards"]
        trick_leader = trick_state.get("leader")

        total_played = state.declarer_tricks + state.defender_tricks
        remaining_tricks = 13 - total_played

        # 从 state.hands 直接取全四家手牌（完整信息）
        hands = {}
        for pos in POSITION_ORDER:
            hands[pos] = list(state.hands.get(pos, []))

        # DDS: trick_cards 不能出现在 hands 中（否则 remainCards 与 currentTrickSuit 双重计算）
        # state.hands 已在 play_card 时移除 trick_cards，无需额外处理

        # Phase 0b: DirectDDS Perfect 搜索
        first_p = trick_leader if trick_cards else actual_turn
        solved_list = solve_all_boards_raw([(hands, trump, first_p, trick_cards)])
        if not solved_list or solved_list[0] is None:
            return {"card": playable[0], "reasoning": "DD Perfect: DDS failed"}
        result = solved_list[0]
        score_map = _dds_result_to_score_map(result)

        _DD_POS = {'北': 0, '东': 1, '南': 2, '西': 3}
        cur_p = (_DD_POS.get(first_p, 0) + len(trick_cards)) % 4
        curplayer_is_declarer = cur_p in (_DD_POS.get(declarer, 2), _DD_POS.get(dummy, 0))

        best_card = None
        best_blended = None
        best_scores = None
        best_rank_val = None
        child_stats = []
        blended_map = {}
        scores_map = {}

        for card in playable:
            key = (card.suit, card.rank)
            target_tricks = score_map.get(key, 0)
            if curplayer_is_declarer:
                decl_side_tricks = target_tricks
            else:
                decl_side_tricks = remaining_tricks - target_tricks
            total = state.declarer_tricks + decl_side_tricks
            child_stats.append({
                "card": str(card),
                "samples": 1,
                "avg_tricks": total,
                "min_tricks": total,
                "max_tricks": total,
                "scores": [total],
            })
            rank_val = RANK_ORDER.get(card.rank, 0)
            # Perfect DD：单次精确求解，n=1 时配对阈值退化为 0（精确比较）
            blended_map[str(card)] = total
            scores_map[str(card)] = [total]
            if best_card is None or _compare_candidates(total, [total], rank_val, best_blended, best_scores, best_rank_val, is_declarer_side) > 0:
                best_blended = total
                best_scores = [total]
                best_rank_val = rank_val
                best_card = card

        from functools import cmp_to_key
        child_stats.sort(key=cmp_to_key(
            lambda a, b: -_compare_candidates(
                blended_map[a["card"]], scores_map[a["card"]], _card_rank_val(a["card"]),
                blended_map[b["card"]], scores_map[b["card"]], _card_rank_val(b["card"]),
                is_declarer_side
            )
        ))

        top_plays_str = ", ".join(
            f"{s['card']}({s['avg_tricks']})" for s in child_stats[:5]
        )
        reasoning = (
            f"DD·完美: 全知双明手分析 {len(playable)} 个候选. "
            f"Top: {top_plays_str}"
        )

        return {
            "card": best_card,
            "reasoning": reasoning,
            "full_output": {
                "推荐出牌": str(best_card),
                "核心逻辑": reasoning,
                "候选对比": str(child_stats),
                "局面评估": "DD·完美：基于全知四家手牌的双明手精确分析",
                "mcts_stats": {
                    "iterations": 1,
                    "time_sec": 0,
                    "candidates": child_stats,
                },
            },
            "prompt": "[DD·完美] no prompt",
        }
