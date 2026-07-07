import os
import random
import copy
from typing import Dict, List, Set, Optional, Tuple

from bridge.play_types import Card, PlayState, PlayPhase, POSITION_ORDER
from bridge.mcts.state_utils import clone_hands, SUIT_DISPLAY_ORDER, RANK_DESC
import math
from bridge.mcts.constraints import BidConstraint, validate_sample, compute_sample_violation_score, HCP_MAP, CONTROL_MAP
from bridge.mcts.belief import collect_voids, BeliefTracker


# 一副完整的52张牌
ALL_CARDS = [Card(suit=s, rank=r) for s in SUIT_DISPLAY_ORDER for r in RANK_DESC]

# 约束采样最大重试次数（_constrained_select 保证约束前提下仍保留重试安全网）
MAX_CONSTRAINT_RETRIES = 200  # 有约束时最多重试次数（提高约束命中率）

# 调试日志路径
_BASE_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
_DEBUG_LOG = os.path.join(_BASE_DIR, "dd_debug.log")

# 聚合计时器（_distribute_global_constrained 三步耗时统计，prepare 结束时输出）
_DIST_STATS = {"shape_t": 0.0, "hcp_t": 0.0, "assign_t": 0.0,
               "shape_calls": 0, "hcp_calls": 0, "assign_calls": 0,
               "shape_retries": 0, "hcp_retries": 0,
               "fallback_count": 0, "shape_cache_hits": 0}

# Shape 池缓存：同一 PlayState 下 N 个粒子复用 shape 模板，避免重复随机重试
# key = (unknown_positions tuple, targets tuple, pool_signature)
# value = list of shape dicts (候选模板)
_SHAPE_POOL = {}
_SHAPE_POOL_MAX = 20  # 每个键最多缓存20个候选shape
_SHAPE_POOL_TARGET = 10  # 首次生成时尝试产出10个候选
# 已确认约束硬冲突的 cache_key 集合：避免每个粒子重复跑 50 次外层重试
# 命中后直接走放宽约束分支，不再尝试 suit_min/exact_suit
_SHAPE_POOL_HARD_CONFLICT = set()

def reset_dist_stats():
    for k in _DIST_STATS:
        _DIST_STATS[k] = 0
    # 同时清空shape池（新PlayState或新prepare周期）
    _SHAPE_POOL.clear()
    _SHAPE_POOL_HARD_CONFLICT.clear()

def dump_dist_stats():
    """输出聚合计时到日志，只写1行"""
    s = _DIST_STATS
    if s["shape_calls"] == 0 and s["hcp_calls"] == 0 and s["assign_calls"] == 0:
        return
    with open(_DEBUG_LOG, "a", encoding="utf-8") as _f:
        _f.write(f"[DIST] shape={s['shape_t']:.2f}s/{s['shape_calls']}calls/{s['shape_retries']}retries "
                 f"cache_hits={s['shape_cache_hits']} "
                 f"hcp={s['hcp_t']:.2f}s/{s['hcp_calls']}calls/{s['hcp_retries']}retries "
                 f"assign={s['assign_t']:.2f}s/{s['assign_calls']}calls "
                 f"fallback={s['fallback_count']}\n")


