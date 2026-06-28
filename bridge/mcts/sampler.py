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
        for trick in state.tricks:
            for _, c in trick.cards:
                played_set.add((c.suit, c.rank))
        for _, c in state.current_trick.cards:
            played_set.add((c.suit, c.rank))
        unknown_pool = [c for c in ALL_CARDS
                        if (c.suit, c.rank) not in assigned
                        and (c.suit, c.rank) not in played_set]

        # 5. 分配未知牌到未知位置（含手牌为空的位置）
        # 收集已知 void：void 位置不应收到 void 花色的牌
        known_voids = collect_voids(state)

        if self.constraints:
            _distribute_global_constrained(result, unknown_pool, remaining_counts, self.constraints, known_voids)
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
    max_attempts = 200
    
    # 计算牌池中每个花色实际有多少张
    suit_total = {s: 13 for s in SUITS}
    if pool is not None:
        suit_total = {s: 0 for s in SUITS}
        for c in pool:
            suit_total[c.suit] += 1
    
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
            continue
        
        # Step 4: 验证每花色当前总数不超过牌池
        for s in SUITS:
            total = sum(shape[pos][s] for pos in positions)
            if total > suit_total[s]:
                valid = False
                break
        if not valid:
            continue
        
        # Step 5: 随机填充剩余张数，保证每花色总数=suit_total[s]，每家总数=target
        # 计算还需要分配的张数
        remaining_by_pos = {pos: target_counts[pos] - sum(shape[pos].values()) for pos in positions}
        remaining_by_suit = {s: suit_total[s] - sum(shape[pos][s] for pos in positions) for s in SUITS}
        
        # 检查剩余是否合理
        total_remaining = sum(remaining_by_pos.values())
        if total_remaining != sum(remaining_by_suit.values()):
            continue
        if total_remaining < 0:
            continue
        
        # 逐步随机分配剩余张数
        possible = True
        remaining_slots = total_remaining
        for ___ in range(remaining_slots):
            # 找候选位置（还需要更多牌，且不超过suit_max）
            candidates = []
            for pos in positions:
                if remaining_by_pos[pos] <= 0:
                    continue
                c = constraints.get(pos)
                for s in SUITS:
                    if remaining_by_suit[s] <= 0:
                        continue
                    # 检查suit_max约束
                    max_allowed = 13
                    if c and s in c.suit_max:
                        max_allowed = c.suit_max[s]
                    # 如果要求均型，单套不能超过5张
                    if c and c.balanced and shape[pos][s] >= 5:
                        max_allowed = 5
                    if shape[pos][s] >= max_allowed:
                        continue
                    candidates.append((pos, s))
            
            if not candidates:
                possible = False
                break
            
            # 随机选一个候选，加一张
            pos, s = random.choice(candidates)
            shape[pos][s] += 1
            remaining_by_pos[pos] -= 1
            remaining_by_suit[s] -= 1
        
        if not possible:
            continue
        
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
                is_bal = all(2 <= d <= 5 for d in dist) and not any(d >= 6 for d in dist)
                if c.balanced and not is_bal:
                    ok = False
                if not c.balanced and is_bal:
                    ok = False
        for s in SUITS:
            if sum(shape[pos][s] for pos in positions) != suit_total[s]:
                ok = False
        
        if ok:
            return shape
    
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
    max_attempts = 200
    
    # 计算牌池中总HCP
    total_hcp = 40
    if pool is not None:
        total_hcp = sum(HCP_MAP.get(c.rank, 0) for c in pool)
    
    for _ in range(max_attempts):
        budgets = {}
        remaining = total_hcp
        
        # 先给每个位置分配最小值
        for pos in positions:
            c = constraints.get(pos)
            mn = c.min_hcp if c and c.min_hcp is not None else 0
            budgets[pos] = mn
            remaining -= mn
        
        if remaining < 0:
            continue
        
        # 随机分配剩余点力
        for ___ in range(remaining):
            # 找还能加点的位置
            candidates = []
            for pos in positions:
                c = constraints.get(pos)
                mx = c.max_hcp if c and c.max_hcp is not None else 37
                if budgets[pos] < mx:
                    # 偏好分配给min_hcp_target附近的位置
                    target = None
                    if c and c.min_hcp_target is not None:
                        target = c.min_hcp_target
                    elif c and c.min_hcp is not None and c.max_hcp is not None:
                        target = (c.min_hcp + c.max_hcp) // 2
                    weight = 1
                    if target is not None:
                        dist = abs(budgets[pos] + 1 - target)
                        weight = max(1, 5 - dist)
                    candidates.extend([pos] * weight)
            
            if not candidates:
                break
            pos = random.choice(candidates)
            budgets[pos] += 1
        
        total = sum(budgets.values())
        if total != total_hcp:
            continue
        
        # 验证所有约束
        ok = True
        for pos in positions:
            c = constraints.get(pos)
            h = budgets[pos]
            if c:
                if c.min_hcp is not None and h < c.min_hcp:
                    ok = False
                if c.max_hcp is not None and h > c.max_hcp:
                    ok = False
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
    # 最多进行1000次交换尝试
    for _fix_round in range(1000):
        # 检查当前HCP状态
        current_hcp = {}
        hcp_violations = []
        for pos in positions:
            c = constraints.get(pos)
            cards = result[pos]
            h = sum(HCP_MAP.get(card.rank, 0) for card in cards)
            current_hcp[pos] = h
            if not c:
                continue
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
                    
                    # 尝试找同花色交换：高HCP方出大牌，低HCP方出小牌
                    for _try in range(30):
                        # 从高HCP位置找一张大牌（HCP>0）
                        high_choices = [c for c in high_cards if HCP_MAP.get(c.rank, 0) > 0]
                        if not high_choices:
                            break
                        high_card = random.choice(high_choices)
                        h_card_hcp = HCP_MAP.get(high_card.rank, 0)
                        
                        # 从低HCP位置找同花色的一张小牌（HCP=0）
                        low_choices = [c for c in low_cards if c.suit == high_card.suit and HCP_MAP.get(c.rank, 0) == 0]
                        if not low_choices:
                            # 允许不同花色交换，但要保证牌型张数不变（跨花色交换张数必须相等——单张换单张没问题）
                            low_choices = [c for c in low_cards if HCP_MAP.get(c.rank, 0) < h_card_hcp]
                        if not low_choices:
                            continue
                        low_card = random.choice(low_choices)
                        l_card_hcp = HCP_MAP.get(low_card.rank, 0)
                        
                        # 计算交换后的HCP
                        new_low_h = current_hcp[low_pos] - l_card_hcp + h_card_hcp
                        new_high_h = current_hcp[high_pos] - h_card_hcp + l_card_hcp
                        
                        # 检查HCP约束改善
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
                        
                        # 检查牌型约束（交换后张数不变，牌型自动满足）
                        # 但要检查specific_cards
                        if low_c:
                            for (s, r) in low_c.specific_cards:
                                if (s == low_card.suit and r == low_card.rank):
                                    low_ok = False  # 不能把必须持有的牌换出去
                                if (s == high_card.suit and r == high_card.rank):
                                    pass  # 换进来没问题
                        if high_c:
                            for (s, r) in high_c.specific_cards:
                                if (s == high_card.suit and r == high_card.rank):
                                    high_ok = False  # 不能把必须持有的牌换出去
                        
                        if low_ok and high_ok:
                            # 执行交换
                            result[low_pos] = [c for c in low_cards if c != low_card] + [high_card]
                            result[high_pos] = [c for c in high_cards if c != high_card] + [low_card]
                            swapped = True
                            break
                    if swapped:
                        break
                if swapped:
                    break
        
        # 如果定向交换没成功，做随机交换尝试修复其他约束
        if not swapped:
            for _try in range(20):
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
                    # 检查是否改善了整体HCP误差
                    old_err = sum(max(0, constraints.get(p).min_hcp - current_hcp[p]) for p in positions if constraints.get(p) and constraints.get(p).min_hcp is not None) + \
                              sum(max(0, current_hcp[p] - constraints.get(p).max_hcp) for p in positions if constraints.get(p) and constraints.get(p).max_hcp is not None)
                    new_h = {p: current_hcp[p] for p in positions}
                    new_h[pos1] = new_h[pos1] - HCP_MAP.get(out1.rank, 0) + HCP_MAP.get(out2.rank, 0)
                    new_h[pos2] = new_h[pos2] - HCP_MAP.get(out2.rank, 0) + HCP_MAP.get(out1.rank, 0)
                    new_err = sum(max(0, constraints.get(p).min_hcp - new_h[p]) for p in positions if constraints.get(p) and constraints.get(p).min_hcp is not None) + \
                              sum(max(0, new_h[p] - constraints.get(p).max_hcp) for p in positions if constraints.get(p) and constraints.get(p).max_hcp is not None)
                    if new_err <= old_err:
                        result[pos1] = t1
                        result[pos2] = t2
                        swapped = True
                        break
    
    return result


