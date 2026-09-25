import os
import time
import random
import copy
import math
import threading
from typing import Dict, List, Set, Optional, Tuple

from bridge.play_types import Card, PlayState, PlayPhase, POSITION_ORDER
from bridge.mcts.state_utils import SUIT_DISPLAY_ORDER, RANK_DESC
from bridge.mcts.constraints import (
    BidConstraint, validate_sample,
    HCP_MAP, CONTROL_MAP,
    validate_relaxed, validate_voids_only,
    _is_balanced, _check_constraint, _rank_value_of,
)
from bridge.mcts.belief import collect_voids


# 一副完整的52张牌
ALL_CARDS = [Card(suit=s, rank=r) for s in SUIT_DISPLAY_ORDER for r in RANK_DESC]


# 调试日志路径
_BASE_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
_DEBUG_LOG = os.path.join(_BASE_DIR, "dd_debug.log")

# ---- Phase 0a: 均匀采样 ----

def _extract_known_info(state: "PlayState", perspective: str) -> dict:
    """从 PlayState 提取生成均匀样本所需的所有已知信息。

    Returns dict with keys:
        known_cards: 已确定位置的牌张集合
        unknown_pool: 未知牌池（Card 列表）
        remaining_counts: {pos: count} 每家还需分配的张数
        known_voids: {pos: {suit, ...}} 已知缺门
        own_hand: 自己的手牌 {pos: [Card]}
        dummy_hand: 明手牌（若可见）{pos: [Card]}
        result: 预填充的已知手牌 {pos: [Card]}
    """
    declarer = state.contract.declarer
    dummy = state.dummy
    is_declarer_side = perspective in (declarer, dummy)

    # 1. 收集已知牌张（在局部副本上去重，不写回调用方的 state.hands，
    #    避免此处去重使 DD 引擎先前算好的 playable 失效，导致返回"非法牌"）
    cleaned_hands = {pos: list(hand) for pos, hand in state.hands.items()}
    all_hand_cards = {}
    for pos in POSITION_ORDER:
        hand = cleaned_hands.get(pos, [])
        seen_in_this_pos = set()
        cleaned = []
        for c in hand:
            key = (c.suit, c.rank)
            if key in all_hand_cards:
                other = all_hand_cards[key]
                with open(_DEBUG_LOG, "a", encoding="utf-8") as f:
                    f.write(f"\n[WARN] DUPLICATE in state.hands: {c} in both {other} and {pos}, removed from {pos}\n")
            elif key in seen_in_this_pos:
                with open(_DEBUG_LOG, "a", encoding="utf-8") as f:
                    f.write(f"\n[WARN] DUPLICATE in state.hands[{pos}]: {c} appears twice, removed\n")
            else:
                seen_in_this_pos.add(key)
                all_hand_cards[key] = pos
                cleaned.append(c)
        cleaned_hands[pos] = cleaned

    known_cards: Set[Card] = set()
    own_hand = cleaned_hands.get(perspective, [])
    known_cards.update(own_hand)

    if is_declarer_side and dummy:
        known_cards.update(cleaned_hands.get(declarer, []))
        known_cards.update(cleaned_hands.get(dummy, []))
    elif dummy and perspective != dummy:
        if state.phase != PlayPhase.LEAD:
            known_cards.update(cleaned_hands.get(dummy, []))

    # 已出牌张
    for trick in state.tricks:
        for _, card in trick.cards:
            known_cards.add(card)
    for _, card in state.current_trick.cards:
        known_cards.add(card)

    # 按位置收集已出牌面（首攻白名单递减用：判断已出该花色中 >首攻牌 的张数）
    played_by_pos: Dict[str, List[Card]] = {}
    for trick in state.tricks:
        for _pos, _c in trick.cards:
            played_by_pos.setdefault(_pos, []).append(_c)
    for _pos, _c in state.current_trick.cards:
        played_by_pos.setdefault(_pos, []).append(_c)

    # 2. 计算每家剩余张数
    remaining_counts = compute_remaining_counts(state)

    # 3. 未知牌池
    unknown_pool = [c for c in ALL_CARDS if c not in known_cards]
    random.shuffle(unknown_pool)

    # 4. 预填充已知手牌
    result = {}
    if is_declarer_side and dummy:
        for pos in (declarer, dummy):
            hand = cleaned_hands.get(pos, [])
            if hand:
                result[pos] = [Card(suit=c.suit, rank=c.rank) for c in hand]
    else:
        if own_hand:
            result[perspective] = [Card(suit=c.suit, rank=c.rank) for c in own_hand]
        if dummy and state.phase != PlayPhase.LEAD:
            hand = cleaned_hands.get(dummy, [])
            if hand:
                result[dummy] = [Card(suit=c.suit, rank=c.rank) for c in hand]

    # 4.5 修正已知手牌张数
    for pos in list(result.keys()):
        expected = remaining_counts.get(pos, 0)
        actual = len(result[pos])
        if actual > expected:
            excess = actual - expected
            to_remove = random.sample(result[pos], excess)
            result[pos] = [c for c in result[pos] if c not in set(to_remove)]

    # 4.6 重建未知牌池（基于已分配牌）
    assigned = set()
    for pos, cards in result.items():
        for c in cards:
            assigned.add((c.suit, c.rank))
    played_set = set()
    for trick in state.tricks:
        for _, c in trick.cards:
            played_set.add((c.suit, c.rank))
    for _, c in state.current_trick.cards:
        played_set.add((c.suit, c.rank))
    unknown_pool = [c for c in ALL_CARDS
                    if (c.suit, c.rank) not in assigned
                    and (c.suit, c.rank) not in played_set]

    # 4.7 统计每家已出牌（中局约束扣减用：初始约束 = 已出部分 + 剩余部分）
    played_stats = compute_played_stats(state)

    # 5. 收集已知缺门
    known_voids = collect_voids(state)

    return {
        "known_cards": known_cards,
        "unknown_pool": unknown_pool,
        "remaining_counts": remaining_counts,
        "known_voids": known_voids,
        "own_hand": own_hand,
        "dummy_hand": cleaned_hands.get(dummy, []) if dummy else [],
        "result": result,
        "played": played_stats,
        "played_by_pos": played_by_pos,
    }


