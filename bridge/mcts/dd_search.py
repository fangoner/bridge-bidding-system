"""纯蒙特卡洛 + 双明手评估搜索 (Phase 0b: DirectDDS)。

均匀采样未知手牌，批量 DDS 求解候选出牌的期望赢墩。
"""

import itertools
import math
import os
import time
from typing import Dict, List, Optional

from config import BASE_DIR
from bridge.play_types import Card, PlayState, PlayPhase, POSITION_ORDER, PARTNERS
from bridge.mcts.state_utils import (
    get_current_trick_state,
)
from bridge.mcts.sampler import DealSampler, ALL_CARDS
from bridge.mcts.constraints import validate_sample

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


def _dd_eval_one_world(world, all_played, trick_cards, trick_leader,
                       playable, state, perspective, actual_turn, declarer, dummy,
                       trump, card_scores, weight, sample_idx):
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
        for card in playable:
            key = (card.suit, card.rank)
            target_tricks = score_map.get(key, 0)
            if curplayer_is_declarer:
                decl_side_tricks = target_tricks
            else:
                decl_side_tricks = remaining_tricks - target_tricks
            total = state.declarer_tricks + decl_side_tricks
            stats = card_scores[str(card)]
            stats["weighted_sum"] += total * weight
            stats["total_weight"] += weight
            stats["scores"].append(total)
            stats["mn"] = min(stats["mn"], total)
            stats["mx"] = max(stats["mx"], total)
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
                 trump, card_scores, time_limit, start_time):
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

                for card in playable:
                    key = (card.suit, card.rank)
                    target_tricks = score_map.get(key, 0)
                    if curplayer_is_declarer:
                        decl_side_tricks = target_tricks
                    else:
                        decl_side_tricks = remaining_tricks - target_tricks
                    total = state.declarer_tricks + decl_side_tricks
                    stats = card_scores[str(card)]
                    stats["weighted_sum"] += total
                    stats["total_weight"] += 1.0
                    stats["scores"].append(total)
                    stats["mn"] = min(stats["mn"], total)
                    stats["mx"] = max(stats["mx"], total)
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
                for card in playable:
                    key = (card.suit, card.rank)
                    target_tricks = score_map.get(key, 0)
                    if curplayer_is_declarer:
                        decl_side_tricks = target_tricks
                    else:
                        decl_side_tricks = remaining_tricks - target_tricks
                    total = state.declarer_tricks + decl_side_tricks
                    stats = card_scores[str(card)]
                    stats["weighted_sum"] += total
                    stats["total_weight"] += 1.0
                    stats["scores"].append(total)
                    stats["mn"] = min(stats["mn"], total)
                    stats["mx"] = max(stats["mx"], total)
                samples_done += 1
                solve_times.append(_dt_s)

    return samples_done, solve_times, solve_total, solve_max