class DealSampler:
    """从当前玩家视角采样未知手牌分布。

    每轮MCTS迭代前调用 sample()，返回完整4家手牌分配。
    支持叫牌约束过滤，提高采样质量。
    """

    def __init__(self):
        self.constraints: Dict[str, BidConstraint] = {}
        self.belief_tracker: Optional[BeliefTracker] = None  # 信念跟踪器（可选）

    def set_constraints(self, constraints: Dict[str, BidConstraint]) -> None:
        """设置叫牌约束，后续 sample() 会验证采样结果。

        Args:
            constraints: {position: BidConstraint} 映射
        """
        self.constraints = constraints or {}

    def set_belief_tracker(self, tracker: Optional[BeliefTracker]) -> None:
        """设置信念跟踪器，启用粒子滤波采样。"""
        self.belief_tracker = tracker

    def sample(self, state: PlayState, perspective: str) -> Dict[str, List[Card]]:
        """采样一套与当前信息一致且满足叫牌约束的完整手牌。

        若信念跟踪器已 prepare，则按权重从粒子集抽样；
        否则回退到约束验证 + 随机采样。

        Args:
            state: 当前PlayState
            perspective: 当前出牌者位置（"南"/"西"/"北"/"东"）

        Returns:
            完整4家手牌 Dict[str, List[Card]]
        """
        # 信念跟踪器路径：按权重抽样（粒子已在prepare阶段生成并加权）
        if self.belief_tracker is not None and self.belief_tracker.particles:
            return self.belief_tracker.draw()

        # 原始路径：约束验证 + 随机采样
        if self.constraints:
            # 判断是否是首攻前（完整手牌状态，所有位置13张牌）
            played_cards = sum(len(t.cards) for t in state.tricks) + len(state.current_trick.cards)
            is_opening = (played_cards == 0)
            
            if is_opening:
                # 首攻前：尝试多次满足硬约束（生成初始发牌）
                retries = MAX_CONSTRAINT_RETRIES
            else:
                # 中局阶段：剩余手牌不满足整手HCP/长度约束，少量尝试后即接受
                # 信念跟踪器会用软权重对违反约束的样本降权
                retries = 3
            
            for attempt in range(retries):
                result = self._sample_once(state, perspective)
                if validate_sample(result, self.constraints):
                    return result
            # 超过重试上限，直接返回一次采样结果（信念跟踪器软加权）
            return self._sample_once(state, perspective)
        return self._sample_once(state, perspective)

    def _sample_once(self, state: PlayState, perspective: str) -> Dict[str, List[Card]]:
        """采样一套与当前信息一致的完整手牌。

        Args:
            state: 当前PlayState
            perspective: 当前出牌者位置（"南"/"西"/"北"/"东"）

        Returns:
            完整4家手牌 Dict[str, List[Card]]
        """
        declarer = state.contract.declarer
        dummy = state.dummy
        is_declarer_side = perspective in (declarer, dummy)

        # 1. 收集已知牌张
        known_cards: Set[Card] = set()

        # 自己手牌
        own_hand = state.hands.get(perspective, [])
        known_cards.update(own_hand)

        # 庄家方视角：庄家和明手的手牌都已知且会被保留，必须全部加入 known_cards
        if is_declarer_side and dummy:
            known_cards.update(state.hands.get(declarer, []))
            known_cards.update(state.hands.get(dummy, []))
        elif dummy and perspective != dummy:
            # 防守方视角：首攻后明手可见
            if state.phase != PlayPhase.LEAD:
                known_cards.update(state.hands.get(dummy, []))

        # 已出牌张
        for trick in state.tricks:
            for _, card in trick.cards:
                known_cards.add(card)
        for _, card in state.current_trick.cards:
            known_cards.add(card)

        # 1.5 检测 state.hands 中是否有跨位置重复牌（数据完整性检查），发现则就地修复
        all_hand_cards = {}
        for pos in POSITION_ORDER:
            hand = state.hands.get(pos, [])
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
            if len(cleaned) != len(hand):
                state.hands[pos] = cleaned

        # 2. 计算每个位置剩余张数 = 13 - 已完成墩 - 该位置在当前墩已出牌
        # 当前墩牌已从 state.hands 移除，但必须从 remaining 中扣除，
        # 否则调用方加回当前墩牌后总数会超标（如 8+1=9 导致 Deal 报错）
        total_completed = state.declarer_tricks + state.defender_tricks
        base_remaining = 13 - total_completed
        remaining_counts = {}
        for pos in POSITION_ORDER:
            in_trick = sum(1 for p, _ in state.current_trick.cards if p == pos)
            remaining_counts[pos] = base_remaining - in_trick

        # 3. 未知牌张池
        unknown_pool = [c for c in ALL_CARDS if c not in known_cards]
        random.shuffle(unknown_pool)

        # 4. 已知位置的牌保留原样；手牌为空的位置不保留，留给后续填充
        result = {}
        if is_declarer_side and dummy:
            for pos in (declarer, dummy):
                hand = state.hands.get(pos, [])
                if hand:
                    result[pos] = [Card(suit=c.suit, rank=c.rank) for c in hand]
        else:
            if own_hand:
                result[perspective] = [Card(suit=c.suit, rank=c.rank) for c in own_hand]
            if dummy and state.phase != PlayPhase.LEAD:
                hand = state.hands.get(dummy, [])
                if hand:
                    result[dummy] = [Card(suit=c.suit, rank=c.rank) for c in hand]

        # 4.5 修正：确保已知手牌张数不超过 remaining_counts
        # 注意：actual < expected 是正常的（当前墩牌已从 state.hands 移除），
        # 不删除该位置——调用方（DD/αμ）会在 solve_board 前加回当前墩牌
        for pos in list(result.keys()):
            expected = remaining_counts.get(pos, 0)
            actual = len(result[pos])
            if actual > expected:
                # 牌太多：随机移除多余牌
                excess = actual - expected
                to_remove = random.sample(result[pos], excess)
                result[pos] = [c for c in result[pos] if c not in set(to_remove)]

        # 4.6 重建未知牌池（基于已分配牌 + 已出牌，保证一致性）
        assigned = set()
        for pos, cards in result.items():
            for c in cards:
                assigned.add((c.suit, c.rank))
        played_set = set()
        # 按位置统计已出牌的 HCP、控制数、各花色张数（用于约束扣减：初始约束 = 已出 + 剩余）
        played_hcp_per_pos = {p: 0 for p in POSITION_ORDER}
        played_controls_per_pos = {p: 0 for p in POSITION_ORDER}
        played_suit_per_pos = {p: {"♠": 0, "♥": 0, "♦": 0, "♣": 0} for p in POSITION_ORDER}
        for trick in state.tricks:
            for pos, c in trick.cards:
                played_set.add((c.suit, c.rank))
                played_hcp_per_pos[pos] = played_hcp_per_pos.get(pos, 0) + HCP_MAP.get(c.rank, 0)
                played_controls_per_pos[pos] = played_controls_per_pos.get(pos, 0) + CONTROL_MAP.get(c.rank, 0)
                if pos in played_suit_per_pos:
                    played_suit_per_pos[pos][c.suit] = played_suit_per_pos[pos].get(c.suit, 0) + 1
        for pos, c in state.current_trick.cards:
            played_set.add((c.suit, c.rank))
            played_hcp_per_pos[pos] = played_hcp_per_pos.get(pos, 0) + HCP_MAP.get(c.rank, 0)
            played_controls_per_pos[pos] = played_controls_per_pos.get(pos, 0) + CONTROL_MAP.get(c.rank, 0)
            if pos in played_suit_per_pos:
                played_suit_per_pos[pos][c.suit] = played_suit_per_pos[pos].get(c.suit, 0) + 1
        unknown_pool = [c for c in ALL_CARDS
                        if (c.suit, c.rank) not in assigned
                        and (c.suit, c.rank) not in played_set]

        # 5. 分配未知牌到未知位置（含手牌为空的位置）
        # 收集已知 void：void 位置不应收到 void 花色的牌
        known_voids = collect_voids(state)

        if self.constraints:
            _distribute_global_constrained(result, unknown_pool, remaining_counts, self.constraints, known_voids, played_set, played_hcp_per_pos, played_controls_per_pos, played_suit_per_pos)
        else:
            random.shuffle(unknown_pool)
            idx = 0
            for pos in POSITION_ORDER:
                if pos in result:
                    continue
                count = remaining_counts[pos]
                void_suits = known_voids.get(pos, set())
                result[pos] = []
                for _ in range(count):
                    # 跳过 void 花色的牌，找下一张合法牌
                    while idx < len(unknown_pool) and unknown_pool[idx].suit in void_suits:
                        idx += 1
                    if idx < len(unknown_pool):
                        result[pos].append(unknown_pool[idx])
                        idx += 1

        return result

    def _count_played(self, state: PlayState, position: str) -> int:
        """统计某位置已出牌张数"""
        count = 0
        for trick in state.tricks:
            for pos, _ in trick.cards:
                if pos == position:
                    count += 1
        for pos, _ in state.current_trick.cards:
            if pos == position:
                count += 1
        return count

    def _distribute_biased(
        self,
        result: Dict[str, List[Card]],
        pool: List[Card],
        remaining_counts: Dict[str, int],
        known_voids: Dict[str, Set[str]] = None,
    ) -> None:
        """保证约束的牌张分配：有约束的位置先分配，用 _constrained_select 满足HCP和花色下限。

        同时强制 void 约束：void 位置不收到 void 花色的牌。
        """
        known_voids = known_voids or {}
        # 按约束优先级排序：有实质性约束的位置优先分配
        unknown_positions = [p for p in POSITION_ORDER if p not in result]

        def _has_real_constraint(pos: str) -> bool:
            c = self.constraints.get(pos)
            if c is None:
                return False
            return (c.min_hcp is not None or c.max_hcp is not None or
                    c.balanced is not None or bool(c.suit_min))

        constrained_first = sorted(
            unknown_positions,
            key=lambda p: 0 if _has_real_constraint(p) else 1,
        )

        remaining = list(pool)

        for pos in constrained_first:
            count = remaining_counts[pos]
            if count <= 0 or not remaining:
                result[pos] = []
                continue

            # 过滤掉 void 花色的牌
            void_suits = known_voids.get(pos, set())
            if void_suits:
                available = [c for c in remaining if c.suit not in void_suits]
            else:
                available = remaining

            constraint = self.constraints.get(pos)

            if constraint is None:
                # 无约束：随机选（从 void 过滤后的池中）
                if count >= len(available):
                    result[pos] = list(available)
                    for c in result[pos]:
                        remaining.remove(c)
                else:
                    result[pos] = random.sample(available, count)
                    for c in result[pos]:
                        remaining.remove(c)
            else:
                # 有约束：保证满足约束的选取（从 void 过滤后的池中）
                result[pos] = self._constrained_select(available, count, constraint)
                for c in result[pos]:
                    remaining.remove(c)

    @staticmethod
    def _check_all_constraints(
        cards: List[Card],
        constraint: "BidConstraint",
        target_count: int = None,
    ) -> bool:
        """检查一手牌是否满足所有约束（HCP、花色长度、均型、控制数）"""
        if target_count is not None and len(cards) != target_count:
            return False

        hcp = sum(HCP_MAP.get(c.rank, 0) for c in cards)
        if constraint.min_hcp is not None and hcp < constraint.min_hcp:
            return False
        if constraint.max_hcp is not None and hcp > constraint.max_hcp:
            return False

        dist: Dict[str, int] = {"♠": 0, "♥": 0, "♦": 0, "♣": 0}
        for c in cards:
            dist[c.suit] = dist.get(c.suit, 0) + 1

        for suit, min_len in constraint.suit_min.items():
            if dist.get(suit, 0) < min_len:
                return False
        for suit, max_len in constraint.suit_max.items():
            if dist.get(suit, 0) > max_len:
                return False
        for suit, exact_len in constraint.exact_suit.items():
            if dist.get(suit, 0) != exact_len:
                return False

        if constraint.balanced is not None:
            if constraint.balanced:
                if any(d >= 6 for d in dist.values()):
                    return False
                if any(d <= 1 for d in dist.values()):
                    return False
            else:
                if all(2 <= d <= 5 for d in dist.values()) and not any(d >= 6 for d in dist.values()):
                    return False

        if constraint.min_controls is not None:
            controls = sum(CONTROL_MAP.get(c.rank, 0) for c in cards)
            if controls < constraint.min_controls:
                return False

        for (suit, rank) in constraint.specific_cards:
            if not any(c.suit == suit and c.rank == rank for c in cards):
                return False

        return True

    @staticmethod
    def _constrained_select_once(
        pool: List[Card],
        count: int,
        constraint: "BidConstraint",
        target_hcp: Optional[float],
    ) -> Tuple[List[Card], List[Card]]:
        """单次尝试选取满足基本约束的牌，返回 (selected, remaining)"""
        selected: List[Card] = []
        remaining: List[Card] = list(pool)

        # Step 0: 必须包含的特定牌张优先选取（specific_cards）
        for (suit, rank) in constraint.specific_cards:
            found = None
            for c in remaining:
                if c.suit == suit and c.rank == rank:
                    found = c
                    break
            if found is not None:
                selected.append(found)
                remaining.remove(found)

        # Step 1: 先满足精确张数约束（exact_suit）
        for suit, exact_len in constraint.exact_suit.items():
            if exact_len <= 0:
                continue
            suit_cards = [c for c in remaining if c.suit == suit]
            n_pick = min(exact_len, len(suit_cards))
            if n_pick <= 0:
                continue
            if target_hcp is not None:
                per_suit_target = target_hcp * 0.35
                target_per_card = per_suit_target / n_pick if n_pick > 0 else 0
                suit_cards_scored = []
                for c in suit_cards:
                    hcp = HCP_MAP.get(c.rank, 0)
                    score = -abs(hcp - target_per_card) + random.gauss(0, 1.5)
                    suit_cards_scored.append((score, c))
                suit_cards_scored.sort(key=lambda x: -x[0])
                picked = [c for _, c in suit_cards_scored[:n_pick]]
            else:
                random.shuffle(suit_cards)
                picked = suit_cards[:n_pick]
            selected.extend(picked)
            for c in picked:
                remaining.remove(c)

        # Step 2: 满足花色下限（suit_min），同时若balanced=True，限制任意花色不超过5张
        for suit, min_len in constraint.suit_min.items():
            current = sum(1 for c in selected if c.suit == suit)
            need_suit = max(0, min_len - current)
            if need_suit <= 0:
                continue
            suit_cards = [c for c in remaining if c.suit == suit]
            n_pick = min(need_suit, len(suit_cards))
            if n_pick > 0:
                suit_cards.sort(key=lambda c: -(HCP_MAP.get(c.rank, 0) * 0.6 + random.random() * 0.8))
                picked = suit_cards[:n_pick]
                selected.extend(picked)
                for c in picked:
                    remaining.remove(c)

        # Step 3: 处理花色上限——若balanced=True，强制各花色张数≤5
        effective_max = dict(constraint.suit_max)
        if constraint.balanced:
            for s in ("♠", "♥", "♦", "♣"):
                effective_max[s] = min(effective_max.get(s, 13), 5)

        # 过滤掉不能再选的花色
        allowed_remaining = []
        for c in remaining:
            current_in_suit = sum(1 for sc in selected if sc.suit == c.suit)
            max_in_suit = effective_max.get(c.suit, 13)
            if current_in_suit < max_in_suit:
                allowed_remaining.append(c)
        remaining = allowed_remaining

        # Step 4: 补满 count 张
        need = count - len(selected)
        if need > 0 and remaining:
            # 如果是均型牌，保证最终没有单张/缺门：补牌时优先给短套补牌
            if constraint.balanced:
                # 计算当前分布，先给最短的套（<2张）补牌
                dist: Dict[str, int] = {"♠": 0, "♥": 0, "♦": 0, "♣": 0}
                for c in selected:
                    dist[c.suit] = dist.get(c.suit, 0) + 1
                for _ in range(need):
                    dist = {"♠": 0, "♥": 0, "♦": 0, "♣": 0}
                    for c in selected:
                        dist[c.suit] = dist.get(c.suit, 0) + 1
                    # 找最短套（<2张优先），然后最短的套
                    short_suits = [s for s, d in dist.items() if d < 2]
                    if short_suits:
                        candidates = [c for c in remaining if c.suit in short_suits]
                    else:
                        min_len = min(dist.values())
                        candidates = [c for c in remaining if dist[c.suit] == min_len]
                    if not candidates:
                        candidates = remaining
                    # 从中按HCP目标选取
                    current_hcp = sum(HCP_MAP.get(c.rank, 0) for c in selected)
                    hcp_needed = (target_hcp or 10) - current_hcp
                    cards_needed = count - len(selected)
                    hcp_per = hcp_needed / cards_needed if cards_needed > 0 else 0
                    scored = []
                    for c in candidates:
                        hcp = HCP_MAP.get(c.rank, 0)
                        score = -abs(hcp - hcp_per) + random.gauss(0, 1.2)
                        scored.append((score, c))
                    scored.sort(key=lambda x: -x[0])
                    pick = scored[0][1]
                    selected.append(pick)
                    remaining.remove(pick)
            else:
                if target_hcp is not None:
                    current_hcp = sum(HCP_MAP.get(c.rank, 0) for c in selected)
                    hcp_needed_total = target_hcp - current_hcp
                    hcp_per_card = hcp_needed_total / need if need > 0 else 0
                    scored = []
                    for c in remaining:
                        hcp = HCP_MAP.get(c.rank, 0)
                        distance = abs(hcp - hcp_per_card)
                        score = -distance + random.gauss(0, 1.2)
                        scored.append((score, c))
                    scored.sort(key=lambda x: -x[0])
                    for _, c in scored[:need]:
                        selected.append(c)
                        remaining.remove(c)
                else:
                    random.shuffle(remaining)
                    picked = remaining[:need]
                    selected.extend(picked)
                    for c in picked:
                        remaining.remove(c)

        return selected, remaining

    @classmethod
    def _constrained_select(
        cls,
        pool: List[Card],
        count: int,
        constraint: "BidConstraint",
    ) -> List[Card]:
        """从 pool 中选 count 张牌，保证满足所有约束，且HCP分布符合自然概率。
        采用多次重试机制提高满足率。
        """
        if count >= len(pool):
            return list(pool)

        # 计算目标HCP中心值
        target_hcp = None
        if constraint.min_hcp_target is not None:
            target_hcp = constraint.min_hcp_target
        elif constraint.min_hcp is not None and constraint.max_hcp is not None:
            target_hcp = (constraint.min_hcp + constraint.max_hcp) / 2.0
        elif constraint.min_hcp is not None:
            target_hcp = constraint.min_hcp + 2
        elif constraint.max_hcp is not None:
            target_hcp = constraint.max_hcp - 2

        # 多次尝试找满足硬约束的手牌
        max_attempts = 20
        for attempt in range(max_attempts):
            # 每次尝试打乱pool顺序，增加随机性
            attempt_pool = list(pool)
            random.shuffle(attempt_pool)
            selected, remaining = cls._constrained_select_once(attempt_pool, count, constraint, target_hcp)

            # 微调：局部交换修正约束违反
            # 受保护的牌（specific_cards）不能被换出去
            protected = set((c.suit, c.rank) for c in selected if (c.suit, c.rank) in constraint.specific_cards)

            for _ in range(200):
                if cls._check_all_constraints(selected, constraint, count):
                    return selected

                current_hcp = sum(HCP_MAP.get(c.rank, 0) for c in selected)
                current_dist: Dict[str, int] = {"♠": 0, "♥": 0, "♦": 0, "♣": 0}
                for c in selected:
                    current_dist[c.suit] = current_dist.get(c.suit, 0) + 1

                swapped = False

                # 1. 修正HCP不足：换大牌进来（不换出受保护的牌）
                if constraint.min_hcp is not None and current_hcp < constraint.min_hcp:
                    low_cards = sorted(
                        [c for c in selected if (c.suit, c.rank) not in protected],
                        key=lambda c: HCP_MAP.get(c.rank, 0)
                    )
                    for low in low_cards:
                        low_hcp = HCP_MAP.get(low.rank, 0)
                        candidates = [c for c in remaining if HCP_MAP.get(c.rank, 0) > low_hcp]
                        random.shuffle(candidates)
                        for high in candidates:
                            trial = selected.copy()
                            trial.remove(low)
                            trial.append(high)
                            if cls._check_all_constraints(trial, constraint, count):
                                selected = trial
                                remaining.remove(high)
                                remaining.append(low)
                                swapped = True
                                break
                        if swapped:
                            break
                    if swapped:
                        continue

                # 2. 修正HCP过高：换小牌进来（不换出受保护的牌）
                if constraint.max_hcp is not None and current_hcp > constraint.max_hcp:
                    high_cards = sorted(
                        [c for c in selected if (c.suit, c.rank) not in protected],
                        key=lambda c: -HCP_MAP.get(c.rank, 0)
                    )
                    for high in high_cards:
                        high_hcp = HCP_MAP.get(high.rank, 0)
                        candidates = [c for c in remaining if HCP_MAP.get(c.rank, 0) < high_hcp]
                        random.shuffle(candidates)
                        for low in candidates:
                            trial = selected.copy()
                            trial.remove(high)
                            trial.append(low)
                            if cls._check_all_constraints(trial, constraint, count):
                                selected = trial
                                remaining.remove(low)
                                remaining.append(high)
                                swapped = True
                                break
                        if swapped:
                            break
                    if swapped:
                        continue

                # 3. 修正花色长度不满足（短套补牌/长套减牌）
                # 3a. suit_min不满足：某套不够张数，需要换该套牌进来
                for suit, min_len in constraint.suit_min.items():
                    if current_dist.get(suit, 0) < min_len:
                        out_candidates = [c for c in selected if c.suit != suit and (c.suit, c.rank) not in protected]
                        in_candidates = [c for c in remaining if c.suit == suit]
                        random.shuffle(out_candidates)
                        random.shuffle(in_candidates)
                        for out_c in out_candidates:
                            for in_c in in_candidates:
                                trial = selected.copy()
                                trial.remove(out_c)
                                trial.append(in_c)
                                if cls._check_all_constraints(trial, constraint, count):
                                    selected = trial
                                    remaining.remove(in_c)
                                    remaining.append(out_c)
                                    swapped = True
                                    break
                            if swapped:
                                break
                        if swapped:
                            break
                if swapped:
                    continue

                # 3b. suit_max不满足：某套太长，需要换其他套牌
                effective_max = dict(constraint.suit_max)
                if constraint.balanced:
                    for s in ("♠", "♥", "♦", "♣"):
                        effective_max[s] = min(effective_max.get(s, 13), 5)
                for suit, max_len in effective_max.items():
                    if current_dist.get(suit, 0) > max_len:
                        out_candidates = [c for c in selected if c.suit == suit and (c.suit, c.rank) not in protected]
                        in_candidates = [c for c in remaining if c.suit != suit]
                        random.shuffle(out_candidates)
                        random.shuffle(in_candidates)
                        for out_c in out_candidates:
                            for in_c in in_candidates:
                                trial = selected.copy()
                                trial.remove(out_c)
                                trial.append(in_c)
                                if cls._check_all_constraints(trial, constraint, count):
                                    selected = trial
                                    remaining.remove(in_c)
                                    remaining.append(out_c)
                                    swapped = True
                                    break
                            if swapped:
                                break
                        if swapped:
                            break
                if swapped:
                    continue

                # 3c. exact_suit不满足
                for suit, exact_len in constraint.exact_suit.items():
                    if current_dist.get(suit, 0) < exact_len:
                        out_candidates = [c for c in selected if c.suit != suit and (c.suit, c.rank) not in protected]
                        in_candidates = [c for c in remaining if c.suit == suit]
                        random.shuffle(out_candidates)
                        random.shuffle(in_candidates)
                        for out_c in out_candidates:
                            for in_c in in_candidates:
                                trial = selected.copy()
                                trial.remove(out_c)
                                trial.append(in_c)
                                if cls._check_all_constraints(trial, constraint, count):
                                    selected = trial
                                    remaining.remove(in_c)
                                    remaining.append(out_c)
                                    swapped = True
                                    break
                            if swapped:
                                break
                        if swapped:
                            break
                    elif current_dist.get(suit, 0) > exact_len:
                        out_candidates = [c for c in selected if c.suit == suit and (c.suit, c.rank) not in protected]
                        in_candidates = [c for c in remaining if c.suit != suit]
                        random.shuffle(out_candidates)
                        random.shuffle(in_candidates)
                        for out_c in out_candidates:
                            for in_c in in_candidates:
                                trial = selected.copy()
                                trial.remove(out_c)
                                trial.append(in_c)
                                if cls._check_all_constraints(trial, constraint, count):
                                    selected = trial
                                    remaining.remove(in_c)
                                    remaining.append(out_c)
                                    swapped = True
                                    break
                            if swapped:
                                break
                        if swapped:
                            break
                if swapped:
                    continue

                # 4. 修正均型牌约束：没有单张/缺门/6张套
                if constraint.balanced:
                    # 有缺门/单张：需要换牌
                    bad_suits = [s for s, d in current_dist.items() if d <= 1]
                    long_suits = [s for s, d in current_dist.items() if d >= 6]
                    if bad_suits or long_suits:
                        fix_suit = bad_suits[0] if bad_suits else long_suits[0]
                        need_longer = bool(bad_suits)
                        if need_longer:
                            out_candidates = [c for c in selected if c.suit != fix_suit
                                              and current_dist[c.suit] >= 3
                                              and (c.suit, c.rank) not in protected]
                            in_candidates = [c for c in remaining if c.suit == fix_suit]
                        else:
                            out_candidates = [c for c in selected if c.suit == fix_suit and (c.suit, c.rank) not in protected]
                            short_suits = [s for s, d in current_dist.items() if d <= 4 and s != fix_suit]
                            in_candidates = [c for c in remaining if c.suit in short_suits] if short_suits else [c for c in remaining if c.suit != fix_suit]
                        random.shuffle(out_candidates)
                        random.shuffle(in_candidates)
                        for out_c in out_candidates:
                            for in_c in in_candidates:
                                trial = selected.copy()
                                trial.remove(out_c)
                                trial.append(in_c)
                                if cls._check_all_constraints(trial, constraint, count):
                                    selected = trial
                                    remaining.remove(in_c)
                                    remaining.append(out_c)
                                    swapped = True
                                    break
                            if swapped:
                                break
                        if swapped:
                            continue

                # 5. 修正控制数不足（不换出受保护的牌）
                if constraint.min_controls is not None:
                    current_controls = sum(CONTROL_MAP.get(c.rank, 0) for c in selected)
                    if current_controls < constraint.min_controls:
                        low_control = [c for c in selected if CONTROL_MAP.get(c.rank, 0) == 0 and (c.suit, c.rank) not in protected]
                        high_control = [c for c in remaining if CONTROL_MAP.get(c.rank, 0) > 0]
                        random.shuffle(low_control)
                        random.shuffle(high_control)
                        for out_c in low_control:
                            for in_c in high_control:
                                trial = selected.copy()
                                trial.remove(out_c)
                                trial.append(in_c)
                                if cls._check_all_constraints(trial, constraint, count):
                                    selected = trial
                                    remaining.remove(in_c)
                                    remaining.append(out_c)
                                    swapped = True
                                    break
                            if swapped:
                                break
                        if swapped:
                            continue

                if not swapped:
                    break

            if cls._check_all_constraints(selected, constraint, count):
                return selected

        # 所有尝试都失败，返回最后一次结果（软约束会在信念权重中惩罚）
        return selected