def compute_remaining_counts(state: "PlayState") -> Dict[str, int]:
    """计算每家剩余手牌张数（视角无关，供中局约束扣减/展示）。"""
    total_completed = state.declarer_tricks + state.defender_tricks
    base_remaining = 13 - total_completed
    remaining_counts = {}
    for pos in POSITION_ORDER:
        in_trick = sum(1 for p, _ in state.current_trick.cards if p == pos)
        remaining_counts[pos] = base_remaining - in_trick
    return remaining_counts


def compute_played_stats(state: "PlayState") -> Dict[str, dict]:
    """统计每家已出牌汇总（HCP/控制/各花色张数），视角无关。

    中局约束扣减用：初始约束 = 已出部分 + 剩余部分。
    """
    played_stats = {
        p: {"hcp": 0, "controls": 0, "suit": {"♠": 0, "♥": 0, "♦": 0, "♣": 0}}
        for p in POSITION_ORDER
    }
    for _trick in state.tricks:
        for p, c in _trick.cards:
            _st = played_stats.get(p)
            if _st is None:
                continue
            _st["hcp"] += HCP_MAP.get(c.rank, 0)
            _st["controls"] += CONTROL_MAP.get(c.rank, 0)
            _st["suit"][c.suit] = _st["suit"].get(c.suit, 0) + 1
    for p, c in state.current_trick.cards:
        _st = played_stats.get(p)
        if _st is None:
            continue
        _st["hcp"] += HCP_MAP.get(c.rank, 0)
        _st["controls"] += CONTROL_MAP.get(c.rank, 0)
        _st["suit"][c.suit] = _st["suit"].get(c.suit, 0) + 1
    return played_stats


def _sample_uniform(known_info: dict,
                    active_constraints: Dict[str, "BidConstraint"] = None) -> Dict[str, List[Card]]:
    """均匀随机分配未知牌：打乱 pool → 把每张牌分配到所需位置，尽量跳过 void 花色。

    保证世界永远完整（池中每张牌都被分配，绝不丢牌）：void 花色只在对应位置
    仍有需求时避开；若某张牌因 void 在任何仍缺张的位置都放不下（信息矛盾），
    则退回其他位置补齐张数，由上层验证链（Level0/兜底）剔除无效世界。

    这就是论文的 "random generation followed by verification of the constraints"。

    active_constraints 非空时先做 **specific_cards 预分配（pin）**：把"必持牌"
    （如首攻顶张连张 `必持♠Q`）从未知牌池取出直接放进对应未知位置，使硬承诺在
    每层采样初态即满足、不依赖修复迭代（v2.14：修 _sample_mh_repair 对
    specific_cards 缺失偶发修复失败落入放宽链丢约束的问题）。
    """
    result = {pos: list(cards) for pos, cards in known_info["result"].items()}
    pool = list(known_info["unknown_pool"])
    if active_constraints:
        for pos, con in active_constraints.items():
            if pos in known_info.get("result", {}):
                continue  # 已知手牌位置不参与采样/必持牌
            for _suit, _rank in con.specific_cards:
                if any(c.suit == _suit and c.rank == _rank for c in result.get(pos, [])):
                    continue
                idx = next((k for k, c in enumerate(pool)
                            if c.suit == _suit and c.rank == _rank), None)
                if idx is None:
                    continue  # 目标牌在已知手牌/已出 → 可行预检会发现约束不可满足
                result.setdefault(pos, []).append(pool.pop(idx))
            # 首攻小牌白名单预分配（v2.15）：把该花色 >首攻牌 的牌优先塞给该位置，
            # 使"≥3 张 >X"的长四条件在采样初态即满足，不依赖 MH 定向修复
            # （否则"恰3张>X"靠兜底对称交换很难在 300 步内凑出，落入放宽链丢约束）。
            if con.lead_small_shapes is not None:
                _ls_suit, _ls_rank, _ls_entries = con.lead_small_shapes
                _lead_rv = _rank_value_of(_ls_rank)
                # 从白名单条目读总长下限与 >X 上下限（长四=恰3；递减后=0~3）
                _t_min = max((e[0] for e in _ls_entries), default=4)
                _a_min = min((e[2] for e in _ls_entries), default=0)
                _a_max = max((e[3] for e in _ls_entries), default=3)
                _have = [c for c in result.get(pos, []) if c.suit == _ls_suit]
                _have_above = sum(1 for c in _have
                                  if _rank_value_of(c.rank) > _lead_rv)
                # 预分配该花色 >X 牌：
                #   · "恰3"条目（长四初态，amin==amax==3）：取到 3 张即可
                #   · "≤3"条目（递减后，amin==0 amax==3）：**取走全部 >X**
                #     使后续随机分配不可能再塞 >X 牌回该位置，above 恒 ≤3
                #     （否则 Tier1 可能把池中剩余 >8 的牌给西，above 超限违约）
                _target = _a_max if _a_min == _a_max else 13
                for _ in range(max(0, _target - _have_above)):
                    idx = next((k for k, c in enumerate(pool)
                                if c.suit == _ls_suit
                                and _rank_value_of(c.rank) > _lead_rv), None)
                    if idx is None:
                        break
                    result.setdefault(pos, []).append(pool.pop(idx))
                # 补足该花色总长至条目下限
                _have2 = [c for c in result.get(pos, []) if c.suit == _ls_suit]
                if len(_have2) < _t_min:
                    idx = next((k for k, c in enumerate(pool)
                                if c.suit == _ls_suit), None)
                    if idx is not None:
                        result.setdefault(pos, []).append(pool.pop(idx))
    random.shuffle(pool)
    remaining_counts = dict(known_info["remaining_counts"])
    known_voids = known_info["known_voids"]

    for pos in POSITION_ORDER:
        if pos not in result:
            result[pos] = []
    # 每个位置仍缺的张数（剩余需求）
    needs = {
        pos: remaining_counts.get(pos, 0) - len(result.get(pos, []))
        for pos in POSITION_ORDER
    }
    void_suits = {pos: known_voids.get(pos, set()) for pos in POSITION_ORDER}

    residue = []
    # Tier 1：每张牌优先放进「仍缺张，且不 void 该花色，且剩余需求最大」的位置
    for card in pool:
        eligible = [
            pos for pos in POSITION_ORDER
            if needs[pos] > 0 and card.suit not in void_suits[pos]
        ]
        if eligible:
            pos = max(eligible, key=lambda p: needs[p])
            result[pos].append(card)
            needs[pos] -= 1
        else:
            residue.append(card)
    # Tier 2：残留牌（其花色在几乎所有仍缺张的位置都被 void）。
    # 退回仍缺张的位置补齐张数，保证世界完整；可能违反 void，由验证链剔除。
    for card in residue:
        open_pos = [p for p in POSITION_ORDER if needs[p] > 0]
        if not open_pos:
            break
        pos = max(open_pos, key=lambda p: needs[p])
        result[pos].append(card)
        needs[pos] -= 1

    return result