class DDSearch:

    def __init__(self, sampler: DealSampler = None, num_samples: int = 100,
                 min_samples: int = 15, time_limit: float = 5.0,
                 endgame_card_threshold: int = 4, max_enumerations: int = 5000,
                 use_maximin: bool = True, scoring_mode: Optional[str] = None):
        self.sampler = sampler or DealSampler()
        self.num_samples = num_samples
        self.min_samples = min_samples
        self.time_limit = time_limit
        self.endgame_card_threshold = endgame_card_threshold
        self.max_enumerations = max_enumerations
        self.use_maximin = use_maximin
        if scoring_mode is None:
            from config import DD_SCORING_MODE
            scoring_mode = DD_SCORING_MODE
        self.scoring_mode = scoring_mode

    def _decision_value(self, scores: List[int], state: PlayState):
        """按计分制返回决策值（从庄家方越优数值越高的视角）。
        imp/make_rate 覆盖默认 avg_tricks 逻辑；返回 None 表示走既有 avg/regret 逻辑。"""
        mode = self.scoring_mode
        if mode == "imp":
            vul_decl = _declarer_side_vulnerable(state.contract.declarer,
                                                 getattr(state, "vulnerability", "NV"))
            return _expected_imp_value(scores, state.contract, vul_decl)
        if mode == "make_rate":
            return _make_rate_value(scores, state.contract.tricks_needed)
        return None

    def search(self, state: PlayState) -> dict:
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

        # 残局判定：用剩余墩数（=每手牌数），与模式无关
        remaining_tricks = 13 - (state.declarer_tricks + state.defender_tricks)

        # 残局：尝试精确枚举所有分布
        if remaining_tricks <= self.endgame_card_threshold:
            enum_result = self._enumerate_endgame(state, perspective, actual_turn, playable,
                                                   declarer, dummy, trump, is_declarer_side)
            if enum_result is not None:
                return enum_result

        ratio = max(0, remaining_tricks / 13)
        adaptive_samples = int(self.min_samples + (self.num_samples - self.min_samples) * ratio)
        adaptive_samples = max(self.min_samples, min(self.num_samples, adaptive_samples))

        card_scores = {str(c): {"weighted_sum": 0.0, "total_weight": 0.0,
                                  "scores": [], "mn": float("inf"), "mx": -float("inf")}
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

        # Phase 0a: 均匀采样生成样本（替代旧 BeliefTracker）
        # P1-4 修复：时间预算从采样开始计时（原在采样后，约束难满足时采样耗时不受 30s 预算约束）
        start_time = time.time()
        samples = None  # List[Dict[str, List[Card]]]
        _prepare_t = 0.0
        _prep_t0 = time.time()
        samples = self.sampler.sample_n(adaptive_samples, state, perspective)
        _prepare_t = time.time() - _prep_t0
        _has_constraints = bool(self.sampler.constraints)
        _constraint_count = len(self.sampler.constraints) if self.sampler.constraints else 0
        print(f"[DD] 均匀采样: {len(samples)} 样本, "
              f"prepare={_prepare_t:.2f}s, "
              f"constraints={_has_constraints}({ _constraint_count }), "
              f"remaining_tricks={remaining_tricks}")
        with open(_DEBUG_LOG, "a", encoding="utf-8") as _f:
            _f.write(f"[DD] trick={13-remaining_tricks+1} samples={len(samples)} "
                     f"prepare={_prepare_t:.2f}s "
                     f"constraints={_has_constraints}({ _constraint_count }) "
                     f"remaining_tricks={remaining_tricks}\n")

        samples_done = 0
        _solve_total = 0.0
        _solve_max = 0.0
        _solve_count = 0

        # 批量求解优先：solve_all_boards 内部用线程池加速，dds C 库自管理线程安全
        # 失败时降级到串行 DDS
        _solve_times = []  # 所有粒子耗时，用于统计分布
        _batch_used = False
        if samples:
            # 尝试批量求解
            _t_batch_total = time.time()
            _bd, _bt, _bs_tot, _bs_max = _solve_batch(
                samples, all_played, trick_cards, trick_leader,
                playable, state, perspective, actual_turn, declarer, dummy,
                trump, card_scores, self.time_limit, start_time)
            if _bd > 0:
                # 批量成功
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
                for world in samples:
                    if time.time() - start_time > self.time_limit:
                        break
                    samples_done += 1
                    _t_s0 = time.time()
                    _dd_eval_one_world(world, all_played, trick_cards, trick_leader,
                                       playable, state, perspective, actual_turn, declarer, dummy,
                                       trump, card_scores, 1.0, samples_done)
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
              f"{' (均匀采样)'} "
              f"solve_avg={_solve_avg:.3f}s solve_max={_solve_max:.3f}s "
              f"solve_total={_solve_total:.1f}s prepare={_prepare_t:.2f}s")
        with open(_DEBUG_LOG, "a", encoding="utf-8") as _f:
            _f.write(f"[DD] 完成: {samples_done}世界 {elapsed:.1f}s "
                     f"solve_avg={_solve_avg:.3f}s solve_max={_solve_max:.3f}s "
                     f"solve_total={_solve_total:.1f}s prepare={_prepare_t:.2f}s\n")

        best_card = None
        best_blended = None
        best_scores = None
        best_rank_val = None
        child_stats = []
        blended_map = {}
        scores_map = {}
        use_maximin = getattr(self, 'use_maximin', True)

        for card in playable:
            stats = card_scores[str(card)]
            scores = stats["scores"]
            w_sum = stats["weighted_sum"]
            w_total = stats["total_weight"]
            # 加权平均（纯约束模式下所有 weight=1.0，退化为普通平均）
            w_avg = w_sum / w_total if w_total > 0 else 0.0
            mn = stats["mn"] if stats["mn"] != float("inf") else 0
            mx = stats["mx"] if stats["mx"] != -float("inf") else 0
            child_stats.append({
                "card": str(card),
                "samples": len(scores),
                "avg_tricks": round(w_avg, 2),
                "min_tricks": mn,
                "max_tricks": mx,
                "scores": scores,
            })

            rank_val = RANK_ORDER.get(card.rank, 0)

            scoring_val = self._decision_value(scores, state)
            if scoring_val is not None:
                blended = scoring_val
            elif use_maximin:
                from config import DD_REGRET_BASE
                declarer_tricks = state.declarer_tricks
                defender_tricks = state.defender_tricks
                tricks_needed = state.contract.tricks_needed
                remaining = 13 - (declarer_tricks + defender_tricks)

                if is_declarer_side:
                    margin = declarer_tricks + remaining - tricks_needed
                else:
                    tricks_to_beat = 14 - tricks_needed
                    margin = defender_tricks + remaining - tricks_to_beat

                if margin > 1:
                    regret_weight = DD_REGRET_BASE
                elif margin == 1:
                    regret_weight = DD_REGRET_BASE * 0.7
                elif margin == 0:
                    regret_weight = DD_REGRET_BASE * 0.4
                else:
                    regret_weight = 0.0

                blended = (1 - regret_weight) * w_avg + regret_weight * mn
            else:
                blended = w_avg

            blended_map[str(card)] = blended
            scores_map[str(card)] = scores

            # 配对差值检验：同 world 配对差值的样本标准差决定显著性阈值
            if best_card is None or _compare_candidates(blended, scores, rank_val, best_blended, best_scores, best_rank_val, is_declarer_side) > 0:
                best_card = card
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
            f"{s['card']}({s['avg_tricks']}[{s['min_tricks']}-{s['max_tricks']}])"
            for s in child_stats[:5]
        )
        reasoning = (
            f"DDMC: {samples_done} samples in {elapsed:.1f}s. "
            f"Top plays: {top_plays_str}"
        )

        return {
            "card": best_card,
            "reasoning": reasoning,
            "full_output": {
                "推荐出牌": str(best_card),
                "核心逻辑": reasoning,
                "候选对比": str(child_stats),
                "局面评估": (
                    f"DDMC searched {samples_done} samples in {elapsed:.1f}s"
                ),
                "mcts_stats": {
                    "iterations": samples_done,
                    "time_sec": round(elapsed, 2),
                    "iters_per_sec": round(samples_done / elapsed, 1) if elapsed > 0 else 0,
                    "adaptive_cap": self.num_samples,
                    "remaining_cards": remaining_tricks * 4,
                    "candidates": child_stats,
                },
            },
        }

    def _enumerate_endgame(self, state: PlayState, perspective: str, actual_turn: str,
                           playable: List[Card], declarer: str, dummy: str,
                           trump: str, is_declarer_side: bool) -> Optional[dict]:
        """残局精确枚举：枚举所有可能的未知牌分布，对每个做双明手求解。

        返回同 search() 的 dict 格式，若枚举不可行则返回 None（回退采样）。
        """
        start_time = time.time()

        # ── 1. 识别已知/未知位置和未知牌池 ──
        known_positions = {perspective}
        if dummy and state.phase != PlayPhase.LEAD:
            known_positions.add(dummy)
        if dummy and perspective in (declarer, dummy):
            known_positions.add(declarer)

        unknown_positions = [p for p in POSITION_ORDER if p not in known_positions]

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

        # ── 2. 估算枚举总数 ──
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

        # ── 3. 预计算共享状态 ──
        trick_state = get_current_trick_state(state)
        trick_cards = trick_state["cards"]
        trick_leader = trick_state.get("leader")

        all_played = []
        for trick in state.tricks:
            all_played.extend(trick.cards)
        all_played.extend(trick_cards)

        total_played_tricks = state.declarer_tricks + state.defender_tricks
        remaining_tricks = 13 - total_played_tricks

        card_scores = {str(c): [] for c in playable}
        # 残局枚举直接对真实剩余牌池穷举所有分布，无需用叫牌约束过滤。
        # 叫牌约束（如整手16HCP）针对发牌时13张手牌，残局剩余1-2张必然不满足，
        # 若在此验证会导致所有分布被过滤、枚举返回None，进而回退到同样错误的采样。
        constraints = None

        n_pool = len(pool)
        indices = list(range(n_pool))
        n1 = remaining_counts[unknown_positions[0]]
        enum_count = 0
        valid_count = 0

        # ── 4. 枚举所有分布 ──
        for combo1_idx in itertools.combinations(indices, n1):
            if time.time() - start_time > self.time_limit:
                break

            cards1 = [pool[i] for i in combo1_idx]
            combo1_set = set(combo1_idx)
            remaining_idx = [i for i in indices if i not in combo1_set]

            # 构建分布迭代器
            if len(unknown_positions) == 2:
                cards2 = [pool[i] for i in remaining_idx]
                distributions = [{unknown_positions[0]: cards1,
                                  unknown_positions[1]: cards2}]
            elif len(unknown_positions) == 3:
                n2 = remaining_counts[unknown_positions[1]]
                distributions = []
                for combo2_idx in itertools.combinations(remaining_idx, n2):
                    combo2_set = set(combo2_idx)
                    cards2 = [pool[i] for i in combo2_idx]
                    cards3 = [pool[i] for i in remaining_idx if i not in combo2_set]
                    distributions.append({unknown_positions[0]: cards1,
                                          unknown_positions[1]: cards2,
                                          unknown_positions[2]: cards3})
            else:
                # 1或4个未知位置（极端情况），回退
                return None

            for dist in distributions:
                enum_count += 1
                if time.time() - start_time > self.time_limit:
                    break

                # 构建完整四家手牌
                hands = {}
                for pos in known_positions:
                    hands[pos] = list(state.hands.get(pos, []))
                for pos, cards in dist.items():
                    hands[pos] = list(cards)

                # 约束验证
                if constraints:
                    if not validate_sample(hands, constraints):
                        continue
                valid_count += 1

                try:
                    # 安全网清除已出牌（只从打出位置移除）
                    for pos, card in all_played:
                        if pos in hands:
                            hands[pos] = [c for c in hands[pos]
                                          if not (c.suit == card.suit and c.rank == card.rank)]
                    # 验证无重复牌
                    if _has_duplicates(hands):
                        continue
                    # DDS: trick_cards 不能出现在 hands 中（否则 remainCards 与 currentTrickSuit 双重计算）
                    # all_played 已包含 trick_cards，上面已移除，不再加回

                    # Phase 0b: DirectDDS 替换 endplay
                    first_p = trick_leader if trick_cards else actual_turn
                    solved_list = solve_all_boards_raw([(hands, trump, first_p, trick_cards)])
                    if not solved_list or solved_list[0] is None:
                        continue
                    result = solved_list[0]
                    score_map = _dds_result_to_score_map(result)

                    _DD_POS = {'北': 0, '东': 1, '南': 2, '西': 3}
                    cur_p = (_DD_POS.get(first_p, 0) + len(trick_cards)) % 4
                    curplayer_is_declarer = cur_p in (_DD_POS.get(declarer, 2), _DD_POS.get(dummy, 0))

                    for card in playable:
                        key = (card.suit, card.rank)
                        target_tricks = score_map.get(key, 0)
                        if curplayer_is_declarer:
                            decl_side_tricks = target_tricks
                        else:
                            decl_side_tricks = remaining_tricks - target_tricks
                        total = state.declarer_tricks + decl_side_tricks
                        card_scores[str(card)].append(total)

                except Exception:
                    continue  # 跳过无效分布

            if time.time() - start_time > self.time_limit:
                break

        # ── 5. 汇总结果 ──
        elapsed = time.time() - start_time

        if not any(card_scores.values()):
            return None  # 无有效分布，回退采样

        best_card = None
        best_blended = None
        best_scores = None
        best_rank_val = None
        child_stats = []
        blended_map = {}
        scores_map = {}

        for card in playable:
            scores = card_scores[str(card)]
            avg = sum(scores) / len(scores) if scores else 0.0
            mn = min(scores) if scores else 0
            mx = max(scores) if scores else 0
            child_stats.append({
                "card": str(card),
                "samples": len(scores),
                "avg_tricks": round(avg, 2),
                "min_tricks": mn,
                "max_tricks": mx,
                "scores": scores,
            })
            rank_val = RANK_ORDER.get(card.rank, 0)
            # 残局枚举同样支持计分制决策；否则回退 maximin/avg
            scoring_val = self._decision_value(scores, state)
            if scoring_val is not None:
                blended = scoring_val
            elif getattr(self, 'use_maximin', True):
                from config import DD_REGRET_BASE
                declarer_tricks = state.declarer_tricks
                defender_tricks = state.defender_tricks
                tricks_needed = state.contract.tricks_needed
                remaining = 13 - (declarer_tricks + defender_tricks)
                if is_declarer_side:
                    margin = declarer_tricks + remaining - tricks_needed
                else:
                    tricks_to_beat = 14 - tricks_needed
                    margin = defender_tricks + remaining - tricks_to_beat
                if margin > 1:
                    regret_weight = DD_REGRET_BASE
                elif margin == 1:
                    regret_weight = DD_REGRET_BASE * 0.7
                elif margin == 0:
                    regret_weight = DD_REGRET_BASE * 0.4
                else:
                    regret_weight = 0.0
                blended = (1 - regret_weight) * avg + regret_weight * mn
            else:
                blended = avg
            blended_map[str(card)] = blended
            scores_map[str(card)] = scores
            # 配对差值检验：同分布配对差值的样本标准差决定显著性阈值
            if best_card is None or _compare_candidates(blended, scores, rank_val, best_blended, best_scores, best_rank_val, is_declarer_side) > 0:
                best_blended = blended
                best_scores = scores
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
            f"{s['card']}({s['avg_tricks']}[{s['min_tricks']}-{s['max_tricks']}])"
            for s in child_stats[:5]
        )
        reasoning = (
            f"DD-endgame: {enum_count} enumerations ({valid_count} valid) "
            f"in {elapsed:.1f}s. Top plays: {top_plays_str}"
        )

        return {
            "card": best_card,
            "reasoning": reasoning,
            "full_output": {
                "推荐出牌": str(best_card),
                "核心逻辑": reasoning,
                "候选对比": str(child_stats),
                "局面评估": (
                    f"DD-endgame enumerated {enum_count} distributions "
                    f"({valid_count} valid) in {elapsed:.1f}s"
                ),
                "mcts_stats": {
                    "iterations": enum_count,
                    "valid_distributions": valid_count,
                    "time_sec": round(elapsed, 2),
                    "remaining_cards": len(pool),
                    "candidates": child_stats,
                },
            },
        }

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