# ============================================================
# 新的全局约束采样算法 v2
# 核心思想：先全局分配牌型+HCP，再按骨架填充牌张
# ============================================================

SUITS = ["♠", "♥", "♦", "♣"]


def _generate_valid_shape_distribution(
    constraints: Dict[str, BidConstraint],
    positions: List[str],
    target_counts: Dict[str, int],
    pool: List[Card] = None,
) -> Optional[Dict[str, Dict[str, int]]]:
    """生成合法的牌型分布：shape[pos][suit] = 张数

    约束满足：
    - 每家总张数 = target_counts[pos]
    - 每花色总张数 = pool中该花色的张数
    - 每个位置满足suit_min/suit_max/exact_suit约束
    - 如果constraint.balanced=True，满足均型牌型（无单张/缺门/6+张套）

    返回：{pos: {suit: count}} 或 None 如果生成失败
    """
    max_attempts = 60

    # 失败原因计数器（仅诊断用）
    _fail_reasons = {"step3": 0, "step4": 0, "total_mismatch": 0, "feasibility1": 0,
                     "feasibility2": 0, "no_candidates": 0, "final_validation": 0}

    # 计算牌池中每个花色实际有多少张
    suit_total = {s: 13 for s in SUITS}
    if pool is not None:
        suit_total = {s: 0 for s in SUITS}
        for c in pool:
            suit_total[c.suit] += 1

    # 一次性硬冲突预检：如果某花色 suit_min/exact_suit 之和 > 牌池该花色张数，
    # 不可能满足，直接返回 None（避免 60 次无意义重试）
    _lower_bound = {s: 0 for s in SUITS}
    for pos in positions:
        c = constraints.get(pos)
        if not c:
            continue
        for s in SUITS:
            if s in c.exact_suit:
                _lower_bound[s] += c.exact_suit[s]
            elif s in c.suit_min:
                _lower_bound[s] += c.suit_min[s]
    _hard_conflict_suits = [s for s in SUITS if _lower_bound[s] > suit_total[s]]
    if _hard_conflict_suits:
        # 约束硬冲突：suit_min/exact 之和超过牌池张数，无法生成合法 shape
        with open(_DEBUG_LOG, "a", encoding="utf-8") as _f:
            _f.write(f"[SHAPE_HARD_CONFLICT] suits={_hard_conflict_suits} "
                     f"lower_bound={_lower_bound} suit_total={suit_total} "
                     f"positions={positions} targets={target_counts}\n")
            for pos in positions:
                c = constraints.get(pos)
                if c:
                    _f.write(f"  {pos}: suit_min={dict(c.suit_min)} exact={dict(c.exact_suit)} "
                             f"suit_max={dict(c.suit_max)} balanced={c.balanced} "
                             f"src={c.inference_source}\n")
        return None

    # 预计算每家的 suit_max（含均型约束的 5 张上限）
    effective_max = {}
    for pos in positions:
        c = constraints.get(pos)
        em = {}
        for s in SUITS:
            mx = 13
            if c and s in c.suit_max:
                mx = c.suit_max[s]
            if c and c.balanced:
                mx = min(mx, 5)
            em[s] = mx
        effective_max[pos] = em

    for _ in range(max_attempts):
        shape = {pos: {s: 0 for s in SUITS} for pos in positions}
        valid = True

        # Step 1: 先填充exact_suit精确张数约束
        for pos in positions:
            c = constraints.get(pos)
            if not c:
                continue
            for suit, exact_len in c.exact_suit.items():
                shape[pos][suit] = exact_len

        # Step 2: 填充suit_min最低张数约束
        for pos in positions:
            c = constraints.get(pos)
            if not c:
                continue
            for suit, min_len in c.suit_min.items():
                if shape[pos][suit] < min_len:
                    shape[pos][suit] = min_len

        # Step 3: 验证每家当前总数不超过目标数
        for pos in positions:
            total = sum(shape[pos].values())
            if total > target_counts[pos]:
                valid = False
                break
        if not valid:
            _fail_reasons["step3"] += 1
            continue

        # Step 4: 验证每花色当前总数不超过牌池
        for s in SUITS:
            total = sum(shape[pos][s] for pos in positions)
            if total > suit_total[s]:
                valid = False
                break
        if not valid:
            _fail_reasons["step4"] += 1
            continue

        # Step 5: 随机填充剩余张数，保证每花色总数=suit_total[s]，每家总数=target
        remaining_by_pos = {pos: target_counts[pos] - sum(shape[pos].values()) for pos in positions}
        remaining_by_suit = {s: suit_total[s] - sum(shape[pos][s] for pos in positions) for s in SUITS}

        total_remaining = sum(remaining_by_pos.values())
        if total_remaining != sum(remaining_by_suit.values()):
            _fail_reasons["total_mismatch"] += 1
            continue
        if total_remaining < 0:
            _fail_reasons["total_mismatch"] += 1
            continue

        # 可行性预检：每家剩余需求 ≤ 该家各花色剩余可容纳空间之和
        feasible = True
        for pos in positions:
            if remaining_by_pos[pos] <= 0:
                continue
            capacity = 0
            for s in SUITS:
                room = effective_max[pos][s] - shape[pos][s]
                capacity += min(room, remaining_by_suit[s])
            if capacity < remaining_by_pos[pos]:
                feasible = False
                break
        if not feasible:
            _fail_reasons["feasibility1"] += 1
            continue

        # 每花色剩余供给 ≤ 能接收该花色的位置剩余需求之和
        for s in SUITS:
            if remaining_by_suit[s] <= 0:
                continue
            demand = 0
            for pos in positions:
                if remaining_by_pos[pos] <= 0:
                    continue
                room = effective_max[pos][s] - shape[pos][s]
                if room > 0:
                    demand += min(room, remaining_by_pos[pos])
            if demand < remaining_by_suit[s]:
                feasible = False
                break
        if not feasible:
            _fail_reasons["feasibility2"] += 1
            continue

        # 逐步随机分配剩余张数（约束引导：优先满足suit_min，关键牌强制分配）
        possible = True
        remaining_slots = total_remaining
        # 预计算每家每花色的剩余下限需求（= suit_min - 已分配）
        remaining_min = {}
        for pos in positions:
            c = constraints.get(pos)
            remaining_min[pos] = {}
            for s in SUITS:
                mn = c.suit_min.get(s, 0) if c else 0
                remaining_min[pos][s] = max(0, mn - shape[pos][s])

        for ___ in range(remaining_slots):
            # 早期剪枝：检查是否有"必须分配"的强制位置
            # 若某花色剩余供给 == 某位置该花色剩余下限需求，则强制分配给该位置
            forced = None
            for pos in positions:
                if remaining_by_pos[pos] <= 0:
                    continue
                for s in SUITS:
                    if remaining_min[pos][s] <= 0:
                        continue
                    if shape[pos][s] >= effective_max[pos][s]:
                        continue
                    # 该位置还需要 s 至少 remaining_min[pos][s] 张
                    # 若剩余供给恰好等于需求，或该位置剩余容量==需求，必须立即分配
                    capacity_left = remaining_by_pos[pos]
                    supply = remaining_by_suit[s]
                    if supply == remaining_min[pos][s] or capacity_left == remaining_min[pos][s]:
                        forced = (pos, s)
                        break
                if forced:
                    break

            if forced:
                pos, s = forced
            else:
                # 普通随机：但优先选择有 suit_min 需求的位置
                priority_candidates = []
                other_candidates = []
                for pos in positions:
                    if remaining_by_pos[pos] <= 0:
                        continue
                    for s in SUITS:
                        if remaining_by_suit[s] <= 0:
                            continue
                        if shape[pos][s] >= effective_max[pos][s]:
                            continue
                        if remaining_min[pos][s] > 0:
                            priority_candidates.append((pos, s))
                        else:
                            other_candidates.append((pos, s))
                candidates = priority_candidates if priority_candidates else other_candidates
            if not candidates:
                possible = False
                _fail_reasons["no_candidates"] += 1
                break
            pos, s = random.choice(candidates)

            shape[pos][s] += 1
            remaining_by_pos[pos] -= 1
            remaining_by_suit[s] -= 1
            if remaining_min[pos][s] > 0:
                remaining_min[pos][s] -= 1

        if not possible:
            continue  # no_candidates 已在 break 处计数

        # Step 6: 最终验证所有约束
        ok = True
        for pos in positions:
            c = constraints.get(pos)
            total = sum(shape[pos].values())
            if total != target_counts[pos]:
                ok = False
                break
            for s in SUITS:
                cnt = shape[pos][s]
                if cnt < 0:
                    ok = False
                if c:
                    if s in c.suit_min and cnt < c.suit_min[s]:
                        ok = False
                    if s in c.suit_max and cnt > c.suit_max[s]:
                        ok = False
                    if s in c.exact_suit and cnt != c.exact_suit[s]:
                        ok = False
            if c and c.balanced is not None:
                dist = list(shape[pos].values())
                # 中局阶段（target<13）放宽balanced下限：只保留上限5张和无6+张套
                # 因为剩余牌池可能某花色=0，无法满足每花色≥2
                if target_counts[pos] >= 13:
                    is_bal = all(2 <= d <= 5 for d in dist) and not any(d >= 6 for d in dist)
                else:
                    is_bal = all(d <= 5 for d in dist) and not any(d >= 6 for d in dist)
                if c.balanced and not is_bal:
                    ok = False
                # 注意：balanced=False（非均型）不应禁止均型分布，
                # 该约束语义是"不要求均型"而非"必须非均型"，故移除 is_bal 拒绝逻辑
        for s in SUITS:
            if sum(shape[pos][s] for pos in positions) != suit_total[s]:
                ok = False

        if ok:
            return shape
        _fail_reasons["final_validation"] += 1

    # 失败统计输出（只写1行）
    _total_fail = sum(_fail_reasons.values())
    if _total_fail > 0:
        with open(_DEBUG_LOG, "a", encoding="utf-8") as _f:
            _f.write(f"[SHAPE_FAIL] attempts={max_attempts} reasons={_fail_reasons} "
                     f"positions={positions} targets={target_counts} suit_total={suit_total}\n")
    return None