def _propose_swap(
    world: Dict[str, List[Card]],
    active_constraints: Dict[str, "BidConstraint"],
    swap_positions: List[str],
) -> Optional[Tuple[str, str, int, int]]:
    """引导式提案：返回一个针对违约位置定向修复的双卡交换 (vpos, dpos, i, j)。

    只在未知位置间交换，不碰已知手牌。按违约类型选择方向与目标牌：
      - HCP 超标：从违约位置挪出最高 HCP 牌，从最低分位置取最低 HCP 牌补入（降 HCP）；
      - HCP 不足：挪出最低 HCP 牌，从最高分位置取最高 HCP 牌补入（升 HCP）；
      - 花色缺长：挪出非该花色牌，从有该花色牌的位置取该花色牌补入；
      - 花色过长：挪出多余花色牌，补入非该花色牌；
      - 兜底：对称交换（保证遍历性）。
    无违约位置时返回 None（调用方视为已满足并结束）。
    """
    violating = [
        p for p in active_constraints
        if p in swap_positions
        and not _check_constraint(world.get(p, []), active_constraints[p])
    ]
    if not violating:
        return None
    vpos = violating[random.randrange(len(violating))]
    vcon = active_constraints[vpos]
    vhand = world.get(vpos, [])
    donors = [p for p in swap_positions if p != vpos]
    if not vhand or not donors:
        return None

    vhcp = sum(HCP_MAP.get(c.rank, 0) for c in vhand)
    vdist: Dict[str, int] = {}
    for c in vhand:
        vdist[c.suit] = vdist.get(c.suit, 0) + 1
    vcontrols = sum(CONTROL_MAP.get(c.rank, 0) for c in vhand)

    def pos_hcp(p: str) -> int:
        return sum(HCP_MAP.get(c.rank, 0) for c in world.get(p, []))

    # 1) HCP 超标：需降 HCP
    if vcon.max_hcp is not None and vhcp > vcon.max_hcp:
        # 挪出的牌必须避开 suit_min 要求保留的花色，否则降 HCP 会破坏花色约束造成振荡
        protected = {
            s for s, n in vcon.suit_min.items()
            if vdist.get(s, 0) <= n
        }
        movable = [k for k in range(len(vhand)) if vhand[k].suit not in protected]
        if not movable:
            movable = list(range(len(vhand)))
        i = max(movable, key=lambda k: HCP_MAP.get(vhand[k].rank, 0))
        dpos = min(donors, key=pos_hcp)
        dhand = world.get(dpos, [])
        if not dhand:
            return None
        j = min(range(len(dhand)), key=lambda k: HCP_MAP.get(dhand[k].rank, 0))
        return vpos, dpos, i, j
    # 2) HCP 不足：需升 HCP
    if vcon.min_hcp is not None and vhcp < vcon.min_hcp:
        i = min(range(len(vhand)), key=lambda k: HCP_MAP.get(vhand[k].rank, 0))
        dpos = max(donors, key=pos_hcp)
        dhand = world.get(dpos, [])
        if not dhand:
            return None
        j = max(range(len(dhand)), key=lambda k: HCP_MAP.get(dhand[k].rank, 0))
        return vpos, dpos, i, j
    # 3) 必持牌缺失（specific_cards，v2.14 首攻顶张连张）：精确目标牌，
    #    从持有它的位置定向换入；换出 vpos 最低 HCP 的非保护牌抵消点力。
    for _suit, _rank in vcon.specific_cards:
        if any(c.suit == _suit and c.rank == _rank for c in vhand):
            continue
        with_card = [
            p for p in donors
            if any(c.suit == _suit and c.rank == _rank for c in world.get(p, []))
        ]
        if not with_card:
            continue  # 目标牌在已知手牌中（不可交换）→ 交 INFEASIBLE 兜底
        dpos = with_card[0]
        dhand = world.get(dpos, [])
        j = next(k for k, c in enumerate(dhand)
                 if c.suit == _suit and c.rank == _rank)
        protected = {
            s for s, n in vcon.suit_min.items()
            if vdist.get(s, 0) <= n
        }
        movable = [k for k in range(len(vhand))
                   if vhand[k].suit not in protected]
        if not movable:
            movable = list(range(len(vhand)))
        i = min(movable, key=lambda k: HCP_MAP.get(vhand[k].rank, 0))
        return vpos, dpos, i, j
    suit_deficit = {
        s: n for s, n in vcon.suit_min.items()
        if n - vdist.get(s, 0) > 0
    }
    for s, n in vcon.exact_suit.items():
        if n - vdist.get(s, 0) > 0:
            suit_deficit[s] = n
    if suit_deficit:
        wanted = next(iter(suit_deficit))
        # 优先从"超过其 suit_min"的花色移出牌，避免补 wanted 时把其他花色压到约束之下
        # （否则补♦会动到♥=5=suit_min，导致 ♥≥5 被破坏，形成补♦破♥的振荡）
        protected = {
            s for s, n in vcon.suit_min.items()
            if vdist.get(s, 0) <= n
        }
        candidates = [k for k in range(len(vhand))
                      if vhand[k].suit != wanted and vhand[k].suit not in protected]
        if not candidates:
            candidates = [k for k in range(len(vhand)) if vhand[k].suit != wanted]
        if not candidates:
            candidates = list(range(len(vhand)))
        with_wanted = [
            p for p in donors
            if any(c.suit == wanted for c in world.get(p, []))
        ]
        pool_d = with_wanted if with_wanted else donors
        # 是否必须保 HCP：若"移出最高非目标牌 + 补入最低目标牌"会跌破 HCP 下限，
        # 则改走保 HCP 路径，避免 new_score 升高被 Metropolis 拒绝而陷入死锁。
        keep_hcp = False
        if vcon.min_hcp is not None:
            max_non_wanted = max(
                (HCP_MAP.get(vhand[k].rank, 0) for k in candidates), default=0
            )
            if vhcp - max_non_wanted < vcon.min_hcp:
                keep_hcp = True
        if keep_hcp:
            # 保 HCP：移出最低 HCP 非目标牌，补入最高 HCP 目标牌（不超出 max_hcp）
            i = min(candidates, key=lambda k: HCP_MAP.get(vhand[k].rank, 0))
            cur_hcp = vhcp - HCP_MAP.get(vhand[i].rank, 0)
            cap = vcon.max_hcp if vcon.max_hcp is not None else float("inf")
            best_d = None
            best_j = -1
            best_hcp = -1
            for p in pool_d:
                dh = world.get(p, [])
                for k in range(len(dh)):
                    if dh[k].suit != wanted or HCP_MAP.get(dh[k].rank, 0) <= best_hcp:
                        continue
                    if cur_hcp + HCP_MAP.get(dh[k].rank, 0) <= cap:
                        best_hcp = HCP_MAP.get(dh[k].rank, 0)
                        best_d = p
                        best_j = k
            if best_d is None:
                # 目标牌都会超 max_hcp，退回最高目标牌（接受率会兜底，不制造新违约循环）
                for p in pool_d:
                    dh = world.get(p, [])
                    for k in range(len(dh)):
                        if dh[k].suit == wanted and HCP_MAP.get(dh[k].rank, 0) > best_hcp:
                            best_hcp = HCP_MAP.get(dh[k].rank, 0)
                            best_d = p
                            best_j = k
            if best_d is None:
                return None
            return vpos, best_d, i, best_j
        # 默认：压低 HCP（移出最高非目标牌，补入最低目标牌）
        i = max(candidates, key=lambda k: HCP_MAP.get(vhand[k].rank, 0))
        dpos = min(pool_d, key=pos_hcp)
        dhand = world.get(dpos, [])
        wanted_idx = [k for k in range(len(dhand)) if dhand[k].suit == wanted]
        if not wanted_idx:
            return None
        j = min(wanted_idx, key=lambda k: HCP_MAP.get(dhand[k].rank, 0))
        return vpos, dpos, i, j
    # 4) 花色过长（suit_max / exact_suit）：需移出多余花色
    excess = set(vcon.suit_max.keys()) | set(vcon.exact_suit.keys())
    over_suit = None
    for s in excess:
        limit = vcon.suit_max.get(s, vcon.exact_suit.get(s, 0))
        if vdist.get(s, 0) > limit:
            over_suit = s
            break
    if over_suit is not None:
        over_idx = [k for k in range(len(vhand)) if vhand[k].suit == over_suit]
        if over_idx:
            i = max(over_idx, key=lambda k: HCP_MAP.get(vhand[k].rank, 0))
            dpos = min(donors, key=pos_hcp)
            dhand = world.get(dpos, [])
            not_over = [k for k in range(len(dhand)) if dhand[k].suit != over_suit]
            if not not_over:
                return None
            j = min(not_over, key=lambda k: HCP_MAP.get(dhand[k].rank, 0))
            return vpos, dpos, i, j
    # 5) 兜底：对称交换（保证遍历性）
    i = random.randrange(len(vhand))
    dpos = random.choice(donors)
    dhand = world.get(dpos, [])
    if not dhand:
        return None
    j = random.randrange(len(dhand))
    return vpos, dpos, i, j


