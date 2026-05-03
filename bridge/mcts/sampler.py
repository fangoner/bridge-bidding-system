import random
from typing import Dict, List, Set, Optional

from bridge.play_types import Card, PlayState, PlayPhase, POSITION_ORDER
from bridge.mcts.state_utils import clone_hands, SUIT_DISPLAY_ORDER, RANK_DESC
from bridge.mcts.constraints import BidConstraint, validate_sample, HCP_MAP


# 一副完整的52张牌
ALL_CARDS = [Card(suit=s, rank=r) for s in SUIT_DISPLAY_ORDER for r in RANK_DESC]

# 约束采样最大重试次数（_constrained_select 保证约束前提下仍保留重试安全网）
MAX_CONSTRAINT_RETRIES = 3


class DealSampler:
    """从当前玩家视角采样未知手牌分布。

    每轮MCTS迭代前调用 sample()，返回完整4家手牌分配。
    支持叫牌约束过滤，提高采样质量。
    """

    def __init__(self):
        self.constraints: Dict[str, BidConstraint] = {}

    def set_constraints(self, constraints: Dict[str, BidConstraint]) -> None:
        """设置叫牌约束，后续 sample() 会验证采样结果。

        Args:
            constraints: {position: BidConstraint} 映射
        """
        self.constraints = constraints or {}

    def sample(self, state: PlayState, perspective: str) -> Dict[str, List[Card]]:
        """采样一套与当前信息一致且满足叫牌约束的完整手牌。

        Args:
            state: 当前PlayState
            perspective: 当前出牌者位置（"南"/"西"/"北"/"东"）

        Returns:
            完整4家手牌 Dict[str, List[Card]]
        """
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

        # 2. 计算每个位置剩余张数
        remaining_counts = {}
        for pos in POSITION_ORDER:
            played = self._count_played(state, pos)
            remaining_counts[pos] = 13 - played

        # 3. 未知牌张池
        unknown_pool = [c for c in ALL_CARDS if c not in known_cards]
        random.shuffle(unknown_pool)

        # 4. 已知位置的牌保留原样
        result = {}
        if is_declarer_side and dummy:
            # 庄家方：庄家和明手的手牌照原样
            result[declarer] = [Card(suit=c.suit, rank=c.rank) for c in state.hands.get(declarer, [])]
            result[dummy] = [Card(suit=c.suit, rank=c.rank) for c in state.hands.get(dummy, [])]
        else:
            # 防守方：只知道自己的牌
            result[perspective] = [Card(suit=c.suit, rank=c.rank) for c in own_hand]
            if dummy and state.phase != PlayPhase.LEAD:
                result[dummy] = [Card(suit=c.suit, rank=c.rank) for c in state.hands.get(dummy, [])]

        # 5. 分配未知牌到未知位置
        if self.constraints:
            self._distribute_biased(result, unknown_pool, remaining_counts)
        else:
            random.shuffle(unknown_pool)
            idx = 0
            for pos in POSITION_ORDER:
                if pos in result:
                    continue
                count = remaining_counts[pos]
                result[pos] = []
                for _ in range(count):
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
    ) -> None:
        """保证约束的牌张分配：有约束的位置先分配，用 _constrained_select 满足HCP和花色下限。"""
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

            constraint = self.constraints.get(pos)

            if constraint is None:
                # 无约束：随机选
                if count >= len(remaining):
                    result[pos] = list(remaining)
                    remaining = []
                else:
                    result[pos] = random.sample(remaining, count)
                    for c in result[pos]:
                        remaining.remove(c)
            else:
                # 有约束：保证满足约束的选取
                result[pos] = self._constrained_select(remaining, count, constraint)
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