def _allocate_hcp_budget(
    constraints: Dict[str, BidConstraint],
    positions: List[str],
    pool: List[Card] = None,
) -> Optional[Dict[str, int]]:
    """分配HCP预算：给每家分配一个目标HCP值

    约束满足：
    - min_hcp[pos] ≤ hcp[pos] ≤ max_hcp[pos]
    - sum(hcp[pos] for unknown pos) = pool中牌的总HCP

    返回：{pos: target_hcp} 或 None 如果无法分配
    """
    max_attempts = 40

    # 计算牌池中总HCP
    total_hcp = 40
    if pool is not None:
        total_hcp = sum(HCP_MAP.get(c.rank, 0) for c in pool)

    # 预计算每家的 min/max 和目标中值
    # 软约束（不参与硬可行性检查，由 compute_sample_violation_score 软加权处理）：
    #   - negative_inference: 负推断（如"pass后≤7"）
    #   - hcp_conservation: 点力守恒推断（如"对家≤7则本家≥8"）
    # 只有用明确叫牌承诺（hard_coded/meaning_parsed/convention）的 HCP 约束做硬约束
    _SOFT_SOURCES = {"negative_inference", "hcp_conservation"}
    bounds = {}
    for pos in positions:
        c = constraints.get(pos)
        is_soft = bool(c and c.inference_source in _SOFT_SOURCES)
        # 软推断的 min_hcp 和 max_hcp 都视为软约束，不参与硬可行性检查
        # 只用明确叫牌承诺（hard_coded/meaning_parsed/convention）做硬约束
        mn = c.min_hcp if c and c.min_hcp is not None and not is_soft else 0
        if c and c.max_hcp is not None and not is_soft:
            mx = c.max_hcp
        else:
            mx = 37
        target = None
        if c and c.min_hcp_target is not None:
            target = c.min_hcp_target
        elif c and c.min_hcp is not None and c.max_hcp is not None:
            target = (c.min_hcp + c.max_hcp) // 2
        bounds[pos] = (mn, mx, target)

    # 可行性检查：最小值之和 ≤ total_hcp ≤ 最大值之和
    # 不可行说明约束互相矛盾（如负推断max过严），返回None让上层降级到 _distribute_biased
    sum_min = sum(bounds[p][0] for p in positions)
    sum_max = sum(bounds[p][1] for p in positions)
    if total_hcp < sum_min or total_hcp > sum_max:
        return None

    for _ in range(max_attempts):
        budgets = {}
        # 先给每家分配最小值
        remaining = total_hcp
        for pos in positions:
            budgets[pos] = bounds[pos][0]
            remaining -= bounds[pos][0]

        if remaining < 0:
            continue

        # 批量分配剩余 HCP：每家用目标中值作为权重，一次性抽取
        # 等价于逐点分配但避免了 N 次内层循环（N 可能 20+）
        if remaining > 0:
            # 计算每家还能接收多少 HCP
            room = {pos: bounds[pos][1] - budgets[pos] for pos in positions}
            # 用目标中值作为权重
            weights = []
            pos_list = []
            for pos in positions:
                if room[pos] <= 0:
                    continue
                target = bounds[pos][2]
                w = 1
                if target is not None:
                    w = max(1, 5 - abs(budgets[pos] + room[pos] // 2 - target))
                # 按权重扩展为多个名额（每个名额代表 1 点 HCP 容量）
                slots = min(room[pos], max(1, w * 3))
                weights.extend([pos] * slots)
                pos_list.append(pos)

            if not weights:
                # 所有人都已到上限，但还有剩余 HCP → 不可行
                continue

            # 一次性从 weights 中抽取 remaining 个（不重复抽取同一名额）
            if remaining <= len(weights):
                chosen = random.sample(weights, remaining)
            else:
                chosen = list(weights)
                # 不够则补充随机分配
                extra = remaining - len(chosen)
                for _ in range(extra):
                    # 找还有容量的位置
                    avail = [p for p in positions if budgets[p] + chosen.count(p) < bounds[p][1]]
                    if not avail:
                        break
                    chosen.append(random.choice(avail))

            for pos in chosen:
                if budgets[pos] < bounds[pos][1]:
                    budgets[pos] += 1

        total = sum(budgets.values())
        if total != total_hcp:
            continue

        # 验证所有约束
        ok = True
        for pos in positions:
            h = budgets[pos]
            mn, mx, _ = bounds[pos]
            if h < mn or h > mx:
                ok = False
                break
        if ok:
            return budgets

    return None


def _assign_cards_by_shape_and_hcp(
    pool: List[Card],
    shape: Dict[str, Dict[str, int]],
    hcp_targets: Dict[str, int],
    constraints: Dict[str, BidConstraint],
    positions: List[str],
) -> Dict[str, List[Card]]:
    """按给定牌型和HCP目标分配具体牌张
    
    Args:
        pool: 可用牌池（未知牌）
        shape: 牌型分布 {pos: {suit: count}}
        hcp_targets: HCP目标 {pos: hcp}
        constraints: 约束（用于specific_cards, min_controls等）
        positions: 位置列表
    
    Returns:
        {pos: [cards]}
    """
    result: Dict[str, List[Card]] = {pos: [] for pos in positions}
    remaining = list(pool)
    
    # Step 1: 先分配specific_cards必须持有的牌
    for pos in positions:
        c = constraints.get(pos)
        if not c:
            continue
        for (suit, rank) in c.specific_cards:
            for card in remaining:
                if card.suit == suit and card.rank == rank:
                    result[pos].append(card)
                    remaining.remove(card)
                    break
    
    # Step 2: 逐花色分配牌张，按HCP目标加权
    for suit in SUITS:
        suit_cards = [c for c in remaining if c.suit == suit]
        # 按HCP从大到小排序
        suit_cards.sort(key=lambda c: -HCP_MAP.get(c.rank, 0))
        
        # 计算每个位置在这个花色需要拿几张
        needed = {pos: shape[pos][suit] - sum(1 for c in result[pos] if c.suit == suit) for pos in positions}
        
        # 计算每个位置还需要多少HCP
        current_hcp = {pos: sum(HCP_MAP.get(c.rank, 0) for c in result[pos]) for pos in positions}
        needed_hcp = {pos: max(0, hcp_targets[pos] - current_hcp[pos]) for pos in positions}
        
        # 分配大牌优先给需要更多HCP的位置——使用强权重（接近确定性分配）
        high_to_low = list(suit_cards)
        
        for card in high_to_low:
            card_hcp = HCP_MAP.get(card.rank, 0)
            # 找需要这门花色牌的位置
            candidates = []
            total_weight = 0
            pos_weights = {}
            for pos in positions:
                if needed[pos] > 0:
                    # 强权重：需要HCP多的位置优先拿大牌，权重是 needed_hcp 的平方
                    if card_hcp > 0:
                        w = needed_hcp[pos] ** 2 + 1
                    else:
                        w = max(1, 20 - needed_hcp[pos])  # 小牌优先给HCP够了的位置
                    pos_weights[pos] = w
                    total_weight += w
            
            if total_weight == 0:
                # 剩下的牌随便分
                for pos in positions:
                    if needed[pos] > 0:
                        candidates.append(pos)
                pos = random.choice(candidates) if candidates else positions[0]
            else:
                # 按权重随机选择（权重高的概率大）
                r = random.randint(1, total_weight)
                cumulative = 0
                pos = positions[0]
                for p, w in pos_weights.items():
                    cumulative += w
                    if r <= cumulative:
                        pos = p
                        break
            
            result[pos].append(card)
            needed[pos] -= 1
            needed_hcp[pos] = max(0, needed_hcp[pos] - card_hcp)
    
    # Step 3: 定向局部交换修正HCP误差（智能交换，而不是盲目随机）
    # 优化：增量HCP维护 + 早停（连续无改善即退出） + 减少上限
    max_fix_rounds = 200
    no_improve_count = 0
    # 初始化增量 HCP（只算一次，后续交换时增量更新）
    current_hcp = {pos: sum(HCP_MAP.get(c.rank, 0) for c in result[pos]) for pos in positions}

    for _fix_round in range(max_fix_rounds):
        # 检查 HCP 违规
        hcp_violations = []
        for pos in positions:
            c = constraints.get(pos)
            if not c:
                continue
            h = current_hcp[pos]
            if c.min_hcp is not None and h < c.min_hcp:
                hcp_violations.append((pos, "low", c.min_hcp - h))
            if c.max_hcp is not None and h > c.max_hcp:
                hcp_violations.append((pos, "high", h - c.max_hcp))

        # 同时检查牌型和其他约束
        all_ok = len(hcp_violations) == 0
        if all_ok:
            for pos in positions:
                c = constraints.get(pos)
                if c and not DealSampler._check_all_constraints(result[pos], c, target_count=None):
                    all_ok = False
                    break

        if all_ok:
            break

        # 找出所有HCP不足和HCP超额的位置
        low_positions = [(p, d) for p, t, d in hcp_violations if t == "low"]
        high_positions = [(p, d) for p, t, d in hcp_violations if t == "high"]

        swapped = False

        # 优先尝试HCP定向交换：从高HCP位置拿大牌换低HCP位置的小牌
        if low_positions and high_positions:
            for low_pos, low_deficit in low_positions:
                for high_pos, high_excess in high_positions:
                    if low_pos == high_pos:
                        continue
                    low_cards = result[low_pos]
                    high_cards = result[high_pos]
                    low_c = constraints.get(low_pos)
                    high_c = constraints.get(high_pos)

                    for _try in range(15):
                        high_choices = [c for c in high_cards if HCP_MAP.get(c.rank, 0) > 0]
                        if not high_choices:
                            break
                        high_card = random.choice(high_choices)
                        h_card_hcp = HCP_MAP.get(high_card.rank, 0)

                        low_choices = [c for c in low_cards if c.suit == high_card.suit and HCP_MAP.get(c.rank, 0) == 0]
                        if not low_choices:
                            low_choices = [c for c in low_cards if HCP_MAP.get(c.rank, 0) < h_card_hcp]
                        if not low_choices:
                            continue
                        low_card = random.choice(low_choices)
                        l_card_hcp = HCP_MAP.get(low_card.rank, 0)

                        new_low_h = current_hcp[low_pos] - l_card_hcp + h_card_hcp
                        new_high_h = current_hcp[high_pos] - h_card_hcp + l_card_hcp

                        low_ok = True
                        high_ok = True
                        if low_c:
                            if low_c.min_hcp is not None and new_low_h < low_c.min_hcp:
                                low_ok = False
                            if low_c.max_hcp is not None and new_low_h > low_c.max_hcp:
                                low_ok = False
                        if high_c:
                            if high_c.min_hcp is not None and new_high_h < high_c.min_hcp:
                                high_ok = False
                            if high_c.max_hcp is not None and new_high_h > high_c.max_hcp:
                                high_ok = False

                        if low_c:
                            for (s, r) in low_c.specific_cards:
                                if s == low_card.suit and r == low_card.rank:
                                    low_ok = False
                        if high_c:
                            for (s, r) in high_c.specific_cards:
                                if s == high_card.suit and r == high_card.rank:
                                    high_ok = False

                        if low_ok and high_ok:
                            result[low_pos] = [c for c in low_cards if c != low_card] + [high_card]
                            result[high_pos] = [c for c in high_cards if c != high_card] + [low_card]
                            # 增量更新 HCP
                            current_hcp[low_pos] = new_low_h
                            current_hcp[high_pos] = new_high_h
                            swapped = True
                            break
                    if swapped:
                        break
                if swapped:
                    break

        # 如果定向交换没成功，做随机交换尝试修复其他约束
        if not swapped:
            for _try in range(10):
                pos1 = random.choice(positions)
                pos2 = random.choice(positions)
                if pos1 == pos2:
                    continue
                c1 = result[pos1]
                c2 = result[pos2]
                if not c1 or not c2:
                    continue
                out1 = random.choice(c1)
                out2 = random.choice(c2)
                t1 = [c for c in c1 if c != out1] + [out2]
                t2 = [c for c in c2 if c != out2] + [out1]
                ok1 = DealSampler._check_all_constraints(t1, constraints.get(pos1), target_count=None)
                ok2 = DealSampler._check_all_constraints(t2, constraints.get(pos2), target_count=None)
                if ok1 and ok2:
                    # 增量计算新 HCP 误差（不重新遍历所有牌）
                    h1_old = current_hcp[pos1]
                    h2_old = current_hcp[pos2]
                    h1_new = h1_old - HCP_MAP.get(out1.rank, 0) + HCP_MAP.get(out2.rank, 0)
                    h2_new = h2_old - HCP_MAP.get(out2.rank, 0) + HCP_MAP.get(out1.rank, 0)

                    old_err = 0
                    new_err = 0
                    for p in positions:
                        c = constraints.get(p)
                        if not c:
                            continue
                        ho = current_hcp[p]
                        hn = ho
                        if p == pos1:
                            hn = h1_new
                        elif p == pos2:
                            hn = h2_new
                        if c.min_hcp is not None:
                            old_err += max(0, c.min_hcp - ho)
                            new_err += max(0, c.min_hcp - hn)
                        if c.max_hcp is not None:
                            old_err += max(0, ho - c.max_hcp)
                            new_err += max(0, hn - c.max_hcp)

                    if new_err <= old_err:
                        result[pos1] = t1
                        result[pos2] = t2
                        current_hcp[pos1] = h1_new
                        current_hcp[pos2] = h2_new
                        swapped = True
                        break

        # 早停：连续无改善计数
        if swapped:
            no_improve_count = 0
        else:
            no_improve_count += 1
            if no_improve_count >= 15:
                break

    return result


def _distribute_global_constrained(
    result: Dict[str, List[Card]],
    pool: List[Card],
    remaining_counts: Dict[str, int],
    constraints: Dict[str, BidConstraint],
    known_voids: Dict[str, Set[str]] = None,
    played_set: Set[Tuple[str, str]] = None,
    played_hcp_per_pos: Dict[str, int] = None,
    played_controls_per_pos: Dict[str, int] = None,
    played_suit_per_pos: Dict[str, Dict[str, int]] = None,
) -> None:
    """新的全局约束分配：先分牌型→再分HCP→再分牌张

    替代原有_distribute_biased逐位置贪心算法
    """
    known_voids = known_voids or {}
    played_set = played_set or set()
    positions = [p for p in POSITION_ORDER]
    unknown_positions = [p for p in positions if p not in result]

    if not unknown_positions:
        return

    # 把已知牌张计入张数约束
    known_shape = {}
    known_cards_set = set()
    for pos, cards in result.items():
        known_shape[pos] = {s: sum(1 for c in cards if c.suit == s) for s in SUITS}
        for c in cards:
            known_cards_set.add((c.suit, c.rank))
    
    # 过滤出真正未知的牌池（排除已分配的）
    real_pool = [c for c in pool if (c.suit, c.rank) not in known_cards_set]
    
    # 构建完整的target_counts：已知位置张数 + 未知位置需要补的
    target_counts = {}
    for pos in positions:
        if pos in result:
            target_counts[pos] = len(result[pos])
        else:
            target_counts[pos] = remaining_counts.get(pos, 13 - sum(known_shape.get(pos, {}).values()))
    
    # 对于未知位置，应用known_voids：如果已知缺门，suit_max[suit] = 0
    # 同时按剩余张数缩减suit_min/HCP/min_controls（整手13张时的约束在中局应等比缩减）
    # 已出的specific_cards应过滤掉，避免_assign_cards找不到该牌导致粒子缺牌
    # 已出牌张集合（用于过滤specific_cards），由调用方传入
    _played_set = played_set

    effective_constraints = {}
    for pos in positions:
        c = constraints.get(pos)
        if c is None:
            c = BidConstraint(position=pos)
        # 复制约束，避免修改原对象
        c_copy = copy.copy(c)
        c_copy.suit_min = dict(c.suit_min)
        c_copy.suit_max = dict(c.suit_max)
        c_copy.exact_suit = dict(c.exact_suit)
        c_copy.specific_cards = {sc for sc in c.specific_cards if sc not in _played_set}
        # 应用已知void
        for void_suit in known_voids.get(pos, set()):
            c_copy.suit_max[void_suit] = 0
        # 未知位置：中局约束缩减
        if pos not in result:
            target = target_counts[pos]
            if target < 13:
                # 张数约束缩减：按花色分别扣减已出张数（初始约束 = 已出 + 剩余）
                # 物理意义：南家♠≥5张约束，已出♠3张 → 剩余♠≥2张
                # 比线性递减 max(0, suit_min-(13-target)) 更准确（不假设均匀分布）
                _played_suits = (played_suit_per_pos or {}).get(pos, {})
                for s in list(c_copy.suit_min.keys()):
                    played_cnt = _played_suits.get(s, 0)
                    reduced = max(0, c_copy.suit_min[s] - played_cnt)
                    reduced = min(reduced, target)
                    c_copy.suit_min[s] = reduced
                # exact_suit 同样按花色扣减
                for s in list(c_copy.exact_suit.keys()):
                    played_cnt = _played_suits.get(s, 0)
                    reduced = c_copy.exact_suit[s] - played_cnt
                    if reduced < 0:
                        # 已出超过初始exact（理论不应发生），删除约束
                        del c_copy.exact_suit[s]
                    else:
                        c_copy.exact_suit[s] = reduced
                # suit_max 也按花色扣减（如初始♥≤4，已出♥2张 → 剩余♥≤2张）
                for s in list(c_copy.suit_max.keys()):
                    played_cnt = _played_suits.get(s, 0)
                    reduced = c_copy.suit_max[s] - played_cnt
                    c_copy.suit_max[s] = max(0, reduced)
                # HCP约束缩减：用已出牌HCP扣减（初始约束 = 已出HCP + 剩余HCP）
                # 物理意义：初始约束针对13张牌，已出牌HCP已消耗部分预算，
                # 剩余手牌HCP范围 = [初始min - 已出HCP, 初始max - 已出HCP]
                # 这比按target/13比例缩减更准确（HCP集中在A/K/Q/J上，非均匀分布）
                _played_hcp = (played_hcp_per_pos or {}).get(pos, 0)
                if c_copy.min_hcp is not None:
                    c_copy.min_hcp = max(0, c_copy.min_hcp - _played_hcp)
                if c_copy.max_hcp is not None:
                    new_max = c_copy.max_hcp - _played_hcp
                    # max不能低于min（已出HCP超过初始max的极端情况）
                    c_copy.max_hcp = max(new_max, c_copy.min_hcp or 0)
                # min_controls缩减：控制数是整手属性，同样用已出牌扣减
                _played_ctrl = (played_controls_per_pos or {}).get(pos, 0)
                if c_copy.min_controls is not None:
                    c_copy.min_controls = max(0, c_copy.min_controls - _played_ctrl)
        # 对于已有部分牌的位置，调整suit_min/exact以反映已知张数
        if pos in known_shape:
            for s in SUITS:
                have = known_shape[pos][s]
                if s in c_copy.suit_min:
                    c_copy.suit_min[s] = max(0, c_copy.suit_min[s] - have)
                if s in c_copy.exact_suit:
                    c_copy.exact_suit[s] = max(0, c_copy.exact_suit[s] - have)
        effective_constraints[pos] = c_copy
    
    # 未知位置的target_counts是需要从pool中分配的张数
    unknown_targets = {pos: remaining_counts.get(pos, 13) for pos in unknown_positions}

    # Step 1: 生成未知位置的牌型分布（带 shape 池缓存）
    # 同一 PlayState 下 N 个粒子共享 shape 候选池，避免重复随机重试
    import time as _time
    _t0 = _time.time()
    # 构建缓存键：unknown_positions + targets + pool花色分布签名
    _pool_sig = tuple(sorted([(s, sum(1 for _c in real_pool if _c.suit == s)) for s in SUITS]))
    _targets_sig = tuple((pos, unknown_targets[pos]) for pos in unknown_positions)
    _cache_key = (tuple(unknown_positions), _targets_sig, _pool_sig)

    shape = None
    _shape_attempts = 0
    _hard_conflict_skip = _cache_key in _SHAPE_POOL_HARD_CONFLICT
    if _cache_key in _SHAPE_POOL and _SHAPE_POOL[_cache_key]:
        # 缓存命中：从候选池随机选一个
        shape = copy.deepcopy(random.choice(_SHAPE_POOL[_cache_key]))
        _DIST_STATS["shape_cache_hits"] += 1
    elif not _hard_conflict_skip:
        # 首次生成：尝试产出多个候选填满池
        _pool_candidates = []
        for _attempt in range(50):
            _shape_attempts += 1
            _sh = _generate_valid_shape_distribution(
                {pos: effective_constraints[pos] for pos in unknown_positions},
                unknown_positions,
                unknown_targets,
                pool=real_pool,
            )
            if _sh is not None:
                _pool_candidates.append(_sh)
                if len(_pool_candidates) >= _SHAPE_POOL_TARGET:
                    break
        if _pool_candidates:
            shape = copy.deepcopy(_pool_candidates[0])
            _SHAPE_POOL[_cache_key] = _pool_candidates[:_SHAPE_POOL_MAX]
        else:
            shape = None
            # 标记此 cache_key 为硬冲突，后续粒子直接跳到放宽分支
            # 避免每个粒子重复跑 50 次外层重试（2000 粒子 × 50 = 10 万次无意义重试）
            _SHAPE_POOL_HARD_CONFLICT.add(_cache_key)
    _DIST_STATS["shape_t"] += _time.time() - _t0
    _DIST_STATS["shape_calls"] += 1
    _DIST_STATS["shape_retries"] += _shape_attempts - 1 if _shape_attempts > 0 else 0

    if shape is None:
        # 牌型生成失败：针对性放宽约束
        # 策略：只放宽冲突花色的 suit_min/exact_suit（降到 pool 能容纳的值），
        # 保留其他花色约束、HCP 范围、suit_max（含void）、balanced
        # 这样最大程度保留约束信息，粒子权重由 compute_sample_violation_score 软惩罚冲突花色
        _relaxed_constraints = {}
        # 计算每个花色 pool 张数与各位置 suit_min/exact 之和的差值，找出冲突花色
        _pool_by_suit = {s: sum(1 for _c in real_pool if _c.suit == s) for s in SUITS}
        _lower_by_suit = {s: 0 for s in SUITS}
        for pos in unknown_positions:
            c = effective_constraints.get(pos)
            if not c:
                continue
            for s in SUITS:
                if s in c.exact_suit:
                    _lower_by_suit[s] += c.exact_suit[s]
                elif s in c.suit_min:
                    _lower_by_suit[s] += c.suit_min[s]
        _conflict_suits = {s for s in SUITS if _lower_by_suit[s] > _pool_by_suit[s]}

        for pos in unknown_positions:
            c = effective_constraints.get(pos)
            if c is None:
                c = BidConstraint(position=pos)
            c_relax = copy.copy(c)
            c_relax.suit_min = dict(c.suit_min)
            c_relax.suit_max = dict(c.suit_max)
            c_relax.exact_suit = dict(c.exact_suit)
            c_relax.specific_cards = set(c.specific_cards)
            # 只放宽冲突花色的 suit_min/exact_suit
            for s in _conflict_suits:
                if s in c_relax.exact_suit:
                    # exact_suit 降为 suit_min 语义（至少改为 pool 可容纳值）
                    available = max(0, _pool_by_suit[s] - (_lower_by_suit[s] - c_relax.exact_suit[s]))
                    if available > 0:
                        c_relax.suit_min[s] = min(c_relax.exact_suit[s], available)
                    del c_relax.exact_suit[s]
                elif s in c_relax.suit_min:
                    # suit_min 降到 pool 可容纳值（其他位置 suit_min 已占用剩余）
                    available = max(0, _pool_by_suit[s] - (_lower_by_suit[s] - c_relax.suit_min[s]))
                    c_relax.suit_min[s] = min(c_relax.suit_min[s], available)
            # 中局阶段（target<13）：balanced 约束下限已无法保证（pool 不足），
            # 只保留上限（无6+张套），避免与 suit_max 叠加导致无解
            if c.balanced and unknown_targets.get(pos, 13) < 13:
                c_relax.balanced = None  # 由 suit_max≤5 替代上限检查
            _relaxed_constraints[pos] = c_relax
        # 放宽后重试shape生成
        for _attempt in range(30):
            shape = _generate_valid_shape_distribution(
                _relaxed_constraints,
                unknown_positions,
                unknown_targets,
                pool=real_pool,
            )
            if shape is not None:
                break
        if shape is None:
            # 放宽后仍失败：最终回退到_distribute_biased（极少发生）
            orig_sampler = DealSampler()
            orig_sampler.constraints = constraints
            orig_sampler._distribute_biased(result, pool, remaining_counts, known_voids)
            _DIST_STATS["fallback_count"] += 1
            _suit_total = {s: sum(1 for _c in real_pool if _c.suit == s) for s in SUITS}
            with open(_DEBUG_LOG, "a", encoding="utf-8") as _f:
                _f.write(f"[FB_HARD] pool={len(real_pool)} suits={_suit_total} "
                         f"unknown_pos={unknown_positions} targets={unknown_targets} "
                         f"known_voids={known_voids}\n")
            return
        # 放宽重试成功：shape 已生成，继续走 HCP+牌张分配流程
        # 注意：effective_constraints 仍用原值（HCP约束保留），shape只是放宽了suit_min/balanced
    
    # 合并已知牌张到完整shape
    full_shape = {}
    for pos in positions:
        if pos in known_shape:
            full_shape[pos] = dict(known_shape[pos])
        else:
            full_shape[pos] = dict(shape[pos])
    
    # Step 2: 分配HCP预算
    _t1 = _time.time()
    known_hcp = {}
    for pos in result:
        known_hcp[pos] = sum(HCP_MAP.get(c.rank, 0) for c in result[pos])

    hcp_budgets = None
    # 可行性检查是确定性的，1次调用即可判断，无需重试50次
    unknown_budgets = _allocate_hcp_budget(
        {pos: effective_constraints[pos] for pos in unknown_positions},
        unknown_positions,
        pool=real_pool,
    )
    if unknown_budgets is not None:
        hcp_budgets = {}
        for pos in positions:
            if pos in known_hcp:
                hcp_budgets[pos] = known_hcp[pos]
            else:
                hcp_budgets[pos] = unknown_budgets[pos]
    _DIST_STATS["hcp_t"] += _time.time() - _t1
    _DIST_STATS["hcp_calls"] += 1
    _DIST_STATS["hcp_retries"] += 0

    # HCP 预算不可行（明确叫牌的硬约束之间矛盾，极少发生）
    # 此时降级到 _distribute_biased（仍尊重约束，通过 _constrained_select 软逼近）
    if hcp_budgets is None:
        if _DIST_STATS["fallback_count"] < 3:
            with open(_DEBUG_LOG, "a", encoding="utf-8") as _f:
                _eff_bounds = {p: (effective_constraints[p].min_hcp, effective_constraints[p].max_hcp, effective_constraints[p].inference_source) for p in unknown_positions}
                _pool_hcp = sum(HCP_MAP.get(c.rank, 0) for c in real_pool)
                _f.write(f"[HCP_BUDGET_FAIL] unknown_bounds={_eff_bounds} "
                         f"pool_hcp={_pool_hcp} → _distribute_biased\n")
        _DIST_STATS["fallback_count"] += 1
        orig_sampler = DealSampler()
        orig_sampler.constraints = constraints
        orig_sampler._distribute_biased(result, pool, remaining_counts, known_voids)
        return

    # Step 3: 分配具体牌张
    _t2 = _time.time()
    unknown_result = _assign_cards_by_shape_and_hcp(
        real_pool,
        shape,
        {pos: hcp_budgets[pos] - known_hcp.get(pos, 0) for pos in unknown_positions},
        {pos: effective_constraints[pos] for pos in unknown_positions},
        unknown_positions,
    )
    _DIST_STATS["assign_t"] += _time.time() - _t2
    _DIST_STATS["assign_calls"] += 1

    # 合并到结果
    for pos in unknown_positions:
        result[pos] = unknown_result.get(pos, [])