def _sample_mh_repair(
    known_info: dict,
    active_constraints: Dict[str, "BidConstraint"],
    max_swaps: int = 300,
    stall_limit: int = 60,
    beta: float = 1.0,
) -> Tuple[Dict[str, List[Card]], bool]:
    """MH 修复：从一次均匀发牌出发，用引导式提案 + Metropolis 接受率逼近满足 L1 的手牌。

    提案优先定向移动高价值牌到违约位置（收敛快），按 Metropolis 接受率
    min(1, exp(-beta * Δscore)) 接受/拒绝，在加速收敛的同时对分布做校正。
    β 越小越接近均匀探索，β 越大越激进逼近硬约束。只交换未知位置，不碰已知手牌。
    返回 (world, ok)。

    打分=0 与 validate_hard 通过严格等价（违反任一条件都会使分数>0），故循环内
    只用分数判停，省掉每步重复的完整约束校验（旧实现每步还会先生态一次必然
    False 的 validate_hard，纯浪费）；连续 stall_limit 步无改进即提前退出，
    避免不可行局面烧光 max_swaps 预算（不等价收敛仍在预算内完成，语义不变）。
    """
    world = _sample_uniform(known_info, active_constraints)
    if not active_constraints:
        return world, True
    known_positions = set(known_info.get("result", {}).keys())
    swap_positions = [p for p in world if p not in known_positions]
    if len(swap_positions) < 2:
        return world, False

    def total_score() -> int:
        return sum(
            _constraint_violation_score(world.get(p, []), con)
            for p, con in active_constraints.items()
        )

    current_score = total_score()
    if current_score == 0:
        return world, True
    no_improve = 0
    for _ in range(max_swaps):
        proposal = _propose_swap(world, active_constraints, swap_positions)
        if proposal is None:
            return world, current_score == 0
        vpos, dpos, i, j = proposal
        hand_v = world.get(vpos, [])
        hand_d = world.get(dpos, [])
        if not hand_v or not hand_d:
            return world, False
        hand_v[i], hand_d[j] = hand_d[j], hand_v[i]
        new_score = total_score()
        accept_prob = min(1.0, math.exp(-beta * (new_score - current_score)))
        if random.random() < accept_prob:
            current_score = new_score
            if current_score == 0:
                return world, True
        else:
            hand_v[i], hand_d[j] = hand_d[j], hand_v[i]
        no_improve = 0 if current_score == 0 else no_improve + 1
        if current_score != 0 and no_improve >= stall_limit:
            break
    return world, current_score == 0


