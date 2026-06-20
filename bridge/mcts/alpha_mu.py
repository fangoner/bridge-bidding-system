"""αμ 搜索算法（Alpha-Mu Search）。

参考论文：
- Cazenave & Ventos, "The αμ Search Algorithm for the Game of Bridge", 2019
- Cazenave, Legras & Ventos, "Optimizing αμ", 2021

αμ 修复 PIMC 的两个核心缺陷：
1. **Strategy Fusion**：PIMC 在不同 possible world 中选不同 Max 动作，
   但实际游戏中 Max 必须在所有 worlds 选同一动作。αμ 强制 Max 节点
   在所有 worlds 上联合评估每个候选动作。
2. **Non-Locality**：PIMC 在每个节点选局部最优，但局部最优可能全局次优。
   αμ 用 Pareto Front 备份，保留多个非支配向量，避免过早收敛到局部最优。

核心数据结构：
- **OutcomeVector**：长度 N 的 0/1 向量，N = possible worlds 数量，
  每个元素表示该 world 下 Max 方是否达成目标（成约/赢墩≥阈值）。
- **ParetoFront**：不被支配的 OutcomeVector 集合。

搜索规则：
- **Max 节点（庄家方）**：对每个候选 move 递归得到子 Pareto front，
  最终 front = 所有子 fronts 的并集（再去支配）。Max 保留所有非支配选项。
- **Min 节点（防守方）**：假设 Min 完美信息，对每个 world 独立选最小化 Max
  结果的 move。组合所有 worlds 的最小值得到单一 OutcomeVector。
- **叶子节点**：对每个 world 调用 DDS（solve_board）得到赢墩数，
  与 tricks_needed 比较得 0/1。

触发条件：每手 ≤8 张牌（残局），endplay 可用。
"""

import time
from typing import Dict, List, Optional, Set, Tuple, FrozenSet

from bridge.play_types import Card, PlayState, PlayPhase, POSITION_ORDER, PARTNERS
from bridge.mcts.state_utils import (
    cards_to_hand_str, get_current_trick_state,
    POSITION_TO_PLAYER, PLAYER_TO_POSITION, SUIT_TO_DENOM,
)
from bridge.mcts.sampler import DealSampler, ALL_CARDS

try:
    from endplay import Deal
    from endplay.dds import solve_board
    from endplay.types import Card as EpCard, Denom, Player, Rank
    ENDPLAY_AVAILABLE = True
except ImportError:
    ENDPLAY_AVAILABLE = False

# 复用 dd_search 的 endplay 转换工具
from bridge.mcts.dd_search import (
    _to_ep, _hands_to_pbn, _SUIT_MAP, _RANK_MAP,
    _DENOM_TO_SUIT, _RANK_TO_CHAR, _has_duplicates,
)


# ──────────────────────────────────────────────────────────────────
# 数据结构
# ──────────────────────────────────────────────────────────────────

