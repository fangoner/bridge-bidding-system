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
- **OutcomeVector**：长度 N 的**布尔**向量，N = possible worlds 数量，
  每个元素 = 1（该 world 下 our_side 达成目标）或 0（未达成）。
  与原论文一致：目标 = 庄家方赢墩≥tricks_needed / 防守方赢墩≥14-tricks_needed。
- **ParetoFront**：不被支配的 OutcomeVector 集合。

搜索规则：
- **Max 节点（我方）**：对每个候选 move 递归得到子 Pareto front，
  最终 front = 所有子 fronts 的并集（再去支配）。Max 保留所有非支配选项。
- **Min 节点（对手方）**：假设 Min 完美信息，对每个 world 独立选最小化
  our_side 成功率的 move。组合所有 worlds 得单一 OutcomeVector。
- **叶子节点**：对每个 world 调用 DDS 得庄家赢墩数，与 goal 比较得 0/1。
- **根节点选牌**：Maximin——最大化最小成功率，平局时按成功率均值决胜。

我方/对手方判定：
- our_side = {perspective, partner(perspective)}
- 当 perspective 是庄家方时：our_side = {庄家, 明手}，Min = 防守方
- 当 perspective 是防守方时：our_side = {防守方A, 防守方B}，Min = 庄家方

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

from bridge.mcts.dd_search import (
    _to_ep, _hands_to_pbn, _SUIT_MAP, _RANK_MAP,
    _DENOM_TO_SUIT, _RANK_TO_CHAR, _has_duplicates,
)


# ── 数据结构 ──

class OutcomeVector:
    """长度 N 的布尔向量。每元素 = 1（our_side 达成目标）或 0（未达成）。
    useful_mask[i]=False 表示该 world 已 impossible，比较时跳过。"""

    __slots__ = ("values", "useful_mask")

    def __init__(self, values: List[int], useful_mask: List[bool] = None):
        self.values = list(values)
        n = len(self.values)
        self.useful_mask = list(useful_mask) if useful_mask is not None else [True] * n

    def __len__(self) -> int:
        return len(self.values)

    def __getitem__(self, idx: int) -> int:
        return self.values[idx]

    def success_rate(self) -> float:
        """成功率（0.0-1.0）：useful worlds 中 1 的比例。"""
        useful_vals = [v for v, m in zip(self.values, self.useful_mask) if m]
        if not useful_vals:
            return 0.0
        return sum(useful_vals) / len(useful_vals)

    def worst(self) -> int:
        """useful worlds 中的最小值（0 或 1）。Maximin 选牌用。"""
        useful_vals = [v for v, m in zip(self.values, self.useful_mask) if m]
        if not useful_vals:
            return 0
        return min(useful_vals)

    def count_success(self) -> int:
        """成功 world 的数量。"""
        return sum(1 for v, m in zip(self.values, self.useful_mask) if m and v == 1)

    def dominates(self, other: "OutcomeVector") -> bool:
        """self 是否支配 other。"""
        if len(self.values) != len(other.values):
            return False
        has_strict = False
        for i in range(len(self.values)):
            if not self.useful_mask[i] or not other.useful_mask[i]:
                continue
            if self.values[i] < other.values[i]:
                return False
            if self.values[i] > other.values[i]:
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
        n = len(self.values)
        won = self.count_success()
        total = sum(1 for m in self.useful_mask if m)
        s = "".join("x" if not m else str(v) for v, m in zip(self.values, self.useful_mask))
        return f"OV[{s}]({won}/{total}={self.success_rate():.2f})"