def _master_priority(con: "BidConstraint") -> int:
    score = 0
    if con.min_hcp is not None:
        score += con.min_hcp
    if con.min_controls is not None:
        score += con.min_controls * 2
    for _s, n in con.suit_min.items():
        score += n * 2
    if con.balanced is not None:
        score += 1
    return score


def _sample_master_soft(
    known_info: dict,
    active_constraints: Dict[str, "BidConstraint"],
    max_masters: int = 3,
) -> Optional[Dict[str, List[Card]]]:
    """主从软约束采样：只保证「约束最紧」的一方硬满足，其余未知位置吃剩余牌。

    背景：两家主动叫牌（如南逆叫16+、西1NT均型）同时硬满足在均匀空间里极稀疏
    （双约束占比可低至 0.004%），MH 对称修复两个违约位置会互相拉扯而难以收敛。
    这里选中约束最紧的一方作为 master 单独做 MH 修复，slave 位置自动吃剩余牌，
    其约束退化为软约束（不否决世界），符合「主分配一家 + 另一家暂不严格」的直觉。
    返回 None 表示无法满足任一 master（调用方继续降级到 Level 2）。
    """
    positions = [
        p for p in active_constraints.keys()
        if p not in known_info.get("result", {})
    ]
    if len(positions) < 2:
        return None
    ordered = sorted(
        positions,
        key=lambda p: _master_priority(active_constraints[p]),
        reverse=True,
    )
    remaining_counts = known_info.get("remaining_counts", {})
    unknown_pool = known_info.get("unknown_pool", [])
    for master in ordered[:max_masters]:
        # 单位置可满足性预检：HCP/花色与剩余牌池必然冲突的主位直接跳过，
        # 不给 MH 修复留空转机会（非充分检查，仅跳过必然不可行者）
        if not _position_hcp_feasible(
            active_constraints[master], unknown_pool, remaining_counts.get(master, 0)
        ):
            continue
        world, ok = _sample_mh_repair(
            known_info, {master: active_constraints[master]}
        )
        if ok:
            return world
    return None


def _constraint_trivially_satisfied(c: "BidConstraint", remaining_count: int) -> bool:
    """剩余约束是否无条件满足（采样无需再验证该位置）。"""
    if c.min_hcp not in (None, 0):
        return False
    if c.max_hcp is not None and c.max_hcp < remaining_count * 4:
        return False
    if c.min_controls not in (None, 0):
        return False
    if any(c.suit_min.values()):
        return False
    if any(c.suit_max.values()):
        return False
    if c.exact_suit:
        return False
    if c.specific_cards:
        return False
    if c.length_above:
        return False
    if c.lead_shape is not None:
        return False
    if c.lead_small_shapes is not None:
        return False
    if c.balanced is not None:
        return False
    return True


def _position_hcp_feasible(
    con: "BidConstraint",
    pool_cards: List[Card],
    L: int,
) -> bool:
    """单位置可满足性：在满足花色要求的前提下，该位置 HCP 可达区间是否与约束有交集。

    若被迫拿满 suit_min 所需花色后 HCP 必然超标（或必然不足），则约束必不可行。
    例如某位置 ♠≥6 且池中♠全高HCP，西拿满6张♠后 HCP 必 > max_hcp。
    这是必要不充分检查，用于在 MH/L1/L2 空转前识别确定性冲突。
    """
    if L <= 0:
        return True
    suit_sorted = {
        s: sorted([c for c in pool_cards if c.suit == s], key=lambda c: HCP_MAP.get(c.rank, 0))
        for s in SUIT_DISPLAY_ORDER
    }
    # 合并 suit_min 与 exact_suit 为各花色必需张数（exact_suit 覆盖为精确值）
    required: Dict[str, int] = {}
    for s, n in con.suit_min.items():
        required[s] = max(required.get(s, 0), n)
    for s, n in con.exact_suit.items():
        required[s] = n
    fixed = 0
    for s, n in required.items():
        if len(suit_sorted[s]) < n:
            return False
        fixed += n
    rem = L - fixed
    if rem < 0:
        return False
    used = {s: required.get(s, 0) for s in SUIT_DISPLAY_ORDER if s in required}
    # 最小可达 HCP：各必需花色取最低 n 张，其余取全池最低 rem 张
    mn = 0
    for s in SUIT_DISPLAY_ORDER:
        n = used.get(s, 0)
        mn += sum(HCP_MAP.get(c.rank, 0) for c in suit_sorted[s][:n])
    rest_low = []
    for s in SUIT_DISPLAY_ORDER:
        n = used.get(s, 0)
        seq = suit_sorted[s]
        if s in con.exact_suit:
            continue  # exact_suit 恰好取 n 张，剩余该花色不能进入该位置
        rest_low.extend(seq[n:])
    rest_low.sort(key=lambda c: HCP_MAP.get(c.rank, 0))
    mn += sum(HCP_MAP.get(c.rank, 0) for c in rest_low[:rem])
    # 最大可达 HCP：各必需花色取最高 n 张，其余取全池最高 rem 张
    mx = 0
    for s in SUIT_DISPLAY_ORDER:
        n = used.get(s, 0)
        seq = suit_sorted[s]
        mx += sum(HCP_MAP.get(c.rank, 0) for c in seq[-n:] if n)
    rest_high = []
    for s in SUIT_DISPLAY_ORDER:
        n = used.get(s, 0)
        seq = suit_sorted[s]
        if s in con.exact_suit:
            continue
        rest_high.extend(seq[:len(seq) - n])
    rest_high.sort(key=lambda c: HCP_MAP.get(c.rank, 0), reverse=True)
    mx += sum(HCP_MAP.get(c.rank, 0) for c in rest_high[:rem])
    if con.max_hcp is not None and mn > con.max_hcp:
        return False
    if con.min_hcp is not None and mx < con.min_hcp:
        return False
    return True