class OutcomeVector:
    """长度 N 的 0/1 向量，N = possible worlds 数量。

    每个元素表示该 world 下 Max 方是否达成目标。
    'x' 表示该 world 已 impossible（不再有效），比较时按 1 处理（乐观）。
    '-' 表示该 world 已 useless（已知为 0），比较时按 0 处理。
    """

    __slots__ = ("values", "useful_mask")

    def __init__(self, values: List[int], useful_mask: List[bool] = None):
        # values: 0/1 list，长度 = N
        # useful_mask: bool list，长度 = N，True 表示该 world 仍有效
        self.values = list(values)
        n = len(self.values)
        self.useful_mask = list(useful_mask) if useful_mask is not None else [True] * n

    def __len__(self) -> int:
        return len(self.values)

    def __getitem__(self, idx: int) -> int:
        return self.values[idx]

    def score(self) -> float:
        """向量平均分：在 useful worlds 上的平均值。"""
        useful_vals = [v for v, m in zip(self.values, self.useful_mask) if m]
        if not useful_vals:
            return 0.0
        return sum(useful_vals) / len(useful_vals)

    def dominates(self, other: "OutcomeVector") -> bool:
        """self 是否支配 other。

        规则（参考论文）：
        - useful worlds 上 self[i] >= other[i] 对所有 i
        - 至少一个 useful world 上 self[i] > other[i]
        - impossible worlds 在比较时按 1 处理（乐观）
        - useless worlds 按 0 处理
        """
        if len(self.values) != len(other.values):
            return False

        has_strict = False
        for i in range(len(self.values)):
            # 处理 impossible/useless worlds
            s_useful = self.useful_mask[i]
            o_useful = other.useful_mask[i]
            s_val = self.values[i] if s_useful else 1  # impossible → 1
            o_val = other.values[i] if o_useful else (1 if not o_useful and other.values[i] == 1 else 0)

            # 更精确：useless 的 world（已知为 0）按 0
            if not s_useful and self.values[i] == 0:
                s_val = 0
            if not o_useful and other.values[i] == 0:
                o_val = 0

            if s_val < o_val:
                return False
            if s_val > o_val:
                has_strict = True
        return has_strict

    def __eq__(self, other) -> bool:
        if not isinstance(other, OutcomeVector):
            return False
        return (self.values == other.values
                and self.useful_mask == other.useful_mask)

    def __hash__(self) -> int:
        return hash((tuple(self.values), tuple(self.useful_mask)))

    def __repr__(self) -> str:
        s = "".join(
            "x" if not m else ("1" if v == 1 else "0")
            for v, m in zip(self.values, self.useful_mask)
        )
        return f"OV[{s}]({self.score():.2f})"


class ParetoFront:
    """Pareto 前沿：不被支配的 OutcomeVector 集合。"""

    def __init__(self, vectors: List[OutcomeVector] = None):
        self.vectors: List[OutcomeVector] = []
        for v in (vectors or []):
            self.add(v)

    def add(self, candidate: OutcomeVector) -> bool:
        """添加候选向量，返回是否成功加入。

        - 若 candidate 被现有向量支配 → 不加入
        - 若 candidate 不被支配 → 加入，并移除被它支配的现有向量
        """
        # 检查是否被现有向量支配
        for existing in self.vectors:
            if existing.dominates(candidate) or existing == candidate:
                return False

        # 移除被 candidate 支配的现有向量
        self.vectors = [v for v in self.vectors if not candidate.dominates(v)]
        self.vectors.append(candidate)
        return True

    def union(self, other: "ParetoFront") -> "ParetoFront":
        """合并两个 Pareto front（去支配）。"""
        result = ParetoFront(list(self.vectors))
        for v in other.vectors:
            result.add(v)
        return result

    def best_score(self) -> float:
        """前沿中最高分向量的得分。"""
        if not self.vectors:
            return 0.0
        return max(v.score() for v in self.vectors)

    def best_vector(self) -> Optional[OutcomeVector]:
        """前沿中得分最高的向量。"""
        if not self.vectors:
            return None
        return max(self.vectors, key=lambda v: v.score())

    def __len__(self) -> int:
        return len(self.vectors)

    def __iter__(self):
        return iter(self.vectors)

    def __repr__(self) -> str:
        return f"PF({len(self.vectors)}: {[repr(v) for v in self.vectors[:3]]})"


# ──────────────────────────────────────────────────────────────────
# αμ 搜索器
# ──────────────────────────────────────────────────────────────────