class ParetoFront:
    """Pareto 前沿：不被支配的 OutcomeVector 集合。"""

    def __init__(self, vectors: List[OutcomeVector] = None):
        self.vectors: List[OutcomeVector] = []
        for v in (vectors or []):
            self.add(v)

    def add(self, candidate: OutcomeVector) -> bool:
        for existing in self.vectors:
            if existing.dominates(candidate) or existing == candidate:
                return False
        self.vectors = [v for v in self.vectors if not candidate.dominates(v)]
        self.vectors.append(candidate)
        return True

    def union(self, other: "ParetoFront") -> "ParetoFront":
        result = ParetoFront(list(self.vectors))
        for v in other.vectors:
            result.add(v)
        return result

    def best_score(self) -> float:
        """最高成功率（用于显示）。"""
        if not self.vectors:
            return 0.0
        return max(v.success_rate() for v in self.vectors)

    def best_vector(self) -> Optional[OutcomeVector]:
        """成功率最高的向量（用于显示）。"""
        if not self.vectors:
            return None
        return max(self.vectors, key=lambda v: v.success_rate())

    def maximin_vector(self) -> Optional[OutcomeVector]:
        """Maximin 选牌：优先最大化最小成功率，次按成功率均值决胜。"""
        if not self.vectors:
            return None
        # primary: max worst (0 or 1), secondary: max success_rate
        return max(self.vectors, key=lambda v: (v.worst(), v.success_rate()))

    def maximin_score(self) -> float:
        v = self.maximin_vector()
        return v.success_rate() if v else 0.0

    def __len__(self) -> int:
        return len(self.vectors)

    def __iter__(self):
        return iter(self.vectors)

    def __repr__(self) -> str:
        return f"PF({len(self.vectors)}: {[repr(v) for v in self.vectors[:3]]})"


# ── αμ 搜索器 ──