def _check_feasible(
    active_constraints: Dict[str, "BidConstraint"],
    known_info: dict,
) -> bool:
    """可满足性预检：约束在当前未知牌池下是否可能同时成立。

    仅做必要条件检查（不充分）。任一不满足则约束必不可能满足，
    调用方应跳过 L1/L2 重试直接降级，避免无效空转。
    """
    unknown_pool = known_info["unknown_pool"]
    total_hcp = sum(HCP_MAP.get(c.rank, 0) for c in unknown_pool)
    total_controls = sum(CONTROL_MAP.get(c.rank, 0) for c in unknown_pool)
    suit_counts: Dict[str, int] = {s: 0 for s in SUIT_DISPLAY_ORDER}
    pool_cards: Set[Tuple[str, str]] = set()
    for c in unknown_pool:
        suit_counts[c.suit] = suit_counts[c.suit] + 1
        pool_cards.add((c.suit, c.rank))

    sum_min_hcp = 0
    sum_min_controls = 0
    sum_suit_min: Dict[str, int] = {s: 0 for s in SUIT_DISPLAY_ORDER}
    for con in active_constraints.values():
        if con.min_hcp is not None and con.min_hcp > 0:
            sum_min_hcp += con.min_hcp
            if con.min_hcp > total_hcp:
                return False
        if con.min_controls is not None and con.min_controls > 0:
            sum_min_controls += con.min_controls
            if con.min_controls > total_controls:
                return False
        for s, n in con.suit_min.items():
            sum_suit_min[s] += n
            if n > suit_counts[s]:
                return False
        for suit, rank in con.specific_cards:
            if (suit, rank) not in pool_cards:
                return False
        for suit, (base_rank, need_n) in con.length_above.items():
            pool_above = [c for c in unknown_pool if c.suit == suit
                          and c.rank_value > _rank_value_of(base_rank)]
            if len(pool_above) < need_n:
                return False
    if sum_min_hcp > total_hcp:
        return False
    if sum_min_controls > total_controls:
        return False
    for s in SUIT_DISPLAY_ORDER:
        if sum_suit_min[s] > suit_counts[s]:
            return False
    # 单位置：花色+HCP 冲突检测（如被迫拿满高HCP花色必然超标）
    remaining_counts = known_info.get("remaining_counts", {})
    for pos, con in active_constraints.items():
        L = remaining_counts.get(pos, 0)
        if L > 0 and not _position_hcp_feasible(con, unknown_pool, L):
            return False
    return True


def _constraint_violation_score(cards: List[Card], con: "BidConstraint") -> int:
    """单位置约束违反打分：分数越小越接近满足，0 表示完全满足。

    用于兜底降级保护：在无法满足硬约束时挑选违反最少的候选世界。
    """
    hcp = 0
    controls = 0
    dist: Dict[str, int] = {s: 0 for s in SUIT_DISPLAY_ORDER}
    for c in cards:
        hcp += HCP_MAP.get(c.rank, 0)
        controls += CONTROL_MAP.get(c.rank, 0)
        dist[c.suit] = dist[c.suit] + 1
    score = 0
    if con.min_hcp is not None and hcp < con.min_hcp:
        score += con.min_hcp - hcp
    if con.max_hcp is not None and hcp > con.max_hcp:
        score += hcp - con.max_hcp
    if con.min_controls is not None and controls < con.min_controls:
        score += con.min_controls - controls
    for s, n in con.suit_min.items():
        if dist.get(s, 0) < n:
            score += n - dist.get(s, 0)
    for s, n in con.suit_max.items():
        if dist.get(s, 0) > n:
            score += dist.get(s, 0) - n
    for s, n in con.exact_suit.items():
        if dist.get(s, 0) != n:
            score += abs(dist.get(s, 0) - n)
    if con.balanced is not None:
        if con.balanced != _is_balanced(dist):
            score += 1
    for suit, rank in con.specific_cards:
        if not any(c.suit == suit and c.rank == rank for c in cards):
            score += 1
    for suit, (base_rank, need_n) in con.length_above.items():
        above = sum(1 for c in cards if c.suit == suit
                    and c.rank_value > _rank_value_of(base_rank))
        if above < need_n:
            score += need_n - above
    if con.lead_shape is not None:
        from bridge.mcts.constraints import match_suit_shape
        if not match_suit_shape(cards, con.lead_shape):
            score += 1
    if con.lead_small_shapes is not None:
        from bridge.mcts.constraints import match_suit_small_shapes
        if not match_suit_small_shapes(cards, con.lead_small_shapes):
            score += 1
    return score