class AlphaMuSearch:
    """αμ 搜索算法实现。

    在残局（每手 ≤8 张）启用，用 belief tracker 的粒子作为 possible worlds。
    Max = 庄家方（必须所有 worlds 选同一动作），Min = 防守方（假设完美信息）。
    """

    def __init__(self, sampler: DealSampler = None,
                 num_worlds: int = 20,
                 max_depth: int = 4,
                 time_limit: float = 8.0):
        """初始化 αμ 搜索器。

        Args:
            sampler: 采样器（用于生成 possible worlds）
            num_worlds: possible worlds 数量（粒子数）
            max_depth: 最大搜索深度（Max moves 数）
            time_limit: 时间限制（秒）
        """
        if not ENDPLAY_AVAILABLE:
            raise RuntimeError("endplay library not available (pip install endplay)")
        self.sampler = sampler or DealSampler()
        self.num_worlds = num_worlds
        self.max_depth = max_depth
        self.time_limit = time_limit
        self._start_time: float = 0
        self._nodes_searched: int = 0
        self._dds_calls: int = 0

    def search(self, state: PlayState) -> dict:
        """αμ 搜索主入口。

        Returns:
            与 DDSearch.search 兼容的 dict 格式：
            - card: 最优出牌 Card
            - reasoning: 推理说明
            - full_output: 详细统计
        """
        self._start_time = time.time()
        self._nodes_searched = 0
        self._dds_calls = 0

        perspective = state.current_player
        declarer = state.contract.declarer
        dummy = state.dummy
        trump = state.contract.suit
        tricks_needed = state.contract.tricks_needed

        playable = state.get_playable_cards(perspective)
        if len(playable) == 1:
            return {
                "card": playable[0],
                "reasoning": "αμ: 唯一选择",
                "full_output": {"推荐出牌": str(playable[0])},
            }

        # ── 1. 生成 possible worlds（粒子）──
        if self.sampler.belief_tracker is not None:
            self.sampler.belief_tracker.prepare(state, perspective)
        worlds: List[Dict[str, List[Card]]] = []
        for _ in range(self.num_worlds):
            try:
                w = self.sampler.sample(state, perspective)
                worlds.append(w)
            except Exception:
                continue
        if not worlds:
            raise RuntimeError("αμ: 无法生成 possible worlds")

        n_worlds = len(worlds)
        is_declarer_side = perspective in (declarer, dummy)

        # ── 2. 递归搜索 ──
        # 根节点：当前出牌者选 move
        # 若 Max 出牌 → 联合评估所有候选
        # 若 Min 出牌 → 但根节点是当前玩家选自己的 move，所以根节点总是 Max-like
        # （即"我"在所有 worlds 选同一 move）
        # 实际上 αμ 中 Max=我方，Min=对手
        # 当前出牌者视角：我=Max，对手=Min

        # 对每个候选 move 递归
        move_fronts: List[Tuple[Card, ParetoFront]] = []
        for move in playable:
            if self._time_up():
                break
            front = self._search_recursive(
                state, worlds, move, perspective, depth=0,
                declarer=declarer, dummy=dummy, trump=trump,
                tricks_needed=tricks_needed,
            )
            move_fronts.append((move, front))

        if not move_fronts:
            # 超时未完成任何 move 评估，回退到第一个候选
            return {
                "card": playable[0],
                "reasoning": "αμ: 超时回退",
                "full_output": {"推荐出牌": str(playable[0])},
            }

        # ── 3. 根节点选择：Max 选 score 最高的 move ──
        # Max 节点：所有 move 的 front 取并集，但选择时按单个 move 的 best_score
        # 因为 Max 必须选一个 move，所以选 best_score 最高的 move
        best_move = None
        best_score = -1.0
        move_scores: List[dict] = []

        for move, front in move_fronts:
            score = front.best_score()
            best_vec = front.best_vector()
            move_scores.append({
                "card": str(move),
                "score": round(score, 3),
                "front_size": len(front),
                "best_vector": repr(best_vec) if best_vec else "∅",
            })
            # 庄家方选高分，防守方选低分（最小化庄家成约概率）
            effective_score = score if is_declarer_side else (1.0 - score)
            if effective_score > best_score:
                best_score = effective_score
                best_move = move

        # 排序展示
        move_scores.sort(key=lambda s: s["score"],
                         reverse=is_declarer_side)

        elapsed = time.time() - self._start_time
        top_str = ", ".join(
            f"{s['card']}({s['score']:.2f})"
            for s in move_scores[:5]
        )
        reasoning = (
            f"αμ搜索: {n_worlds} worlds, depth≤{self.max_depth}, "
            f"{self._nodes_searched} nodes, {self._dds_calls} DDS calls, "
            f"{elapsed:.1f}s. Top: {top_str}"
        )

        return {
            "card": best_move,
            "reasoning": reasoning,
            "full_output": {
                "推荐出牌": str(best_move),
                "核心逻辑": reasoning,
                "候选对比": str(move_scores),
                "局面评估": f"αμ搜索：{n_worlds}个possible worlds联合评估",
                "mcts_stats": {
                    "iterations": self._dds_calls,
                    "time_sec": round(elapsed, 2),
                    "candidates": move_scores,
                    "num_worlds": n_worlds,
                    "nodes_searched": self._nodes_searched,
                    "algorithm": "alpha_mu",
                },
            },
        }

    def _search_recursive(
        self,
        state: PlayState,
        worlds: List[Dict[str, List[Card]]],
        move: Card,
        current_player: str,
        depth: int,
        declarer: str,
        dummy: str,
        trump: str,
        tricks_needed: int,
    ) -> ParetoFront:
        """递归搜索：在当前出牌者选 move 后，返回 Pareto front。

        - 若 current_player 是 Max 方（庄家方）→ Max 节点逻辑
        - 若 current_player 是 Min 方（防守方）→ Min 节点逻辑

        Args:
            state: 原始 PlayState（用于获取已完成墩、当前墩等）
            worlds: possible worlds 列表
            move: 当前要评估的 move
            current_player: 当前出牌者
            depth: 当前搜索深度（Max moves 计数）
        """
        self._nodes_searched += 1
        if self._time_up():
            # 超时返回悲观估计
            n = len(worlds)
            return ParetoFront([OutcomeVector([0] * n)])

        # 在每个 world 上应用 move，得到下一状态
        # 注意：worlds 是完整4家手牌，需要模拟出牌
        next_states: List[Tuple[Dict[str, List[Card]], dict]] = []
        # next_states[i] = (updated_hands_i, trick_state_i)

        trick_state = get_current_trick_state(state)
        trick_cards = trick_state["cards"]
        trick_leader = trick_state.get("leader")

        for w_idx, world in enumerate(worlds):
            # 复制 world 手牌
            hands = {pos: [Card(suit=c.suit, rank=c.rank) for c in cards]
                     for pos, cards in world.items()}

            # 应用 move
            if move not in hands.get(current_player, []):
                # 该 world 中 current_player 没有 move（采样不一致）
                # 标记该 world 为 impossible
                next_states.append((None, {"impossible": True}))
                continue

            # 模拟出牌
            from bridge.mcts.state_utils import apply_play_to_state
            new_hands, new_current, new_trick, decl_tricks, def_tricks, trick_done = \
                apply_play_to_state(
                    hands, current_player, move, trick_state,
                    state.declarer_tricks, state.defender_tricks,
                    trump, declarer, dummy,
                )
            next_states.append((new_hands, {
                "new_current": new_current,
                "new_trick": new_trick,
                "decl_tricks": decl_tricks,
                "def_tricks": def_tricks,
                "trick_done": trick_done,
                "impossible": False,
            }))

        # 判断下一出牌者是 Max 还是 Min
        # 取第一个 possible world 的下一出牌者
        next_player = None
        for ns in next_states:
            if not ns[1].get("impossible"):
                next_player = ns[1]["new_current"]
                break

        if next_player is None:
            # 所有 worlds 都 impossible
            n = len(worlds)
            return ParetoFront([OutcomeVector([0] * n)])

        is_next_max = next_player in (declarer, dummy)

        # ── 检查是否到达叶子条件 ──
        # 叶子条件：depth >= max_depth 或 所有 world 手牌为空
        should_leaf = depth >= self.max_depth
        if not should_leaf:
            # 检查手牌是否快空（≤1 张时直接 DDS 评估）
            for ns in next_states:
                if not ns[1].get("impossible"):
                    remaining = sum(len(h) for h in ns[0].values())
                    if remaining <= 4:  # 总共≤4张牌=1墩
                        should_leaf = True
                        break

        if should_leaf:
            return self._evaluate_leaf(
                next_states, worlds, state, declarer, dummy, trump,
                tricks_needed, current_player, move,
            )

        # ── 内部节点：递归子节点 ──
        if is_next_max:
            # Max 节点：下一出牌者是庄家方
            # 对每个候选 move 递归，front = 所有子 fronts 的并集
            # 但 Max 必须选一个 move，所以这里返回所有候选 move 的 fronts 并集
            # 上层（根节点）会从中选 best_score 最高的 move

            # 收集下一出牌者的候选 moves（取所有 worlds 的并集）
            candidate_moves = self._collect_candidate_moves(
                next_states, next_player)

            if not candidate_moves:
                return self._evaluate_leaf(
                    next_states, worlds, state, declarer, dummy, trump,
                    tricks_needed, current_player, move,
                )

            # 构建子 state（用第一个 possible world 的状态作为代表）
            # 注意：αμ 中 Max 在所有 worlds 选同一 move，所以递归时
            # 传递相同的 move 给所有 worlds
            combined_front = ParetoFront()
            for child_move in candidate_moves:
                if self._time_up():
                    break
                # 构建子 state（更新当前墩、墩数）
                child_state = self._build_child_state(
                    state, next_states, next_player, child_move)
                if child_state is None:
                    continue
                child_front = self._search_recursive(
                    child_state, worlds, child_move, next_player, depth + 1,
                    declarer, dummy, trump, tricks_needed,
                )
                combined_front = combined_front.union(child_front)

            return combined_front if combined_front.vectors else self._evaluate_leaf(
                next_states, worlds, state, declarer, dummy, trump,
                tricks_needed, current_player, move,
            )
        else:
            # Min 节点：下一出牌者是防守方
            # Min 假设完美信息，可在每个 world 选不同 move
            # 对每个 world 独立选最小化 Max 结果的 move
            return self._min_node_evaluate(
                next_states, worlds, state, next_player, depth,
                declarer, dummy, trump, tricks_needed,
            )

    def _min_node_evaluate(
        self,
        next_states: List[Tuple[Dict[str, List[Card]], dict]],
        worlds: List[Dict[str, List[Card]]],
        state: PlayState,
        min_player: str,
        depth: int,
        declarer: str,
        dummy: str,
        trump: str,
        tricks_needed: int,
    ) -> ParetoFront:
        """Min 节点评估：每个 world 独立选最小化 Max 的 move。

        Min 假设完美信息，所以每个 world 可以选不同 move。
        对每个 world 找到使 Max 成约概率最低的 move，组合成单一 OutcomeVector。
        """
        n = len(worlds)
        result_vector = [1] * n  # 默认 Max 成约（乐观）
        useful_mask = [True] * n

        for w_idx, (hands, ns_info) in enumerate(next_states):
            if ns_info.get("impossible"):
                useful_mask[w_idx] = False
                continue

            # 该 world 中 Min 的候选 moves
            min_hand = hands.get(min_player, [])
            if not min_hand:
                useful_mask[w_idx] = False
                continue

            # 跟花色规则
            trick_state = ns_info["new_trick"]
            from bridge.mcts.state_utils import get_playable_from_hands
            candidate_moves = get_playable_from_hands(hands, min_player, trick_state)

            if not candidate_moves:
                useful_mask[w_idx] = False
                continue

            # 对每个候选 move，DDS 评估该 world 的结果
            best_for_min = 1  # Min 想最小化 Max，初始为最差（Max 成约）
            for min_move in candidate_moves:
                if self._time_up():
                    break
                # DDS 评估：在该 world 中应用 min_move 后，Max 是否成约
                made = self._dds_evaluate_single_world(
                    hands, min_player, min_move, trick_state,
                    ns_info["decl_tricks"], ns_info["def_tricks"],
                    ns_info["trick_done"], declarer, dummy, trump,
                    tricks_needed,
                )
                if made == 0:
                    best_for_min = 0
                    break  # Min 找到使 Max 不成约的 move，无需继续

            result_vector[w_idx] = best_for_min

        return ParetoFront([OutcomeVector(result_vector, useful_mask)])

    def _evaluate_leaf(
        self,
        next_states: List[Tuple[Dict[str, List[Card]], dict]],
        worlds: List[Dict[str, List[Card]]],
        state: PlayState,
        declarer: str,
        dummy: str,
        trump: str,
        tricks_needed: int,
        current_player: str,
        move: Card,
    ) -> ParetoFront:
        """叶子节点评估：对每个 world 调用 DDS，得 OutcomeVector。

        叶子条件：depth >= max_depth 或 手牌接近空。
        """
        n = len(worlds)
        result_vector = [0] * n
        useful_mask = [True] * n

        for w_idx, (hands, ns_info) in enumerate(next_states):
            if ns_info.get("impossible"):
                useful_mask[w_idx] = False
                continue

            if hands is None:
                useful_mask[w_idx] = False
                continue

            # DDS 评估：在该 world 中，从当前状态开始，Max 方最终赢墩数
            # 注意：此时 move 已应用，需要评估剩余局面
            made = self._dds_evaluate_world_post_move(
                hands, ns_info, declarer, dummy, trump, tricks_needed,
            )
            result_vector[w_idx] = 1 if made else 0

        return ParetoFront([OutcomeVector(result_vector, useful_mask)])

    def _dds_evaluate_single_world(
        self,
        hands: Dict[str, List[Card]],
        player: str,
        move: Card,
        trick_state: dict,
        decl_tricks: int,
        def_tricks: int,
        trick_done: bool,
        declarer: str,
        dummy: str,
        trump: str,
        tricks_needed: int,
    ) -> int:
        """DDS 评估单个 world：应用 move 后，Max 方是否成约。

        Returns:
            1 if Max 成约，0 otherwise
        """
        self._dds_calls += 1
        try:
            # 复制手牌并应用 move
            sim_hands = {pos: [Card(suit=c.suit, rank=c.rank) for c in cards]
                         for pos, cards in hands.items()}
            if move not in sim_hands.get(player, []):
                return 0

            sim_hands[player].remove(move)

            # 构建当前墩（含新出的 move）
            new_trick_cards = list(trick_state.get("cards", []))
            new_trick_cards.append((player, move))
            trick_leader = trick_state.get("leader") or player

            # 如果墩未完成，需要继续打到结束
            # 但 DDS solve_board 假设从当前出牌人开始，所以需要构建正确的 Deal
            # 简化：把当前墩所有牌加回手牌，让 solve_board 从当前墩开始

            # 加回当前墩牌到手牌
            for pos, card in new_trick_cards:
                if card not in sim_hands.get(pos, []):
                    sim_hands[pos].append(card)

            # 检查重复
            if _has_duplicates(sim_hands):
                return 0

            pbn = _hands_to_pbn(sim_hands)
            deal = Deal(pbn)
            deal.trump = SUIT_TO_DENOM.get(trump, Denom.nt)

            # 重放当前墩
            if new_trick_cards:
                deal.first = POSITION_TO_PLAYER.get(trick_leader, Player.north)
                for _pos, card in new_trick_cards:
                    deal.play(_to_ep(card), from_hand=True)
            else:
                deal.first = POSITION_TO_PLAYER.get(player, Player.north)

            result = solve_board(deal)
            # result: List[(EpCard, side_tricks)] — side_tricks 是 deal.curplayer 方的赢墩

            # 取任意一个结果（所有结果对应同一出牌方的赢墩）
            if not result:
                return 0

            curplayer_pos = PLAYER_TO_POSITION.get(deal.curplayer, player)
            curplayer_is_declarer = curplayer_pos in (declarer, dummy)

            # solve_board 返回的是 curplayer 方剩余赢墩（含当前墩）
            # 需要计算总赢墩
            remaining_tricks = 13 - (decl_tricks + def_tricks)
            # 当前墩可能未完成，solve_board 返回的是从当前出牌人开始剩余的所有墩
            # 但我们已经重放了当前墩已出的牌，所以 remaining_tricks 包含当前墩

            # 取第一个结果的赢墩数
            _, side_tricks = result[0]
            if curplayer_is_declarer:
                total_decl_tricks = decl_tricks + side_tricks
            else:
                total_decl_tricks = decl_tricks + (remaining_tricks - side_tricks)

            return 1 if total_decl_tricks >= tricks_needed else 0

        except Exception:
            return 0

    def _dds_evaluate_world_post_move(
        self,
        hands: Dict[str, List[Card]],
        ns_info: dict,
        declarer: str,
        dummy: str,
        trump: str,
        tricks_needed: int,
    ) -> int:
        """DDS 评估：move 已应用后的世界，Max 是否成约。

        ns_info 包含：new_current, new_trick, decl_tricks, def_tricks, trick_done
        """
        self._dds_calls += 1
        try:
            sim_hands = {pos: [Card(suit=c.suit, rank=c.rank) for c in cards]
                         for pos, cards in hands.items()}

            if _has_duplicates(sim_hands):
                return 0

            new_trick = ns_info["new_trick"]
            new_current = ns_info["new_current"]
            decl_tricks = ns_info["decl_tricks"]
            def_tricks = ns_info["def_tricks"]

            # 加回当前墩牌到手牌（solve_board 需要完整手牌）
            trick_cards = new_trick.get("cards", [])
            for pos, card in trick_cards:
                if card not in sim_hands.get(pos, []):
                    sim_hands[pos].append(card)

            if _has_duplicates(sim_hands):
                return 0

            pbn = _hands_to_pbn(sim_hands)
            deal = Deal(pbn)
            deal.trump = SUIT_TO_DENOM.get(trump, Denom.nt)

            trick_leader = new_trick.get("leader")
            if trick_cards:
                deal.first = POSITION_TO_PLAYER.get(trick_leader, Player.north)
                for _pos, card in trick_cards:
                    deal.play(_to_ep(card), from_hand=True)
            else:
                deal.first = POSITION_TO_PLAYER.get(new_current, Player.north)

            result = solve_board(deal)
            if not result:
                return 0

            curplayer_pos = PLAYER_TO_POSITION.get(deal.curplayer, new_current)
            curplayer_is_declarer = curplayer_pos in (declarer, dummy)

            remaining_tricks = 13 - (decl_tricks + def_tricks)
            _, side_tricks = result[0]

            if curplayer_is_declarer:
                total_decl_tricks = decl_tricks + side_tricks
            else:
                total_decl_tricks = decl_tricks + (remaining_tricks - side_tricks)

            return 1 if total_decl_tricks >= tricks_needed else 0

        except Exception:
            return 0

    def _collect_candidate_moves(
        self,
        next_states: List[Tuple[Dict[str, List[Card]], dict]],
        next_player: str,
    ) -> List[Card]:
        """收集下一出牌者在所有 possible worlds 中的候选 move 并集。"""
        from bridge.mcts.state_utils import get_playable_from_hands

        move_set: Set[Card] = set()
        for hands, ns_info in next_states:
            if ns_info.get("impossible") or hands is None:
                continue
            trick_state = ns_info["new_trick"]
            moves = get_playable_from_hands(hands, next_player, trick_state)
            for m in moves:
                move_set.add(m)
        return list(move_set)

    def _build_child_state(
        self,
        state: PlayState,
        next_states: List[Tuple[Dict[str, List[Card]], dict]],
        next_player: str,
        child_move: Card,
    ) -> Optional[PlayState]:
        """构建子 PlayState（用于递归）。

        注意：αμ 中 Max 在所有 worlds 选同一 move，所以子 state 的"当前墩"
        应反映 child_move 已出。但 worlds 各自的手牌不同，所以这里构建的
        state 主要用于获取 trick 结构，worlds 在递归时单独传递。
        """
        # 找一个 possible world 作为代表
        for hands, ns_info in next_states:
            if ns_info.get("impossible") or hands is None:
                continue
            # 检查 child_move 是否在该 world 的 next_player 手中
            if child_move not in hands.get(next_player, []):
                continue

            # 构建子 state：复制原 state，更新当前墩和墩数
            # 简化：直接修改 state 的副本
            import copy
            child_state = copy.copy(state)
            child_state.hands = {pos: [Card(suit=c.suit, rank=c.rank) for c in cards]
                                 for pos, cards in hands.items()}
            child_state.current_trick = Trick_from_dict(ns_info["new_trick"])
            child_state.current_player = ns_info["new_current"]
            child_state.declarer_tricks = ns_info["decl_tricks"]
            child_state.defender_tricks = ns_info["def_tricks"]
            return child_state

        return None

    def _time_up(self) -> bool:
        """检查是否超时。"""
        return time.time() - self._start_time > self.time_limit


def Trick_from_dict(trick_dict: dict):
    """从 dict 构建 Trick（用于 αμ 递归构建子 state）。"""
    from bridge.play_types import Trick
    trick = Trick(trump=trick_dict.get("trump"))
    trick.leader = trick_dict.get("leader")
    for pos, card in trick_dict.get("cards", []):
        trick.add_card(pos, card)
    return trick
