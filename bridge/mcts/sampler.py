import os
import random
from typing import Dict, List, Set, Optional

from bridge.play_types import Card, PlayState, PlayPhase, POSITION_ORDER
from bridge.mcts.state_utils import clone_hands, SUIT_DISPLAY_ORDER, RANK_DESC
from bridge.mcts.constraints import BidConstraint, validate_sample, HCP_MAP
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
        # 信念跟踪器路径：按权重抽样
        if self.belief_tracker is not None and self.belief_tracker.particles:
            return self.belief_tracker.draw()

        # 原始路径：约束验证 + 随机采样
        if self.constraints:
            for attempt in range(MAX_CONSTRAINT_RETRIES):
                result = self._sample_once(state, perspective)
                if validate_sample(result, self.constraints):
                    return result
            # 超过重试上限，回退到真正的无约束采样
            saved = self.constraints
            self.constraints = {}
            result = self._sample_once(state, perspective)
            self.constraints = saved
            return result
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
            self._distribute_biased(result, unknown_pool, remaining_counts, known_voids)
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
    def _constrained_select(
        pool: List[Card],
        count: int,
        constraint: "BidConstraint",
    ) -> List[Card]:
        """从 pool 中选 count 张牌，保证满足花色下限和HCP约束。"""
        if count >= len(pool):
            return list(pool)

        selected: List[Card] = []
        remaining: List[Card] = list(pool)

        # Step 1: 满足花色下限（同花色内优先高HCP，避免锁死低HCP牌）
        for suit, min_len in constraint.suit_min.items():
            if min_len <= 0:
                continue
            suit_cards = [c for c in remaining if c.suit == suit]
            n_pick = min(min_len, len(suit_cards))
            if n_pick > 0:
                suit_cards.sort(key=lambda c: -(HCP_MAP.get(c.rank, 0) + random.random() * 0.5))
                picked = suit_cards[:n_pick]
                selected.extend(picked)
                for c in picked:
                    remaining.remove(c)

        # Step 2: 补满 count 张（优先高HCP + 随机扰动）
        need = count - len(selected)
        if need > 0:
            scored = [(HCP_MAP.get(c.rank, 0) + random.random() * 2, c) for c in remaining]
            scored.sort(key=lambda x: -x[0])
            for _, c in scored[:need]:
                selected.append(c)
                remaining.remove(c)

        # Step 3: 满足HCP下限 — 用小牌换大牌，优先同花色替换
        if constraint.min_hcp is not None:
            for _ in range(200):
                current = sum(HCP_MAP.get(c.rank, 0) for c in selected)
                if current >= constraint.min_hcp:
                    break
                low = min(selected, key=lambda c: HCP_MAP.get(c.rank, 0))
                low_hcp = HCP_MAP.get(low.rank, 0)
                low_suit = low.suit
                # 优先选同花色高HCP牌（不妨碍花色下限），再考虑其他花色
                same_suit = [c for c in remaining if c.suit == low_suit and HCP_MAP.get(c.rank, 0) > low_hcp]
                other_suit = [c for c in remaining if c.suit != low_suit and HCP_MAP.get(c.rank, 0) > low_hcp]
                candidates = same_suit + other_suit
                if not candidates:
                    break
                high = max(candidates, key=lambda c: HCP_MAP.get(c.rank, 0))
                # 检查花色下限
                selected.remove(low)
                selected.append(high)
                suit_ok = True
                for suit, min_len in constraint.suit_min.items():
                    if sum(1 for c in selected if c.suit == suit) < min_len:
                        suit_ok = False
                        break
                if suit_ok:
                    remaining.append(low)
                    remaining.remove(high)
                else:
                    selected.remove(high)
                    selected.append(low)

        # Step 4: 满足HCP上限 — 用大牌换小牌，优先同花色替换
        if constraint.max_hcp is not None:
            for _ in range(200):
                current = sum(HCP_MAP.get(c.rank, 0) for c in selected)
                if current <= constraint.max_hcp:
                    break
                high = max(selected, key=lambda c: HCP_MAP.get(c.rank, 0))
                high_hcp = HCP_MAP.get(high.rank, 0)
                high_suit = high.suit
                same_suit = [c for c in remaining if c.suit == high_suit and HCP_MAP.get(c.rank, 0) < high_hcp]
                other_suit = [c for c in remaining if c.suit != high_suit and HCP_MAP.get(c.rank, 0) < high_hcp]
                candidates = same_suit + other_suit
                if not candidates:
                    break
                low = min(candidates, key=lambda c: HCP_MAP.get(c.rank, 0))
                selected.remove(high)
                selected.append(low)
                suit_ok = True
                for suit, min_len in constraint.suit_min.items():
                    if sum(1 for c in selected if c.suit == suit) < min_len:
                        suit_ok = False
                        break
                if suit_ok:
                    remaining.append(high)
                    remaining.remove(low)
                else:
                    selected.remove(low)
                    selected.append(high)

        return selected