def _pick_least_violating(
    active_constraints: Dict[str, "BidConstraint"],
    known_info: dict,
    k: int = 10,
) -> Dict[str, List[Card]]:
    """兜底降级保护：生成 k 个均匀候选，返回违反约束最少的一套。

    约束无法满足时的兜底，从"纯随机"改为"选违反最少的候选"，
    使 DD/αμ 评估起点尽量贴近叫牌信息。
    """
    best_world = None
    best_score = None
    for _ in range(k):
        world = _sample_uniform(known_info, active_constraints)
        total = 0
        for pos, con in active_constraints.items():
            cards = world.get(pos, [])
            if cards:
                total += _constraint_violation_score(cards, con)
        if best_score is None or total < best_score:
            best_score = total
            best_world = world
            if total == 0:
                break
    return best_world


def _reduce_constraint_for_played(
    c: "BidConstraint",
    played: dict,
    remaining_count: int,
    played_cards: Optional[List[Card]] = None,
) -> Optional["BidConstraint"]:
    """中局扣减：把整手约束按已出牌折算为剩余部分约束。

    物理意义：初始约束 = 已出部分 + 剩余部分。返回副本，不修改原约束。
    折算后若无条件满足则返回 None（采样跳过该位置验证）。
    """
    if not played:
        return c
    reduced = copy.deepcopy(c)
    played_hcp = played.get("hcp", 0)
    played_controls = played.get("controls", 0)
    played_suit = played.get("suit", {})
    # HCP：剩余范围 = [初始min - 已出HCP, 初始max - 已出HCP]
    if reduced.min_hcp is not None:
        reduced.min_hcp = max(0, reduced.min_hcp - played_hcp)
    if reduced.max_hcp is not None:
        reduced.max_hcp = max(reduced.max_hcp - played_hcp, reduced.min_hcp or 0)
    # 控制数同样按已出牌扣减
    if reduced.min_controls is not None:
        reduced.min_controls = max(0, reduced.min_controls - played_controls)
    # 花色张数：suit_min/exact_suit 扣减后不超剩余张数；suit_max 扣减已出张数
    for s in list(reduced.suit_min.keys()):
        reduced.suit_min[s] = max(0, min(reduced.suit_min[s] - played_suit.get(s, 0), remaining_count))
    for s in list(reduced.exact_suit.keys()):
        reduced.exact_suit[s] = max(0, min(reduced.exact_suit[s] - played_suit.get(s, 0), remaining_count))
    for s in list(reduced.suit_max.keys()):
        reduced.suit_max[s] = max(0, reduced.suit_max[s] - played_suit.get(s, 0))
    # length_above：> 基准牌 的张数随已出中 > 基准 的张数递减（用户原则：
    # 所有带长度/点力的约束都随出牌递减）
    if reduced.length_above:
        played_above: Dict[str, int] = {}
        for _c in (played_cards or []):
            for _s, (_base_r, _n) in reduced.length_above.items():
                if (_c.suit == _s
                        and _rank_value_of(_c.rank) > _rank_value_of(_base_r)):
                    played_above[_s] = played_above.get(_s, 0) + 1
        for _s in list(reduced.length_above.keys()):
            _base_r, _n = reduced.length_above[_s]
            new_n = max(0, _n - played_above.get(_s, 0))
            if new_n == 0:
                del reduced.length_above[_s]
            else:
                reduced.length_above[_s] = (_base_r, new_n)
    # 均型是整手 13 张属性，剩余碎片无法判断 → 转为不约束
    reduced.balanced = None
    # 首攻牌张白名单随出牌**递减**（针对剩余未出牌）：
    #   · lead_small_shapes（长四小牌首攻）——整手该花色 ≥4 张、>X 恰3 张。
    #     match 口径 total = 1(首攻) + 剩余，故出 1 张(首攻)后剩余≥3 → 条目下限 4；
    #     再出第2张 → 剩余≥2 → 条目下限 3；每多出1张下限-1。
    #     >X 张数：初始恰3，已出该花色中 >X 的张数扣减（出<X 不变，出>X 递减）。
    #   · lead_shape（顶张大牌白名单）——同随出牌递减（见下）。
    if reduced.lead_small_shapes is not None:
        _ls_suit, _ls_rank, _ls_entries = reduced.lead_small_shapes
        n_played_suit = played_suit.get(_ls_suit, 0)
        if n_played_suit > 1:
            _lead_rv = _rank_value_of(_ls_rank)
            _above_played = sum(
                1 for _c in (played_cards or [])
                if _c.suit == _ls_suit and _rank_value_of(_c.rank) > _lead_rv
            )
            # 条目下限：整手≥4 → match(total=1+剩余) ≥ 4 - 已出 + 1
            new_min = 4 - n_played_suit + 1
            # >X 剩余张数：恰3 - 已出>X
            new_above = max(0, 3 - _above_played)
            if new_min <= 1 or new_above == 0:
                # 该花色已基本出尽或 >X 大牌已全部打出 → 首攻推断信息用尽 → 释放
                reduced.lead_small_shapes = None
            else:
                reduced.lead_small_shapes = (
                    _ls_suit, _ls_rank,
                    [(new_min, 13, new_above, new_above, 0, 99)],
                )
        # 已出 1 张（仅首攻）→ 原样保留，约束仍为"≥4 恰3张>X"
    #   · lead_shape（顶张大牌白名单）——随出牌**递减**（用户原则）：首攻牌一
    #     出即从各形态大牌集剔除（剩余口径，如 KQ小≥N → Q小≥N），后续已出大牌
    #     同样剔除、已出小牌从张数区间扣减；所有形态失效则释放。
    #     match_suit_shape 按"形态是否仍含首攻牌"自动区分完整/剩余口径。
    for _attr in ("lead_shape",):
        _ls = getattr(reduced, _attr)
        if _ls is not None:
            _ls_suit, _ls_lead, _ls_entries = _ls
            if played_suit.get(_ls_suit, 0) >= 1:
                lead_rv = _rank_value_of(_ls_lead)
                extra_bigs = set()
                played_small = 0
                for _c in (played_cards or []):
                    if _c.suit != _ls_suit:
                        continue
                    if _rank_value_of(_c.rank) == lead_rv:
                        extra_bigs.add(_c.rank)  # 首攻牌已出 → 从形态剔除
                    elif _c.rank in ("A", "K", "Q", "J", "T"):
                        extra_bigs.add(_c.rank)
                    else:
                        played_small += 1
                new_entries = []
                for (_bigs, _smin, _smax) in _ls_entries:
                    nb = _bigs - extra_bigs
                    ns_min = max(0, _smin - played_small)
                    ns_max = _smax - played_small
                    if ns_max >= ns_min:
                        # nb 允许为空：形态大牌全出后 = 剩余无大牌 + 张数区间
                        new_entries.append((nb, ns_min, ns_max))
                if new_entries:
                    setattr(reduced, _attr, (_ls_suit, _ls_lead, new_entries))
                else:
                    setattr(reduced, _attr, None)
    if _constraint_trivially_satisfied(reduced, remaining_count):
        return None
    return reduced