def _distribute_global_constrained(
    result: Dict[str, List[Card]],
    pool: List[Card],
    remaining_counts: Dict[str, int],
    constraints: Dict[str, BidConstraint],
    known_voids: Dict[str, Set[str]] = None,
) -> None:
    """新的全局约束分配：先分牌型→再分HCP→再分牌张
    
    替代原有的_distribute_biased逐位置贪心算法
    """
    known_voids = known_voids or {}
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
        c_copy.specific_cards = set(c.specific_cards)
        # 应用已知void
        for void_suit in known_voids.get(pos, set()):
            c_copy.suit_max[void_suit] = 0
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
    
    # Step 1: 生成未知位置的牌型分布
    shape = None
    for _attempt in range(50):
        shape = _generate_valid_shape_distribution(
            {pos: effective_constraints[pos] for pos in unknown_positions},
            unknown_positions,
            unknown_targets,
            pool=real_pool,
        )
        if shape is not None:
            break
    
    if shape is None:
        # 牌型生成失败，回退到原有算法
        orig_sampler = DealSampler()
        orig_sampler.constraints = constraints
        orig_sampler._distribute_biased(result, pool, remaining_counts, known_voids)
        return
    
    # 合并已知牌张到完整shape
    full_shape = {}
    for pos in positions:
        if pos in known_shape:
            full_shape[pos] = dict(known_shape[pos])
        else:
            full_shape[pos] = dict(shape[pos])
    
    # Step 2: 分配HCP预算
    # 计算已知位置已有HCP
    known_hcp = {}
    for pos in result:
        known_hcp[pos] = sum(HCP_MAP.get(c.rank, 0) for c in result[pos])
    
    # 未知位置从real_pool分配，HCP预算应针对real_pool中的牌
    hcp_budgets = None
    for _attempt in range(50):
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
            break
    
    if hcp_budgets is None:
        # HCP分配失败，给个均匀预算
        hcp_budgets = {pos: 10 for pos in positions}
    
    # Step 3: 分配具体牌张
    unknown_result = _assign_cards_by_shape_and_hcp(
        real_pool,
        shape,
        {pos: hcp_budgets[pos] - known_hcp.get(pos, 0) for pos in unknown_positions},
        {pos: effective_constraints[pos] for pos in unknown_positions},
        unknown_positions,
    )
    
    # 合并到结果
    for pos in unknown_positions:
        result[pos] = unknown_result.get(pos, [])