class AlphaMuSearch:
    """αμ 搜索算法实现。

    在残局（每手 ≤8 张）启用，用 belief tracker 的粒子作为 possible worlds。
    Max = 我方，必须在所有 worlds 选同一动作。
    Min = 对手方，假设完美信息，每个 world 独立选最优动作。
    根节点用 Maximin 选牌。
    """

    def __init__(self, sampler: DealSampler = None,
                 num_worlds: int = 20,
                 max_depth: int = 4,
                 time_limit: float = 8.0,
                 dds_budget: int = 3000):
        if not ENDPLAY_AVAILABLE:
            raise RuntimeError("endplay library not available (pip install endplay)")
        self.sampler = sampler or DealSampler()
        self.num_worlds = num_worlds
        self.max_depth = max_depth
        self.time_limit = time_limit
        self._start_time: float = 0
        self._nodes_searched: int = 0
        self._dds_calls: int = 0
        self._err_stats: Dict[str, int] = {
            "path_A_move_not_in_hand": 0,
            "path_B_duplicates": 0,
            "path_C_empty_result": 0,
            "path_E_exception": 0,
            "path_D_ok": 0,
            "path_X_unequal_hands": 0,
            "world_cut_0": 0,
            "world_cut_1": 0,
            "min_dds_fallback": 0,
        }
        self._dds_budget = dds_budget
        self._err_samples: Dict[str, str] = {}
        # 内部状态（search 时设置）
        self._goal: int = 0          # our_side 需要达到的赢墩数
        self._is_our_side_declarer: bool = True

    def search(self, state: PlayState) -> dict:
        self._start_time = time.time()
        self._nodes_searched = 0
        self._dds_calls = 0
        self._err_stats = {k: 0 for k in self._err_stats}
        self._err_samples = {}

        perspective = state.current_player
        declarer = state.contract.declarer
        dummy = state.dummy
        trump = state.contract.suit
        tricks_needed = state.contract.tricks_needed

        import os
        _debug_path = os.path.join(os.path.dirname(__file__), "..", "..", "alpha_mu_debug.log")
        with open(_debug_path, "w", encoding="utf-8") as _f:
            _f.write(f"[αμ ROOT] perspective={perspective}, declarer={declarer}, dummy={dummy}\n")
            _f.write(f"decl_tricks={state.declarer_tricks}, def_tricks={state.defender_tricks}\n")
            _f.write(f"hand_sizes={ {p: len(h) for p, h in state.hands.items()} }\n")
            _f.write(f"current_trick_cards={len(state.current_trick.cards)}\n")
            for p in ["北", "东", "南", "西"]:
                _f.write(f"  {p}: {[str(c) for c in state.hands.get(p, [])]}\n")
        print(f"[αμ] perspective={perspective}, declarer={declarer}, dummy={dummy}, "
              f"decl_tricks={state.declarer_tricks}, def_tricks={state.defender_tricks}, "
              f"hand_sizes={ {p: len(h) for p, h in state.hands.items()} }, "
              f"current_trick_cards={len(state.current_trick.cards)}")

        playable = state.get_playable_cards(perspective)
        if len(playable) == 1:
            return {
                "card": playable[0],
                "reasoning": "αμ: 唯一选择",
                "full_output": {"推荐出牌": str(playable[0])},
            }

        # ── 1. 生成 possible worlds ──
        if self.sampler.belief_tracker is not None:
            self.sampler.belief_tracker.prepare(state, perspective)
        worlds: List[Dict[str, List[Card]]] = []
        for _ in range(self.num_worlds):
            try:
                w = self.sampler.sample(state, perspective)
                if w is not None:
                    worlds.append(w)
            except Exception:
                continue
        if not worlds:
            raise RuntimeError("αμ: 无法生成 possible worlds")

        # 诊断
        has_constraints = bool(getattr(self.sampler, 'constraints', None))
        if has_constraints:
            constr = self.sampler.constraints
            print(f"[αμ] 约束: { {p: f'HCP[{c.min_hcp}-{c.max_hcp}]' for p, c in constr.items()} }")

        n_worlds = len(worlds)

        # ── 我方/对手方 + 目标设定 ──
        partner = PARTNERS.get(perspective, perspective)
        our_side = frozenset({perspective, partner})
        self._is_our_side_declarer = our_side == frozenset({declarer, dummy})
        # our_side 需要达到的赢墩数
        if self._is_our_side_declarer:
            self._goal = tricks_needed
        else:
            self._goal = 14 - tricks_needed  # 防守方需要 ≥ 14-tricks_needed 墩

        # ── 2. 递归搜索 ──
        world_decl_tricks = [state.declarer_tricks] * n_worlds
        world_def_tricks = [state.defender_tricks] * n_worlds

        move_fronts: List[Tuple[Card, ParetoFront]] = []
        for move in playable:
            if self._time_up():
                break
            front = self._search_recursive(
                state, worlds, world_decl_tricks, world_def_tricks,
                move, perspective, depth=0,
                declarer=declarer, dummy=dummy, trump=trump,
                tricks_needed=tricks_needed, our_side=our_side,
            )
            move_fronts.append((move, front))

        if not move_fronts:
            return {
                "card": playable[0],
                "reasoning": "αμ: 超时回退",
                "full_output": {"推荐出牌": str(playable[0])},
            }

        # ── 3. 根节点选牌：Maximin ──
        move_scores: List[dict] = []
        best_move = None
        best_key = (-1, -1.0)  # (worst, success_rate)

        for move, front in move_fronts:
            mv = front.maximin_vector()
            worst = mv.worst() if mv else 0
            rate = mv.success_rate() if mv else 0.0
            bonus = self._rank_bonus(move)
            # display_score: 转换为庄家赢墩的预期成功率（与 DD 引擎一致）
            display_score = rate

            move_scores.append({
                "card": str(move),
                "success_rate": round(rate, 3),
                "worst": worst,
                "success_count": mv.count_success() if mv else 0,
                "total_useful": sum(1 for m in mv.useful_mask if m) if mv else 0,
                "front_size": len(front),
                "best_vector": repr(mv) if mv else "∅",
            })
            key = (worst, rate + bonus)
            if key > best_key:
                best_key = key
                best_move = move

        move_scores.sort(key=lambda s: (s["worst"], s["success_rate"]), reverse=True)

        elapsed = time.time() - self._start_time
        top_str = ", ".join(
            f"{s['card']}({s['success_rate']:.0%})"
            for s in move_scores[:5]
        )
        reasoning = (
            f"αμ搜索: {n_worlds} worlds, depth≤{self.max_depth}, "
            f"{self._nodes_searched} nodes, {self._dds_calls} DDS calls, "
            f"{elapsed:.1f}s. Top: {top_str}"
        )

        err_diag = " | ".join(
            f"{k}={v}" for k, v in self._err_stats.items() if v > 0
        )
        err_samples_str = "; ".join(
            f"[{k}] {v[:200]}" for k, v in self._err_samples.items()
        )

        return {
            "card": best_move,
            "reasoning": reasoning,
            "full_output": {
                "推荐出牌": str(best_move),
                "核心逻辑": reasoning,
                "候选对比": str(move_scores),
                "局面评估": f"αμ搜索：{n_worlds}个possible worlds联合评估",
                "DDS诊断": f"DDS路径统计: {err_diag} | 样本: {err_samples_str}",
                "mcts_stats": {
                    "iterations": self._dds_calls,
                    "time_sec": round(elapsed, 2),
                    "candidates": move_scores,
                    "num_worlds": n_worlds,
                    "nodes_searched": self._nodes_searched,
                    "algorithm": "alpha_mu",
                    "err_stats": dict(self._err_stats),
                    "err_samples": dict(self._err_samples),
                },
            },
        }

    # ── 递归搜索 ──

    def _search_recursive(
        self,
        state: PlayState,
        worlds: List[Dict[str, List[Card]]],
        world_decl_tricks: List[int],
        world_def_tricks: List[int],
        move: Card,
        current_player: str,
        depth: int,
        declarer: str,
        dummy: str,
        trump: str,
        tricks_needed: int,
        our_side: frozenset,
    ) -> ParetoFront:
        self._nodes_searched += 1
        n = len(worlds)
        if self._time_up():
            return ParetoFront([OutcomeVector([0] * n)])

        next_states: List[Tuple[Dict[str, List[Card]], dict]] = []
        trick_state = get_current_trick_state(state)

        for w_idx, world in enumerate(worlds):
            if world is None:
                next_states.append((None, {"impossible": True}))
                continue
            hands = {pos: [Card(suit=c.suit, rank=c.rank) for c in cards]
                     for pos, cards in world.items()}
            if move not in hands.get(current_player, []):
                next_states.append((None, {"impossible": True}))
                continue
            from bridge.mcts.state_utils import apply_play_to_state
            new_hands, new_current, new_trick, decl_tricks, def_tricks, trick_done = \
                apply_play_to_state(
                    hands, current_player, move, trick_state,
                    world_decl_tricks[w_idx], world_def_tricks[w_idx],
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

        return self._evaluate_state(
            next_states, n, state, depth,
            declarer, dummy, trump, tricks_needed,
            our_side,
        )

    def _evaluate_state(
        self,
        next_states: List[Tuple[Dict[str, List[Card]], dict]],
        n: int,
        state: PlayState,
        depth: int,
        declarer: str,
        dummy: str,
        trump: str,
        tricks_needed: int,
        our_side: frozenset,
    ) -> ParetoFront:
        next_player = None
        for ns in next_states:
            if not ns[1].get("impossible"):
                next_player = ns[1]["new_current"]
                break

        # World Cuts
        useful_count = sum(1 for ns in next_states if not ns[1].get("impossible"))
        if useful_count == 0 or next_player is None:
            self._err_stats["world_cut_0"] += 1
            return ParetoFront([OutcomeVector([0] * n, [False] * n)])
        if useful_count == 1:
            self._err_stats["world_cut_1"] += 1
            return self._evaluate_leaf(
                next_states, n, declarer, dummy, trump, tricks_needed)

        is_next_max = next_player in our_side

        # Leaf check
        should_leaf = depth >= self.max_depth
        if not should_leaf:
            for ns in next_states:
                if not ns[1].get("impossible"):
                    remaining = sum(len(h) for h in ns[0].values())
                    if remaining <= 4:
                        should_leaf = True
                        break
        if should_leaf:
            return self._evaluate_leaf(
                next_states, n, declarer, dummy, trump, tricks_needed)

        if is_next_max:
            candidate_moves = self._collect_candidate_moves(next_states, next_player)
            if not candidate_moves:
                return self._evaluate_leaf(
                    next_states, n, declarer, dummy, trump, tricks_needed)
            updated_worlds, next_world_decl, next_world_def = \
                self._extract_updated_worlds(next_states)
            combined_front = ParetoFront()
            for child_move in candidate_moves:
                if self._time_up():
                    break
                child_state = self._build_child_state(state, next_states, child_move)
                if child_state is None:
                    continue
                child_front = self._search_recursive(
                    child_state, updated_worlds,
                    next_world_decl, next_world_def,
                    child_move, next_player, depth + 1,
                    declarer, dummy, trump, tricks_needed, our_side,
                )
                combined_front = combined_front.union(child_front)
            return combined_front if combined_front.vectors else self._evaluate_leaf(
                next_states, n, declarer, dummy, trump, tricks_needed)
        else:
            return self._min_node_evaluate(
                next_states, n, next_player,
                state, depth,
                declarer, dummy, trump, tricks_needed,
                our_side,
            )

    def _min_node_evaluate(
        self,
        next_states: List[Tuple[Dict[str, List[Card]], dict]],
        n: int,
        min_player: str,
        state: PlayState,
        depth: int,
        declarer: str,
        dummy: str,
        trump: str,
        tricks_needed: int,
        our_side: frozenset,
    ) -> ParetoFront:
        # N>5 时回退 DDS（递归状态不一致风险高）
        if n > 5:
            return self._evaluate_min_dds(
                next_states, n, min_player,
                declarer, dummy, trump, tricks_needed)

        # World Cuts
        useful_count = sum(1 for _, ns_info in next_states
                          if not ns_info.get("impossible"))
        if useful_count == 0:
            self._err_stats["world_cut_0"] += 1
            return ParetoFront([OutcomeVector([0] * n, [False] * n)])

        result_vector = [0] * n
        useful_mask = [True] * n

        for w_idx, (hands, ns_info) in enumerate(next_states):
            if ns_info.get("impossible"):
                useful_mask[w_idx] = False
                continue
            min_hand = hands.get(min_player, [])
            if not min_hand:
                useful_mask[w_idx] = False
                continue
            trick_state = ns_info["new_trick"]
            from bridge.mcts.state_utils import get_playable_from_hands
            candidate_moves = get_playable_from_hands(hands, min_player, trick_state)
            if not candidate_moves:
                useful_mask[w_idx] = False
                continue

            # Min 想最小化 our_side 成功（0 = Min 胜）
            best_for_min = 1  # 初始最差：our_side 成功
            for min_move in candidate_moves:
                if self._time_up():
                    break
                modified_next_states = []
                for w2_idx, (w2_hands, w2_ns_info) in enumerate(next_states):
                    if w2_ns_info.get("impossible") or w2_hands is None:
                        modified_next_states.append((None, {"impossible": True}))
                    elif w2_idx == w_idx:
                        from bridge.mcts.state_utils import apply_play_to_state
                        new_hands, new_current, new_trick, decl_t, def_t, td = \
                            apply_play_to_state(
                                w2_hands, min_player, min_move, trick_state,
                                ns_info["decl_tricks"], ns_info["def_tricks"],
                                trump, declarer, dummy,
                            )
                        modified_next_states.append((new_hands, {
                            "new_current": new_current,
                            "new_trick": new_trick,
                            "decl_tricks": decl_t,
                            "def_tricks": def_t,
                            "trick_done": td,
                            "impossible": False,
                        }))
                    else:
                        modified_next_states.append((w2_hands, w2_ns_info))

                child_state = self._build_min_child_state(state, modified_next_states)
                child_front = self._evaluate_state(
                    modified_next_states, n, child_state,
                    depth + 1,
                    declarer, dummy, trump, tricks_needed,
                    our_side,
                )
                # Min 最小化 our_side 成功
                our_success = child_front.best_score()
                if our_success < best_for_min:
                    best_for_min = our_success
                    if best_for_min == 0:
                        break
            result_vector[w_idx] = int(best_for_min)

        return ParetoFront([OutcomeVector(result_vector, useful_mask)])

    @staticmethod
    def _worlds_consistent(next_states) -> tuple:
        ref = None
        for _, ns_info in next_states:
            if ns_info.get("impossible"):
                continue
            cur = ns_info.get("new_current")
            if ref is None:
                ref = cur
            elif cur != ref:
                return False, None
        return True, ref

    def _build_min_child_state(
        self,
        state: PlayState,
        next_states: List[Tuple[Dict[str, List[Card]], dict]],
    ) -> PlayState:
        import copy
        for hands, ns_info in next_states:
            if ns_info.get("impossible") or hands is None:
                continue
            child_state = copy.copy(state)
            child_state.hands = {pos: [Card(suit=c.suit, rank=c.rank) for c in cards]
                                for pos, cards in hands.items()}
            child_state.current_trick = Trick_from_dict(ns_info["new_trick"])
            child_state.current_player = ns_info["new_current"]
            child_state.declarer_tricks = ns_info["decl_tricks"]
            child_state.defender_tricks = ns_info["def_tricks"]
            return child_state
        return copy.copy(state)

    def _evaluate_min_dds(
        self,
        next_states: List[Tuple[Dict[str, List[Card]], dict]],
        n: int,
        min_player: str,
        declarer: str,
        dummy: str,
        trump: str,
        tricks_needed: int,
    ) -> ParetoFront:
        """Min 节点 DDS 直接评估（回退路径）。布尔版：Min 选使 our_side 失败(0)的 move。"""
        result_vector = [0] * n
        useful_mask = [True] * n

        for w_idx, (hands, ns_info) in enumerate(next_states):
            if ns_info.get("impossible"):
                useful_mask[w_idx] = False
                continue
            min_hand = hands.get(min_player, [])
            if not min_hand:
                useful_mask[w_idx] = False
                continue
            trick_state = ns_info["new_trick"]
            from bridge.mcts.state_utils import get_playable_from_hands
            candidate_moves = get_playable_from_hands(hands, min_player, trick_state)
            if not candidate_moves:
                useful_mask[w_idx] = False
                continue

            best_for_min = 1  # 初始：our_side 成功
            for min_move in candidate_moves:
                if self._time_up():
                    break
                decl_tricks = self._dds_evaluate_single_world(
                    hands, min_player, min_move, trick_state,
                    ns_info["decl_tricks"], ns_info["def_tricks"],
                    ns_info["trick_done"], declarer, dummy, trump,
                    tricks_needed,
                )
                our_tricks = decl_tricks if self._is_our_side_declarer else (13 - decl_tricks)
                success = 1 if our_tricks >= self._goal else 0
                if success < best_for_min:
                    best_for_min = success
                    if best_for_min == 0:
                        break
            result_vector[w_idx] = best_for_min

        return ParetoFront([OutcomeVector(result_vector, useful_mask)])

    def _evaluate_leaf(
        self,
        next_states: List[Tuple[Dict[str, List[Card]], dict]],
        n: int,
        declarer: str,
        dummy: str,
        trump: str,
        tricks_needed: int,
    ) -> ParetoFront:
        """叶子节点：对每个 world 调 DDS，转为布尔成功/失败。"""
        useful_count = sum(1 for _, ns_info in next_states
                          if not ns_info.get("impossible"))
        if useful_count == 0:
            self._err_stats["world_cut_0"] += 1
            return ParetoFront([OutcomeVector([0] * n, [False] * n)])

        result_vector = [0] * n
        useful_mask = [True] * n

        for w_idx, (hands, ns_info) in enumerate(next_states):
            if ns_info.get("impossible"):
                useful_mask[w_idx] = False
                continue
            if hands is None:
                useful_mask[w_idx] = False
                continue

            decl_tricks = self._dds_evaluate_world_post_move(
                hands, ns_info, declarer, dummy, trump, tricks_needed)
            our_tricks = decl_tricks if self._is_our_side_declarer else (13 - decl_tricks)
            result_vector[w_idx] = 1 if our_tricks >= self._goal else 0

        return ParetoFront([OutcomeVector(result_vector, useful_mask)])

    # ── DDS 辅助 ──

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
        self._dds_calls += 1
        try:
            sim_hands = {pos: [Card(suit=c.suit, rank=c.rank) for c in cards]
                         for pos, cards in hands.items()}
            if move not in sim_hands.get(player, []):
                self._err_stats["path_A_move_not_in_hand"] += 1
                return 0
            sim_hands[player].remove(move)
            new_trick_cards = list(trick_state.get("cards", []))
            new_trick_cards.append((player, move))
            trick_leader = trick_state.get("leader") or player
            for pos, card in new_trick_cards:
                if card not in sim_hands.get(pos, []):
                    sim_hands[pos].append(card)
            if _has_duplicates(sim_hands):
                self._err_stats["path_B_duplicates"] += 1
                return 0

            pbn = _hands_to_pbn(sim_hands)
            deal = Deal(pbn)
            deal.trump = SUIT_TO_DENOM.get(trump, Denom.nt)
            if new_trick_cards:
                deal.first = POSITION_TO_PLAYER.get(trick_leader, Player.north)
                for _pos, card in new_trick_cards:
                    deal.play(_to_ep(card), from_hand=True)
            else:
                deal.first = POSITION_TO_PLAYER.get(player, Player.north)
            result = solve_board(deal)
            if not result:
                self._err_stats["path_C_empty_result"] += 1
                return 0
            curplayer_pos = PLAYER_TO_POSITION.get(deal.curplayer, player)
            curplayer_is_declarer = curplayer_pos in (declarer, dummy)
            remaining_tricks = 13 - (decl_tricks + def_tricks)
            side_tricks = max(score for _, score in result)
            if curplayer_is_declarer:
                total_decl_tricks = decl_tricks + side_tricks
            else:
                total_decl_tricks = decl_tricks + (remaining_tricks - side_tricks)
            self._err_stats["path_D_ok"] += 1
            return total_decl_tricks
        except Exception as e:
            self._err_stats["path_E_exception"] += 1
            if "path_E_exception" not in self._err_samples:
                import traceback
                self._err_samples["path_E_exception"] = (
                    f"exception={e}, player={player}, move={move}, "
                    f"decl={decl_tricks}, def={def_tricks}, "
                    f"trick_cards={[(p, str(c)) for p, c in trick_state.get('cards', [])]}, "
                    f"traceback={traceback.format_exc()[:500]}")
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
        self._dds_calls += 1
        try:
            sim_hands = {pos: [Card(suit=c.suit, rank=c.rank) for c in cards]
                         for pos, cards in hands.items()}
            if _has_duplicates(sim_hands):
                self._err_stats["path_B_duplicates"] += 1
                return 0
            new_trick = ns_info["new_trick"]
            new_current = ns_info["new_current"]
            decl_tricks = ns_info["decl_tricks"]
            def_tricks = ns_info["def_tricks"]
            trick_cards = new_trick.get("cards", [])
            for pos, card in trick_cards:
                if card not in sim_hands.get(pos, []):
                    sim_hands[pos].append(card)
            if _has_duplicates(sim_hands):
                self._err_stats["path_B_duplicates"] += 1
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
                self._err_stats["path_C_empty_result"] += 1
                return 0
            curplayer_pos = PLAYER_TO_POSITION.get(deal.curplayer, new_current)
            curplayer_is_declarer = curplayer_pos in (declarer, dummy)
            remaining_tricks = 13 - (decl_tricks + def_tricks)
            side_tricks = max(score for _, score in result)
            if curplayer_is_declarer:
                total_decl_tricks = decl_tricks + side_tricks
            else:
                total_decl_tricks = decl_tricks + (remaining_tricks - side_tricks)
            self._err_stats["path_D_ok"] += 1
            return total_decl_tricks
        except Exception as e:
            self._err_stats["path_E_exception"] += 1
            if "path_E_exception" not in self._err_samples:
                import traceback
                self._err_samples["path_E_exception"] = (
                    f"[leaf] exception={e}, "
                    f"decl={decl_tricks}, def={def_tricks}, "
                    f"trick_cards={[(p, str(c)) for p, c in ns_info.get('new_trick', {}).get('cards', [])]}, "
                    f"traceback={traceback.format_exc()[:500]}")
            return 0

    # ── 辅助方法 ──

    def _collect_candidate_moves(
        self,
        next_states: List[Tuple[Dict[str, List[Card]], dict]],
        next_player: str,
    ) -> List[Card]:
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
        child_move: Card,
    ) -> Optional[PlayState]:
        import copy
        for hands, ns_info in next_states:
            if ns_info.get("impossible") or hands is None:
                continue
            world_next = ns_info["new_current"]
            if child_move not in hands.get(world_next, []):
                continue
            child_state = copy.copy(state)
            child_state.hands = {pos: [Card(suit=c.suit, rank=c.rank) for c in cards]
                                 for pos, cards in hands.items()}
            child_state.current_trick = Trick_from_dict(ns_info["new_trick"])
            child_state.current_player = ns_info["new_current"]
            child_state.declarer_tricks = ns_info["decl_tricks"]
            child_state.defender_tricks = ns_info["def_tricks"]
            return child_state
        return None

    def _extract_updated_worlds(
        self,
        next_states: List[Tuple[Dict[str, List[Card]], dict]],
    ) -> Tuple[List[Optional[Dict[str, List[Card]]]], List[int], List[int]]:
        updated_worlds: List[Optional[Dict[str, List[Card]]]] = []
        world_decl: List[int] = []
        world_def: List[int] = []
        for hands, ns_info in next_states:
            if ns_info.get("impossible") or hands is None:
                updated_worlds.append(None)
                world_decl.append(0)
                world_def.append(0)
            else:
                updated_worlds.append(hands)
                world_decl.append(ns_info["decl_tricks"])
                world_def.append(ns_info["def_tricks"])
        return updated_worlds, world_decl, world_def

    @staticmethod
    def _rank_bonus(card: Card) -> float:
        """平局 tie-break，bonus 足够小不覆盖真实差异。"""
        rank_values = {
            'A': 0.009, 'K': 0.008, 'Q': 0.007, 'J': 0.006, 'T': 0.005,
            '9': 0.004, '8': 0.003, '7': 0.002, '6': 0.001,
            '5': 0.0009, '4': 0.0008, '3': 0.0007, '2': 0.0006,
        }
        return rank_values.get(card.rank, 0.0)

    def _time_up(self) -> bool:
        return time.time() - self._start_time > self.time_limit


def Trick_from_dict(trick_dict: dict):
    from bridge.play_types import Trick
    trick = Trick(trump=trick_dict.get("trump"))
    trick.leader = trick_dict.get("leader")
    for pos, card in trick_dict.get("cards", []):
        trick.add_card(pos, card)
    return trick