_fallback_last_ts: Dict[str, float] = {}
_fallback_lock = threading.Lock()
_FALLBACK_MIN_INTERVAL = 0.5  # 同一级回退日志最小写间隔（秒），防止逐世界刷盘


def _warn_fallback(level: str, known_info: dict, constraints: dict) -> None:
    """记录约束降级日志（按级别节流，避免每个世界都往调试日志追加一行）。"""
    try:
        with _fallback_lock:
            now = time.monotonic()
            if now - _fallback_last_ts.get(level, 0.0) < _FALLBACK_MIN_INTERVAL:
                return
            _fallback_last_ts[level] = now
        pos_list = [p for p in POSITION_ORDER if p not in known_info.get("result", {})]
        srcs = {}
        for p in pos_list:
            if p in constraints:
                srcs[p] = constraints[p].inference_source
        with open(_DEBUG_LOG, "a", encoding="utf-8") as _f:
            _f.write(f"[SAMPLER_FALLBACK] {level} sources={srcs}\n")
    except Exception:
        pass


class DealSampler:
    """从当前玩家视角采样未知手牌分布。

    Phase 0a: 使用均匀随机分配 + 分级硬约束验证回退链。
    不再使用 BeliefTracker 或加权粒子。
    """

    def __init__(self):
        self.constraints: Dict[str, BidConstraint] = {}
        self.belief_tracker = None  # 已废弃，保留属性向后兼容

    def set_constraints(self, constraints: Dict[str, BidConstraint]) -> None:
        self.constraints = constraints or {}

    def sample(self, state: PlayState, perspective: str) -> Dict[str, List[Card]]:
        """均匀采样一套与当前信息一致的手牌，等级约束验证。

        Phase 0a: 使用均匀随机分配 + 分级硬约束验证回退。
        """
        known_info = _extract_known_info(state, perspective)
        return self._sample_one(known_info, self.constraints)

    def sample_n(self, n: int, state: PlayState, perspective: str) -> List[Dict[str, List[Card]]]:
        """生成 n 个独立均匀样本（用于 DD/αμ 引擎）。

        提取一次 known_info，复用 n 次，避免每个样本重复扫描 state。
        """
        known_info = _extract_known_info(state, perspective)
        results = []
        for _ in range(n):
            results.append(self._sample_one(known_info, self.constraints))
        return results

    def _sample_one(
        self,
        known_info: dict,
        constraints_in: Dict[str, "BidConstraint"],
    ) -> Dict[str, List[Card]]:
        """单次采样（复用 known_info，不重复提取）。"""
        # 过滤：已知手牌的位置不验证（手牌由发牌固定，无法通过采样改变）
        known_positions = set(known_info.get("result", {}).keys())
        played_stats = known_info.get("played", {})
        remaining_counts = known_info.get("remaining_counts", {})
        # 中局扣减：把整手约束按已出牌折算为剩余部分约束，再用于验证
        active_constraints = {}
        played_by_pos = known_info.get("played_by_pos", {})
        for pos, c in constraints_in.items():
            if pos in known_positions:
                continue
            reduced = _reduce_constraint_for_played(
                c, played_stats.get(pos), remaining_counts.get(pos, 0),
                played_cards=played_by_pos.get(pos, []),
            )
            if reduced is None:
                continue
            active_constraints[pos] = reduced
        # 可满足性预检：约束在当前牌池下必不可能满足时，跳过 MH/L0 空转
        feasible = _check_feasible(active_constraints, known_info)
        if feasible:
            if active_constraints:
                # Level 0: MH 修复（从一次均匀发牌出发对称交换，无偏提速）
                world, ok = _sample_mh_repair(known_info, active_constraints)
                if ok:
                    return world
                _warn_fallback("L0→L1", known_info, self.constraints)
                ms_world = _sample_master_soft(known_info, active_constraints)
                if ms_world is not None:
                    _warn_fallback("L1_master_soft", known_info, self.constraints)
                    return ms_world
            else:
                return _sample_uniform(known_info)
        else:
            _warn_fallback("INFEASIBLE", known_info, self.constraints)
            ms_world = _sample_master_soft(known_info, active_constraints)
            if ms_world is not None:
                _warn_fallback("L1_master_soft", known_info, self.constraints)
                return ms_world
        # Level 2: 放宽约束
        _warn_fallback("L2_relaxed", known_info, self.constraints)
        for _attempt in range(50):
            world = _sample_uniform(known_info, active_constraints)
            if validate_relaxed(world, active_constraints):
                return world
        # Level 3: 仅 void
        _warn_fallback("L3_voids", known_info, self.constraints)
        for _attempt in range(20):
            world = _sample_uniform(known_info, active_constraints)
            if validate_voids_only(world, known_info["known_voids"]):
                return world
        # 兜底：选违反约束最少的候选世界（兜底降级保护）
        _warn_fallback("L4_FINAL", known_info, self.constraints)
        return _pick_least_violating(active_constraints, known_info)

