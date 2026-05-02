import random
from typing import Dict, List, Set, Optional

from bridge.play_types import Card, PlayState, PlayPhase, POSITION_ORDER, PARTNERS
from bridge.mcts.state_utils import clone_hands, SUIT_DISPLAY_ORDER, RANK_DESC
from bridge.mcts.constraints import BidConstraint, validate_sample


# 一副完整的52张牌
ALL_CARDS = [Card(suit=s, rank=r) for s in SUIT_DISPLAY_ORDER for r in RANK_DESC]

# 约束验证最大重试次数（biased采样后大幅降低）
MAX_CONSTRAINT_RETRIES = 10


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
            # 超过重试上限，回退到无约束采样
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

        # 明手（庄家方视角始终可见；防守方首攻后可见）
        if dummy and perspective != dummy:
            dummy_visible = is_declarer_side or state.phase != PlayPhase.LEAD
            if dummy_visible:
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
        """约束感知的牌张分配：对每个未知位置加权随机选牌。

        权重设计：
        - 基础权重 1.0
        - 满足 suit_min 的花色 ×3
        - 大牌 HCP 权重 ×(1 + hcp * 0.3)
        - 随机扰动 key/weight 保证采样多样性
        """
        from bridge.mcts.constraints import HCP_MAP

        # 按约束优先级排序：有约束的位置优先分配
        unknown_positions = [p for p in POSITION_ORDER if p not in result]
        constrained_first = sorted(
            unknown_positions,
            key=lambda p: 0 if p in self.constraints else 1,
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
                # 有约束：加权随机选
                result[pos] = self._weighted_select(remaining, count, constraint)
                for c in result[pos]:
                    remaining.remove(c)

    @staticmethod
    def _weighted_select(
        pool: List[Card],
        count: int,
        constraint: "BidConstraint",
    ) -> List[Card]:
        """从 pool 中加权随机选出 count 张牌，倾向满足约束。"""
        from bridge.mcts.constraints import HCP_MAP

        if count >= len(pool):
            return list(pool)

        # key / weight: 高权重 → 低 adjusted → 排序靠前
        scored = []
        for c in pool:
            weight = 1.0
            for suit, min_len in constraint.suit_min.items():
                if c.suit == suit:
                    weight *= 3.0
            hcp = HCP_MAP.get(c.rank, 0)
            weight *= (1.0 + hcp * 0.3)
            adjusted = random.random() / weight
            scored.append((adjusted, c))

        scored.sort(key=lambda x: x[0])
        return [c for _, c in scored[:count]]
