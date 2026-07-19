"""纯蒙特卡洛 + 双明手评估搜索。

采样后把当前墩牌加回手牌使四家张数相等，
deal.play(from_hand=True) 写入当前墩，
solve_board 求解并取期望值选最优出牌。
"""

import itertools
import math
import os
import time
from typing import Dict, List, Optional

from config import BASE_DIR
from bridge.play_types import Card, PlayState, PlayPhase, POSITION_ORDER, PARTNERS
from bridge.mcts.state_utils import (
    cards_to_hand_str, get_current_trick_state, POSITION_TO_PLAYER, PLAYER_TO_POSITION, SUIT_TO_DENOM,
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


# ── 显著性阈值 ──
# tricks 单次标准差经验值（桥牌 DD 评估中 tricks 的典型离散度）
_SIGMA_TRICKS = 2.2
# 显著性 Z 值（1.0 = 1σ ≈ 68% 置信，平衡灵敏度与噪声）
_Z_SCORE = 1.0


def _significance_threshold(n_samples: int) -> float:
    """根据采样数动态计算 avg 显著性阈值。

    阈值 = Z × √2 × σ / √N
    配对采样下差值标准差通常更小，此为保守上界。
    N=500→0.14, N=1000→0.10, N=2000→0.07
    """
    if n_samples <= 1:
        return 0.0  # 单次精确求解无需阈值
    return _Z_SCORE * math.sqrt(2) * _SIGMA_TRICKS / math.sqrt(n_samples)


def _compare_candidates(a_avg, a_rank_val, b_avg, b_rank_val, is_declarer_side, threshold):
    """比较两个候选牌。

    返回: 1 if a 优于 b, -1 if b 优于 a, 0 if 等价。
    分层决胜：
    1. avg 差距 > threshold → 显著差异，按 avg 方向决胜
       （庄家方取高，防守方取低）
    2. rank 不同 → 小牌优先（保留大牌结构/进张）
    3. rank 相同 → 回退到原始 avg（虽在阈值内属噪声，
       但仍比迭代顺序任意决定更合理）
    """
    diff = a_avg - b_avg
    if is_declarer_side:
        if diff > threshold:
            return 1   # a 显著更高（庄家方更优）
        if diff < -threshold:
            return -1  # b 显著更高
    else:
        if diff < -threshold:
            return 1   # a 显著更低（防守方更优）
        if diff > threshold:
            return -1  # b 显著更低
    # 平局：小牌优先（rank 值小 = 小牌）
    if a_rank_val < b_rank_val:
        return 1
    if a_rank_val > b_rank_val:
        return -1
    # rank 也相同：回退到原始 avg 方向（避免迭代顺序任意决定）
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

try:
    from endplay import Deal
    from endplay.dds import solve_board, solve_all_boards
    from endplay.types import Card as EpCard, Denom, Player, Rank
    ENDPLAY_AVAILABLE = True
except ImportError:
    ENDPLAY_AVAILABLE = False

_SUIT_MAP = {}
_RANK_MAP = {}
_DENOM_TO_SUIT = {}
_RANK_TO_CHAR = {}

if ENDPLAY_AVAILABLE:
    _SUIT_MAP = {"♠": Denom.spades, "♥": Denom.hearts, "♦": Denom.diamonds, "♣": Denom.clubs}
    _RANK_MAP = {r: getattr(Rank, "R" + r) for r in ["A", "K", "Q", "J", "T", "9", "8", "7", "6", "5", "4", "3", "2"]}
    _DENOM_TO_SUIT = {Denom.spades: "♠", Denom.hearts: "♥", Denom.diamonds: "♦", Denom.clubs: "♣"}
    _RANK_TO_CHAR = {getattr(Rank, "R" + c): c for c in ["A", "K", "Q", "J", "T", "9", "8", "7", "6", "5", "4", "3", "2"]}


def _to_ep(card: Card) -> EpCard:
    return EpCard(suit=_SUIT_MAP[card.suit], rank=_RANK_MAP[card.rank])


def _hands_to_pbn(hands: Dict[str, List[Card]]) -> str:
    parts = []
    for pos in ["北", "东", "南", "西"]:
        cards = hands.get(pos, [])
        hand_str = cards_to_hand_str(cards)
        suits = []
        for s in hand_str.split():
            if s and s != "-":
                s = s[1:] if s[0] in "♠♥♦♣" else s
            suits.append(s)
        while len(suits) < 4:
            suits.append("")
        suits = ["" if s == "-" else s for s in suits]
        parts.append(".".join(suits))
    return f"N:{' '.join(parts)}"


def _dd_eval_one_world(sampled, all_played, trick_cards, trick_leader,
                       playable, state, perspective, actual_turn, declarer, dummy,
                       trump, card_scores, weight, sample_idx):
    """对单个世界运行 solve_board，累加加权分到 card_scores。

    actual_turn: 真实出牌者（明手领出时 ≠ perspective，deal.first 必须用此值）
    """
    try:
        # 1. 安全网：移除已出牌
        for pos, card in all_played:
            if pos in sampled:
                sampled[pos] = [c for c in sampled[pos]
                                if not (c.suit == card.suit and c.rank == card.rank)]

        # 2. 检测重复牌
        if _has_duplicates(sampled):
            return

        # 3. 加回当前墩的牌
        for pos, card in trick_cards:
            sampled[pos].append(card)

        # 4. PBN → Deal → solve_board
        pbn = _hands_to_pbn(sampled)
        deal = Deal(pbn)
        deal.trump = SUIT_TO_DENOM.get(trump, Denom.nt)
        if trick_cards:
            deal.first = POSITION_TO_PLAYER.get(trick_leader, Player.north)
            for _pos, card in trick_cards:
                deal.play(_to_ep(card), from_hand=True)
        else:
            deal.first = POSITION_TO_PLAYER.get(actual_turn, Player.north)

        result = solve_board(deal)
        score_map = {}
        for ep_card, side_score in result:
            key = (_DENOM_TO_SUIT.get(ep_card.suit), _RANK_TO_CHAR.get(ep_card.rank))
            score_map[key] = side_score

        total_played = state.declarer_tricks + state.defender_tricks
        remaining_tricks = 13 - total_played
        curplayer_pos = PLAYER_TO_POSITION.get(deal.curplayer, actual_turn)
        curplayer_is_declarer = curplayer_pos in (declarer, dummy)

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
        pass  # 单个世界失败不阻塞整体流程


def _dd_eval_one_world_pure(world, all_played, trick_cards, trick_leader,
                            playable, state, perspective, actual_turn, declarer, dummy,
                            trump, weight):
    """纯函数版：返回 partial_scores dict，不修改共享状态，供并行调用。

    actual_turn: 真实出牌者（明手领出时 ≠ perspective，deal.first 必须用此值）
    返回: dict {str(card): {"weighted_sum": float, "total_weight": float,
                             "scores": list, "mn": int, "mx": int}}
           若失败返回 None。
    """
    try:
        # 深拷贝 world，避免修改原数据
        sampled = {pos: [Card(suit=c.suit, rank=c.rank) for c in hand]
                   for pos, hand in world.items()}

        # 1. 安全网：移除已出牌
        for pos, card in all_played:
            if pos in sampled:
                sampled[pos] = [c for c in sampled[pos]
                                if not (c.suit == card.suit and c.rank == card.rank)]

        # 2. 检测重复牌
        if _has_duplicates(sampled):
            return None

        # 3. 加回当前墩的牌
        for pos, card in trick_cards:
            sampled[pos].append(card)

        # 4. PBN → Deal → solve_board
        pbn = _hands_to_pbn(sampled)
        deal = Deal(pbn)
        deal.trump = SUIT_TO_DENOM.get(trump, Denom.nt)
        if trick_cards:
            deal.first = POSITION_TO_PLAYER.get(trick_leader, Player.north)
            for _pos, card in trick_cards:
                deal.play(_to_ep(card), from_hand=True)
        else:
            deal.first = POSITION_TO_PLAYER.get(actual_turn, Player.north)

        result = solve_board(deal)
        score_map = {}
        for ep_card, side_score in result:
            key = (_DENOM_TO_SUIT.get(ep_card.suit), _RANK_TO_CHAR.get(ep_card.rank))
            score_map[key] = side_score

        total_played = state.declarer_tricks + state.defender_tricks
        remaining_tricks = 13 - total_played
        curplayer_pos = PLAYER_TO_POSITION.get(deal.curplayer, actual_turn)
        curplayer_is_declarer = curplayer_pos in (declarer, dummy)

        partial = {}
        for card in playable:
            key = (card.suit, card.rank)
            target_tricks = score_map.get(key, 0)
            if curplayer_is_declarer:
                decl_side_tricks = target_tricks
            else:
                decl_side_tricks = remaining_tricks - target_tricks
            total = state.declarer_tricks + decl_side_tricks
            partial[str(card)] = {
                "weighted_sum": total * weight,
                "total_weight": weight,
                "scores": [total],
                "mn": total,
                "mx": total,
            }
        return partial

    except Exception:
        return None


def _merge_partial_scores(card_scores, partial):
    """将 partial scores 合并到 card_scores（线程安全由调用方保证）。"""
    if partial is None:
        return
    for card_key, p in partial.items():
        if card_key not in card_scores:
            continue
        stats = card_scores[card_key]
        stats["weighted_sum"] += p["weighted_sum"]
        stats["total_weight"] += p["total_weight"]
        stats["scores"].extend(p["scores"])
        stats["mn"] = min(stats["mn"], p["mn"])
        stats["mx"] = max(stats["mx"], p["mx"])


def _build_deal_for_world(world, all_played, trick_cards, trick_leader,
                          perspective, actual_turn, trump):
    """从粒子 world 构建 endplay Deal（移除已出牌、加回当前墩、设置 trump/first）。

    actual_turn: 真实出牌者（明手领出时 ≠ perspective，deal.first 必须用此值）
    返回 (Deal, sampled) 或 (None, None) 表示构建失败（重复牌等）。
    """
    # 深拷贝 world
    sampled = {pos: [Card(suit=c.suit, rank=c.rank) for c in hand]
               for pos, hand in world.items()}
    # 1. 安全网：移除已出牌
    for pos, card in all_played:
        if pos in sampled:
            sampled[pos] = [c for c in sampled[pos]
                            if not (c.suit == card.suit and c.rank == card.rank)]
    # 2. 检测重复牌
    if _has_duplicates(sampled):
        return None, None
    # 3. 加回当前墩的牌
    for pos, card in trick_cards:
        sampled[pos].append(card)
    # 4. PBN → Deal
    pbn = _hands_to_pbn(sampled)
    deal = Deal(pbn)
    deal.trump = SUIT_TO_DENOM.get(trump, Denom.nt)
    if trick_cards:
        deal.first = POSITION_TO_PLAYER.get(trick_leader, Player.north)
        for _pos, card in trick_cards:
            deal.play(_to_ep(card), from_hand=True)
    else:
        deal.first = POSITION_TO_PLAYER.get(actual_turn, Player.north)
    return deal, sampled


def _solve_batch(samples, all_played, trick_cards, trick_leader,
                 playable, state, perspective, actual_turn, declarer, dummy,
                 trump, card_scores, time_limit, start_time):
    """用 solve_all_boards 批量求解所有样本，累加结果到 card_scores。

    Phase 0a: samples 是均匀无偏样本（等权 weight=1.0）。

    solve_all_boards 的 C 库硬限制 MAXNOOFBOARDS=200，所以分批处理，每批 ≤ 200。
    返回 (samples_done, solve_times_list, solve_total, solve_max)。
    """
    import time as _time
    _BATCH_SIZE = 200  # endplay C 库 MAXNOOFBOARDS 限制

    # 1. 构建所有 Deal（均匀采样：所有样本等权）
    deals = []
    for idx, world in enumerate(samples):
        if _time.time() - start_time > time_limit:
            break
        deal, _sampled = _build_deal_for_world(world, all_played, trick_cards,
                                                trick_leader, perspective, actual_turn, trump)
        if deal is not None:
            deals.append(deal)

    if not deals:
        return 0, [], 0.0, 0.0

    total_played = state.declarer_tricks + state.defender_tricks
    remaining_tricks = 13 - total_played
    solve_times = []
    solve_total = 0.0
    solve_max = 0.0
    samples_done = 0
    batch_count = 0

    # 2. 分批求解（每批 ≤ 200），所有样本等权
    for batch_start in range(0, len(deals), _BATCH_SIZE):
        if _time.time() - start_time > time_limit:
            break
        batch_end = min(batch_start + _BATCH_SIZE, len(deals))
        batch_deals = deals[batch_start:batch_end]
        _t_batch = _time.time()
        try:
            solved_list = solve_all_boards(batch_deals)
            _dt_batch = _time.time() - _t_batch
            solve_total += _dt_batch
            _per_deal = _dt_batch / max(len(batch_deals), 1)
            if _per_deal > solve_max:
                solve_max = _per_deal
            batch_count += 1
            # 累加结果（等权 weight=1.0）
            for i, solved in enumerate(solved_list):
                deal = batch_deals[i]
                score_map = {}
                for ep_card, side_score in solved:
                    key = (_DENOM_TO_SUIT.get(ep_card.suit), _RANK_TO_CHAR.get(ep_card.rank))
                    score_map[key] = side_score
                curplayer_pos = PLAYER_TO_POSITION.get(deal.curplayer, actual_turn)
                curplayer_is_declarer = curplayer_pos in (declarer, dummy)
                for card in playable:
                    key = (card.suit, card.rank)
                    target_tricks = score_map.get(key, 0)
                    if curplayer_is_declarer:
                        decl_side_tricks = target_tricks
                    else:
                        decl_side_tricks = remaining_tricks - target_tricks
                    total = state.declarer_tricks + decl_side_tricks
                    stats = card_scores[str(card)]
                    stats["weighted_sum"] += total  # weight=1.0
                    stats["total_weight"] += 1.0
                    stats["scores"].append(total)
                    stats["mn"] = min(stats["mn"], total)
                    stats["mx"] = max(stats["mx"], total)
                samples_done += 1
                solve_times.append(_per_deal)
        except Exception as _e:
            # 批失败：诊断第一个 Deal
            with open(_DEBUG_LOG, "a", encoding="utf-8") as _f:
                _f.write(f"[BATCH_FAIL] batch#{batch_count} start={batch_start} "
                         f"size={len(batch_deals)} reason={type(_e).__name__}: {_e}\n")
                if batch_deals:
                    try:
                        _f.write(f"  deal[0] pbn={batch_deals[0].to_pbn()} "
                                 f"trump={batch_deals[0].trump} first={batch_deals[0].first}\n")
                    except Exception:
                        pass
            # 该批降级到串行（等权）
            for i, deal in enumerate(batch_deals):
                if _time.time() - start_time > time_limit:
                    break
                _t_s = _time.time()
                try:
                    result = solve_board(deal)
                except Exception:
                    continue
                _dt_s = _time.time() - _t_s
                solve_total += _dt_s
                if _dt_s > solve_max:
                    solve_max = _dt_s
                score_map = {}
                for ep_card, side_score in result:
                    key = (_DENOM_TO_SUIT.get(ep_card.suit), _RANK_TO_CHAR.get(ep_card.rank))
                    score_map[key] = side_score
                curplayer_pos = PLAYER_TO_POSITION.get(deal.curplayer, actual_turn)
                curplayer_is_declarer = curplayer_pos in (declarer, dummy)
                for card in playable:
                    key = (card.suit, card.rank)
                    target_tricks = score_map.get(key, 0)
                    if curplayer_is_declarer:
                        decl_side_tricks = target_tricks
                    else:
                        decl_side_tricks = remaining_tricks - target_tricks
                    total = state.declarer_tricks + decl_side_tricks
                    stats = card_scores[str(card)]
                    stats["weighted_sum"] += total  # weight=1.0
                    stats["total_weight"] += 1.0
                    stats["scores"].append(total)
                    stats["mn"] = min(stats["mn"], total)
                    stats["mx"] = max(stats["mx"], total)
                samples_done += 1
                solve_times.append(_dt_s)

    with open(_DEBUG_LOG, "a", encoding="utf-8") as _f:
        _f.write(f"[BATCH] total_deals={samples_done} batches_ok={batch_count} "
                 f"batch_total={solve_total:.2f}s "
                 f"per_deal_avg={solve_total*1000/max(samples_done,1):.1f}ms\n")
    return samples_done, solve_times, solve_total, solve_max


class DDSearch:

    def __init__(self, sampler: DealSampler = None, num_samples: int = 100,
                 min_samples: int = 15, time_limit: float = 5.0,
                 endgame_card_threshold: int = 10, max_enumerations: int = 5000,
                 use_maximin: bool = True):
        if not ENDPLAY_AVAILABLE:
            raise RuntimeError("endplay library not available (pip install endplay)")
        self.sampler = sampler or DealSampler()
        self.num_samples = num_samples
        self.min_samples = min_samples
        self.time_limit = time_limit
        self.endgame_card_threshold = endgame_card_threshold
        self.max_enumerations = max_enumerations
        self.use_maximin = use_maximin

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

        start_time = time.time()
        samples_done = 0
        _solve_total = 0.0
        _solve_max = 0.0
        _solve_count = 0

        # 批量求解优先：solve_all_boards 内部用线程池加速，dds C 库自管理线程安全
        # 失败时降级到串行 solve_board
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
        else:
            # samples 已在上面生成，跳过
            pass

        elapsed = time.time() - start_time
        _solve_avg = (_solve_total / _solve_count) if _solve_count > 0 else 0.0
        print(f"[DD] 全量模式完成: {samples_done} 世界, {elapsed:.1f}s"
              f"{' (信念加权)' if particles else ' (纯约束等权)'} "
              f"solve_avg={_solve_avg:.3f}s solve_max={_solve_max:.3f}s "
              f"solve_total={_solve_total:.1f}s prepare={_prepare_t:.2f}s")
        with open(_DEBUG_LOG, "a", encoding="utf-8") as _f:
            _f.write(f"[DD] 完成: {samples_done}世界 {elapsed:.1f}s "
                     f"solve_avg={_solve_avg:.3f}s solve_max={_solve_max:.3f}s "
                     f"solve_total={_solve_total:.1f}s prepare={_prepare_t:.2f}s\n")

        best_card = None
        best_blended = None
        best_rank_val = None
        child_stats = []
        use_maximin = getattr(self, 'use_maximin', True)

        # 计算显著性阈值（与采样数匹配）
        _first_scores = card_scores[str(playable[0])]["scores"] if playable else []
        _threshold = _significance_threshold(len(_first_scores))

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
            })

            rank_val = RANK_ORDER.get(card.rank, 0)

            if use_maximin:
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

            # 显著性比较：avg 差距 < 阈值视为平局，小牌优先
            if best_card is None or _compare_candidates(blended, rank_val, best_blended, best_rank_val, is_declarer_side, _threshold) > 0:
                best_card = card
                best_blended = blended
                best_rank_val = rank_val

        from functools import cmp_to_key
        child_stats.sort(key=cmp_to_key(
            lambda a, b: -_compare_candidates(
                a["avg_tricks"], _card_rank_val(a["card"]),
                b["avg_tricks"], _card_rank_val(b["card"]),
                is_declarer_side, _threshold
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
            remaining_counts[pos] = 13 - self.sampler._count_played(state, pos)

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
        constraints = self.sampler.constraints

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
                    # 加回当前墩牌
                    for pos, card in trick_cards:
                        hands[pos].append(card)

                    # PBN → Deal → solve_board
                    pbn = _hands_to_pbn(hands)
                    deal = Deal(pbn)
                    deal.trump = SUIT_TO_DENOM.get(trump, Denom.nt)

                    if trick_cards:
                        deal.first = POSITION_TO_PLAYER.get(trick_leader, Player.north)
                        for _pos, card in trick_cards:
                            deal.play(_to_ep(card), from_hand=True)
                    else:
                        deal.first = POSITION_TO_PLAYER.get(actual_turn, Player.north)

                    result = solve_board(deal)
                    score_map = {}
                    for ep_card, side_score in result:
                        key = (_DENOM_TO_SUIT.get(ep_card.suit),
                               _RANK_TO_CHAR.get(ep_card.rank))
                        score_map[key] = side_score

                    curplayer_pos = PLAYER_TO_POSITION.get(deal.curplayer, actual_turn)
                    curplayer_is_declarer = curplayer_pos in (declarer, dummy)

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
        best_rank_val = None
        child_stats = []

        # 计算显著性阈值（与采样数匹配）
        _first_scores = card_scores[str(playable[0])] if playable else []
        _threshold = _significance_threshold(len(_first_scores))

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
            })
            rank_val = RANK_ORDER.get(card.rank, 0)
            # 残局枚举同样适用 maximin（精确分布下 min 更可靠）
            if getattr(self, 'use_maximin', True):
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
            # 显著性比较：avg 差距 < 阈值视为平局，小牌优先
            if best_card is None or _compare_candidates(blended, rank_val, best_blended, best_rank_val, is_declarer_side, _threshold) > 0:
                best_blended = blended
                best_rank_val = rank_val
                best_card = card

        from functools import cmp_to_key
        child_stats.sort(key=cmp_to_key(
            lambda a, b: -_compare_candidates(
                a["avg_tricks"], _card_rank_val(a["card"]),
                b["avg_tricks"], _card_rank_val(b["card"]),
                is_declarer_side, _threshold
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
        """全知双明手搜索：AI 知道四家手牌，一次 solve_board 得所有候选精确分。

        与 search() 不同，此方法不采样，直接使用 state.hands 中的全部手牌。
        每次出牌只需一次 solve_board 调用，极快且确定。
        """
        if not ENDPLAY_AVAILABLE:
            raise RuntimeError("endplay 库不可用，无法运行完美DD搜索")

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

        # 移除当前墩已打出的牌（避免 PBN 中重复，之后通过 deal.play 重放）
        for pos, card in trick_cards:
            hands[pos] = [c for c in hands[pos]
                          if not (c.suit == card.suit and c.rank == card.rank)]
        # 加回当前墩牌（PBN 构建用）
        for pos, card in trick_cards:
            hands[pos].append(card)

        pbn = _hands_to_pbn(hands)
        deal = Deal(pbn)
        deal.trump = SUIT_TO_DENOM.get(trump, Denom.nt)

        if trick_cards:
            deal.first = POSITION_TO_PLAYER.get(trick_leader, Player.north)
            for _pos, card in trick_cards:
                deal.play(_to_ep(card), from_hand=True)
        else:
            deal.first = POSITION_TO_PLAYER.get(actual_turn, Player.north)

        result = solve_board(deal)
        score_map = {}
        for ep_card, side_score in result:
            key = (_DENOM_TO_SUIT.get(ep_card.suit),
                   _RANK_TO_CHAR.get(ep_card.rank))
            score_map[key] = side_score

        curplayer_pos = PLAYER_TO_POSITION.get(deal.curplayer, actual_turn)
        curplayer_is_declarer = curplayer_pos in (declarer, dummy)

        best_card = None
        best_blended = None
        best_rank_val = None
        child_stats = []
        _threshold = 0.0  # Perfect DD 是精确值，无需显著性阈值

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
            })
            rank_val = RANK_ORDER.get(card.rank, 0)
            # 显著性比较：精确值 threshold=0，平局时小牌优先
            if best_card is None or _compare_candidates(total, rank_val, best_blended, best_rank_val, is_declarer_side, _threshold) > 0:
                best_blended = total
                best_rank_val = rank_val
                best_card = card

        from functools import cmp_to_key
        child_stats.sort(key=cmp_to_key(
            lambda a, b: -_compare_candidates(
                a["avg_tricks"], _card_rank_val(a["card"]),
                b["avg_tricks"], _card_rank_val(b["card"]),
                is_declarer_side, _threshold
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
