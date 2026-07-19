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
- **根节点选牌**：论文 §4.1 — "the highest score of all vectors in the Pareto front"。
  即 best_score = max(success_rate over all vectors in the front)，平局按出现顺序。

我方/对手方判定：
- our_side = {perspective, partner(perspective)}
- 当 perspective 是庄家方时：our_side = {庄家, 明手}，Min = 防守方
- 当 perspective 是防守方时：our_side = {防守方A, 防守方B}，Min = 庄家方

触发条件：每手 ≤8 张牌（残局），endplay 可用。
"""

import time
from typing import Dict, List, Optional, Set, Tuple, FrozenSet

from bridge.play_types import Card, PlayState, PARTNERS
from bridge.mcts.state_utils import get_current_trick_state
from bridge.mcts.sampler import DealSampler

# Phase 1a: ENDPLAY_AVAILABLE 兼容导出（DirectDDS 替代 endplay，总是可用）
ENDPLAY_AVAILABLE = True


# ── 数据结构 ──

class OutcomeVector:
    """长度 N 的布尔向量。每元素 = 1（our_side 达成目标）或 0（未达成）。
    useful_mask[i]=False 表示该 world 已 impossible，比较时跳过。

    附加 tricks_list：每个 world 下我方实际赢墩数，用于成功率相同时的 tie-break
    （宕牌时选少宕的，铁成时选超墩多的）。"""

    __slots__ = ("values", "useful_mask", "tricks_list")

    def __init__(self, values: List[int], useful_mask: List[bool] = None,
                 tricks_list: List[int] = None, _copy: bool = True):
        self.values = list(values) if _copy else values
        n = len(self.values)
        if _copy:
            self.useful_mask = list(useful_mask) if useful_mask is not None else [True] * n
            self.tricks_list = list(tricks_list) if tricks_list is not None else [0] * n
        else:
            self.useful_mask = useful_mask if useful_mask is not None else [True] * n
            self.tricks_list = tricks_list if tricks_list is not None else [0] * n

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

    def is_all_won(self) -> bool:
        """所有 useful world 是否都赢了（全 1 向量）。

        2021 论文 §Cut on Win: 若某子节点返回全 1 向量，Max 节点可立即截断。
        """
        for v, m in zip(self.values, self.useful_mask):
            if m and v == 0:
                return False
        return any(self.useful_mask)  # 至少有一个 useful world

    def avg_tricks(self) -> float:
        """我方平均赢墩数（tie-break 用）。"""
        useful_tricks = [t for t, m in zip(self.tricks_list, self.useful_mask) if m]
        if not useful_tricks:
            return 0.0
        return sum(useful_tricks) / len(useful_tricks)

    def min_tricks(self) -> int:
        """我方最差赢墩数（tie-break 用，maximin 风格）。"""
        useful_tricks = [t for t, m in zip(self.tricks_list, self.useful_mask) if m]
        if not useful_tricks:
            return 0
        return min(useful_tricks)

    def dominates(self, other: "OutcomeVector") -> bool:
        """self 是否支配 other。

        论文 §3.1: "v1 dominates v2 iff they have the same associated worlds,
        v1 >= v2 and exists i such that v1[i] > v2[i]"
        即 useful_mask 必须完全相同才能比较支配关系。
        """
        if len(self.values) != len(other.values):
            return False
        if self.useful_mask != other.useful_mask:
            return False
        has_strict = False
        for i in range(len(self.values)):
            if not self.useful_mask[i]:
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
        avg_t = self.avg_tricks()
        return f"OV[{s}]({won}/{total}={self.success_rate():.2f}, avg_tricks={avg_t:.1f})"


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
        # 原地 swap-pop 移除被支配向量，避免每次新建 list
        i = 0
        while i < len(self.vectors):
            if candidate.dominates(self.vectors[i]):
                self.vectors[i] = self.vectors[-1]
                self.vectors.pop()
            else:
                i += 1
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
                 M: int = 2,
                 time_limit: float = 8.0,
                 dds_budget: int = 3000):
        # DirectDDS: load dds.dll via ctypes (bundled with endplay)
        try:
            from bridge.mcts.direct_dds import _load_dll
            _load_dll()
        except Exception as e:
            raise RuntimeError(f"DDS library not available: {e}")
        self.sampler = sampler or DealSampler()
        self.num_worlds = num_worlds
        self.M = M  # 论文参数：Max 递归层数（M=1 退化为 PIMC，Min 不减 M）
        self.max_depth = M  # 兼容旧引用
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
            "tt_hit": 0,
            "early_cut": 0,
            "root_cut": 0,
            "cut_on_win": 0,  # 2021 论文
        }
        self._dds_budget = dds_budget
        self._err_samples: Dict[str, str] = {}
        # 内部状态（search 时设置）
        self._goal: int = 0          # our_side 需要达到的赢墩数
        self._is_our_side_declarer: bool = True
        self._debug_dds_log: List[str] = []  # DDS诊断日志（每次search重置）
        # 论文 §4.3 Transposition Table：缓存已搜索状态的 (front, best_move)
        # 配合 iterative deepening：M=k 搜索时复用 M=k-1 的结果
        self._tt: Dict[Tuple, Tuple[ParetoFront, Optional[Card]]] = {}
        # 论文 §4.3 Root Cut：上一次 iterative deepening 迭代的 best_score
        # 当根节点某 move 的 score == prev_best_score 时，停止搜索
        self._prev_best_score: float = -1.0
        self._is_root: bool = False  # 标记当前是否在根节点

    def search(self, state: PlayState) -> dict:
        self._nodes_searched = 0
        self._dds_calls = 0
        self._err_stats = {k: 0 for k in self._err_stats}
        self._err_samples = {}
        self._debug_dds_log = []
        self._tt = {}  # 论文 §4.3：每次 search 清空 transposition table
        self._prev_best_score = -1.0  # 论文 §4.3：root cut 用

        perspective = state.current_player
        actual_turn = state.current_player
        declarer = state.contract.declarer
        dummy = state.dummy
        # 明手不做决策：搜索视角改为庄家
        if perspective == dummy:
            perspective = declarer
        trump = state.contract.suit
        tricks_needed = state.contract.tricks_needed
        contract_str = f"{state.contract.level}{state.contract.suit}"

        import os
        _debug_path = os.path.join(os.path.dirname(__file__), "..", "..", "alpha_mu_debug.log")
        _trick_cards_str = [(p, str(c)) for p, c in state.current_trick.cards]
        with open(_debug_path, "w", encoding="utf-8") as _f:
            _f.write(f"[αμ ROOT] perspective={perspective}, actual_turn={actual_turn}, declarer={declarer}, dummy={dummy}\n")
            _f.write(f"contract={contract_str}, tricks_needed={tricks_needed}\n")
            _f.write(f"decl_tricks={state.declarer_tricks}, def_tricks={state.defender_tricks}\n")
            _f.write(f"hand_sizes={ {p: len(h) for p, h in state.hands.items()} }\n")
            _f.write(f"current_trick_cards={len(state.current_trick.cards)}, trick={_trick_cards_str}\n")
            _f.write(f"played_cards={[str(c) for trick in state.tricks for _, c in trick.cards]}\n")
            for p in ["北", "东", "南", "西"]:
                _f.write(f"  {p}: {[str(c) for c in state.hands.get(p, [])]}\n")
        print(f"[αμ] perspective={perspective}, actual_turn={actual_turn}, declarer={declarer}, dummy={dummy}, "
              f"contract={contract_str}, tricks_needed={tricks_needed}, "
              f"decl_tricks={state.declarer_tricks}, def_tricks={state.defender_tricks}, "
              f"hand_sizes={ {p: len(h) for p, h in state.hands.items()} }, "
              f"current_trick_cards={len(state.current_trick.cards)}, trick={_trick_cards_str}")

        playable_raw = state.get_playable_cards(actual_turn)
        # ── 排序：将牌优先，确保小将牌不会因超时排到末尾被截断 ──
        # 将牌：rank升序（小将牌先评估，它们是"将吃"的主力）
        # 副牌：rank降序（大牌先评估）
        trump_cards = [c for c in playable_raw if c.suit == trump]
        side_cards = [c for c in playable_raw if c.suit != trump]
        trump_cards.sort(key=lambda c: c.rank_value)
        side_cards.sort(key=lambda c: c.rank_value, reverse=True)
        playable = trump_cards + side_cards

        if len(playable) == 1:
            return {
                "card": playable[0],
                "reasoning": "αμ: 唯一选择",
                "full_output": {"推荐出牌": str(playable[0])},
            }

        # ── 1. 生成 possible worlds（均匀采样 + 分级约束验证）──
        # Phase 0a: 直接调用 sampler.sample_n()，等权均匀 world 集合
        worlds: List[Dict[str, List[Card]]] = []
        try:
            worlds = self.sampler.sample_n(self.num_worlds, state, perspective)
        except Exception:
            worlds = []
        if not worlds:
            raise RuntimeError("αμ: 无法生成 possible worlds")

        # 开始计时（粒子/worlds准备完成后才开始算搜索时间）
        self._start_time = time.time()

        # 诊断
        has_constraints = bool(getattr(self.sampler, 'constraints', None))
        if has_constraints:
            constr = self.sampler.constraints
            print(f"[αμ] 约束: { {p: f'HCP[{c.min_hcp}-{c.max_hcp}]' for p, c in constr.items()} }")

        n_worlds = len(worlds)
        print(f"[αμ] worlds生成完成: {n_worlds}个, 耗时{time.time()-self._start_time:.2f}s")

        # ── 我方/对手方 + 目标设定 ──
        partner = PARTNERS.get(perspective, perspective)
        our_side = frozenset({perspective, partner})
        self._is_our_side_declarer = our_side == frozenset({declarer, dummy})
        # our_side 需要达到的赢墩数
        if self._is_our_side_declarer:
            self._goal = tricks_needed
        else:
            self._goal = 14 - tricks_needed  # 防守方需要 ≥ 14-tricks_needed 墩

        # ── 2. 递归搜索（论文 §4.3 Iterative Deepening + Root Cuts）──
        # 转换为 bitmap 手牌：所有内部节点用位运算替代 Card 列表操作
        from bridge.mcts.bit_hands import world_to_bits
        worlds_bits = [world_to_bits(w) for w in worlds]
        world_decl_tricks = [state.declarer_tricks] * n_worlds
        world_def_tricks = [state.defender_tricks] * n_worlds

        # 论文 §4.3：从 M=1 开始，逐步增加到 self.M
        # M=1 退化为 PIMC，速度快；M=k 的结果存入 _tt 供 M=k+1 复用
        # 每次 M 迭代的 best_score 存入 _prev_best_score，供下一次 root cut
        # 候选顺序：M=k 迭代时按 M=k-1 的得分降序排，best 在前，便于 root cut 提前触发
        best_move_overall = None
        best_score_overall = -1.0
        move_fronts: List[Tuple[Card, ParetoFront]] = []
        iterative_results: Dict[int, List[Tuple[Card, ParetoFront]]] = {}
        prev_iter_scores: Dict[Card, float] = {}  # M=k-1 各候选得分

        for current_M in range(1, self.M + 1):
            if self._time_up():
                break
            self._is_root = True
            print(f"[αμ] Iterative Deepening M={current_M}/{self.M}, prev_best={self._prev_best_score:.3f}")
            iter_move_fronts: List[Tuple[Card, ParetoFront]] = []
            iter_best_score = -1.0

            # M=k 迭代：按 M=k-1 得分降序排候选（best 在前）
            # 2021 §Empty Entry: 标记上轮被 root cut 跳过的候选
            empty_candidates = set()
            if prev_iter_scores and current_M > 1:
                ordered_playable = sorted(
                    playable,
                    key=lambda c: prev_iter_scores.get(c, -1.0),
                    reverse=True,
                )
                # 未出现在 prev_iter_scores 中的候选 = 被上轮 root cut 跳过
                empty_candidates = {c for c in playable
                                   if c not in prev_iter_scores}
            else:
                ordered_playable = playable

            # 论文 §4.3 Bound Reuse：M=k 的初始 alpha = M=k-1 的最佳 front
            # 将 M=k-1 所有候选 front 的并集作为 M=k 搜索的初始 alpha 界限
            # 这使 Min 节点 Early Cut 能利用 TT 中 M=k-1 的结果进行剪枝
            root_alpha = ParetoFront()
            if current_M > 1 and (current_M - 1) in iterative_results:
                for _, prev_front in iterative_results[current_M - 1]:
                    root_alpha = root_alpha.union(prev_front)
                print(f"[αμ] Bound Reuse: M={current_M} 初始 alpha 含 {len(root_alpha.vectors)} vectors (来自 M={current_M-1})")

            for i, move in enumerate(ordered_playable):
                if self._time_up():
                    break

                # 2021 §Empty Entry: 上轮 root cut 跳过的候选，先浅层评估填 TT
                if move in empty_candidates and current_M > 2:
                    _ = self._search_recursive(
                        state, worlds_bits, world_decl_tricks, world_def_tricks,
                        move, actual_turn, M_remaining=0,  # leaf only
                        declarer=declarer, dummy=dummy, trump=trump,
                        tricks_needed=tricks_needed, our_side=our_side,
                        alpha=ParetoFront(),
                        deep_alpha=ParetoFront(),
                    )
                    self._err_stats["empty_entry"] = self._err_stats.get("empty_entry", 0) + 1

                front = self._search_recursive(
                    state, worlds_bits, world_decl_tricks, world_def_tricks,
                    move, actual_turn, M_remaining=current_M - 1,
                    declarer=declarer, dummy=dummy, trump=trump,
                    tricks_needed=tricks_needed, our_side=our_side,
                    alpha=root_alpha,
                    deep_alpha=ParetoFront(),  # 根节点：无祖先
                )
                iter_move_fronts.append((move, front))
                # Max 节点：累积最佳 front，收紧后续候选的 alpha 界限
                root_alpha = root_alpha.union(front)
                move_score = front.best_score()
                print(f"[αμ] M={current_M} 候选 {i+1}/{len(ordered_playable)} {move} 完成: score={move_score:.3f}, nodes={self._nodes_searched}, dds={self._dds_calls}, 耗时{time.time()-self._start_time:.2f}s")

                # 论文 §4.3 Root Cut：M=k 某候选 score == M=k-1 的 best_score 则停止
                # "the same probability of winning than the best move of the previous iteration"
                # 更深的搜索（更大M）因 strategy fusion 只能持平或更悲观，故等同时已触上界。
                # 浮点容差 0.001 处理整数除法产生的有理数截断。
                if (self._prev_best_score > 0
                        and abs(move_score - self._prev_best_score) < 0.001
                        and current_M > 1):
                    self._err_stats["root_cut"] += 1
                    print(f"[αμ] Root Cut: {move} score={move_score:.3f} >= prev_best={self._prev_best_score:.3f}, 停止搜索")
                    break

                if move_score > iter_best_score:
                    iter_best_score = move_score

            self._is_root = False
            self._prev_best_score = iter_best_score
            prev_iter_scores = {m: f.best_score() for m, f in iter_move_fronts}
            iterative_results[current_M] = iter_move_fronts
            move_fronts = iter_move_fronts  # 用最新迭代的结果

            # 如果当前迭代没完成所有候选（超时），用更深的迭代意义不大
            if len(iter_move_fronts) < len(playable):
                break

        if not move_fronts:
            return {
                "card": playable[0],
                "reasoning": "αμ: 超时回退",
                "full_output": {"推荐出牌": str(playable[0])},
            }

        # ── 3. 根节点选牌（论文 §4.1）──
        # 论文："The score of a move for the declarer is the highest score of
        # all vectors in the Pareto front of the move."
        # 即 best_score = max success_rate over vectors in front。
        # 平局时按出现顺序取第一个（论文未规定 tie-break）。
        move_scores: List[dict] = []
        best_move = None
        best_score = -1.0

        for move, front in move_fronts:
            score = front.best_score()
            best_vec = front.best_vector()
            move_scores.append({
                "card": str(move),
                "best_score": round(score, 3),
                "front_size": len(front),
                "best_vector": repr(best_vec) if best_vec else "∅",
                "success_count": best_vec.count_success() if best_vec else 0,
                "total_useful": sum(1 for m in best_vec.useful_mask if m) if best_vec else 0,
            })
            if score > best_score:
                best_score = score
                best_move = move

        move_scores.sort(key=lambda s: s["best_score"], reverse=True)

        elapsed = time.time() - self._start_time
        _dds_total_s = getattr(self, "_dds_time_total", 0.0)
        _dds_count = getattr(self, "_dds_count_total", 0)
        _dds_pct = (_dds_total_s / elapsed * 100) if elapsed > 0 else 0
        _dds_per = (_dds_total_s * 1000 / _dds_count) if _dds_count > 0 else 0
        print(f"[αμ] 搜索完成: {self._nodes_searched} nodes, {self._dds_calls} DDS calls, {elapsed:.1f}s")
        print(f"[αμ] DDS耗时分析: {_dds_total_s:.2f}s/{_dds_count}次 = {_dds_per:.2f}ms/次, 占总耗时{_dds_pct:.0f}%")
        top_str = ", ".join(
            f"{s['card']}({s['best_score']:.0%})"
            for s in move_scores[:5]
        )
        reasoning = (
            f"αμ搜索: {n_worlds} worlds, M={self.M}, "
            f"{self._nodes_searched} nodes, {self._dds_calls} DDS calls, "
            f"{elapsed:.1f}s. Top: {top_str}"
        )

        err_diag = " | ".join(
            f"{k}={v}" for k, v in self._err_stats.items() if v > 0
        )
        if err_diag:
            print(f"[αμ] 优化统计: {err_diag}")
        err_samples_str = "; ".join(
            f"[{k}] {v[:200]}" for k, v in self._err_samples.items()
        )

        # 将DDS诊断日志追加到debug文件
        if self._debug_dds_log:
            with open(_debug_path, "a", encoding="utf-8") as _f:
                _f.write(f"\n[DDS DIAGNOSTIC] {len(self._debug_dds_log)} samples:\n")
                for line in self._debug_dds_log:
                    _f.write(f"  {line}\n")

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
        M_remaining: int,
        declarer: str,
        dummy: str,
        trump: str,
        tricks_needed: int,
        our_side: frozenset,
        alpha: ParetoFront = None,
        deep_alpha: ParetoFront = None,
    ) -> ParetoFront:
        """应用 move 后递归进入子节点。M_remaining 只在 Max 节点减 1。

        论文 §4.3 alpha：直接父 Max 节点的累积 front。
        deep_alpha（2021 Alg1）：所有祖先 Max 节点的 front 并集。
        """
        self._nodes_searched += 1
        n = len(worlds)
        if self._time_up():
            return ParetoFront([OutcomeVector([0] * n)])

        from bridge.mcts.bit_hands import (clone_world_bits, card_to_bit,
                                            apply_play_to_state_bits, get_playable_from_bits)

        next_states: List[Tuple[Dict[str, int], dict]] = []
        trick_state = get_current_trick_state(state)

        for w_idx, world in enumerate(worlds):
            if world is None:
                next_states.append((None, {"impossible": True}))
                continue
            # bitmap world: clone 仅复制 4 个 int（vs 旧 List[Card] 复制 ~32 个对象）
            hands = clone_world_bits(world)
            hand_bits = hands.get(current_player, 0)
            card_bit = card_to_bit(move)
            if not (hand_bits & card_bit):
                next_states.append((None, {"impossible": True}))
                continue
            new_hands, new_current, new_trick, decl_tricks, def_tricks, trick_done = \
                apply_play_to_state_bits(
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
            next_states, n, state, M_remaining,
            declarer, dummy, trump, tricks_needed,
            our_side,
            alpha=alpha,
            deep_alpha=deep_alpha,
        )

    def _evaluate_state(
        self,
        next_states: List[Tuple[Dict[str, List[Card]], dict]],
        n: int,
        state: PlayState,
        M_remaining: int,
        declarer: str,
        dummy: str,
        trump: str,
        tricks_needed: int,
        our_side: frozenset,
        alpha: ParetoFront = None,
        deep_alpha: ParetoFront = None,
    ) -> ParetoFront:
        """根据下一玩家是 Max 还是 Min，分发到对应节点评估。

        M_remaining = 剩余可递归的 Max 层数。
        alpha = 直接父 Max 节点累积 front（论文 §4.3 Early Cut）。
        deep_alpha = 所有祖先 Max 节点 front 并集（2021 Alg1 Deep Alpha Cut）。

        论文 Alg2 L2 stop function：M=0 时不分 Min/Max，一律触发叶子 DDS 评估。
        论文 §4.3 "Skipping Min nodes"：Min 节点搜一层 DDS 等价于直接 DDS，
        因 DDS 内部已为每个 world 选择最优 Min 策略。

        论文 §4.1 stop function：合同已定（无论后续怎么打都赢/输）时立即终止搜索。
        论文 §4.3 Transposition Table：缓存已搜索状态的 (front, best_move, M_used)。
        论文 §4.3 Early Cuts：Min 节点 front 被 alpha 支配时剪枝。
        2021 Alg1 Deep Alpha Cut：Min 节点 front 被任何祖先 Max front 支配时剪枝。
        """
        if alpha is None:
            alpha = ParetoFront()

        tt_key = self._make_tt_key(next_states, n)
        # 论文：TT 用于提示（best_move 排序 + early cut bound），不设 M 深度守卫
        # 浅搜索的 front 是乐观上界，深搜索可直接复用
        if tt_key is not None and tt_key in self._tt:
            stored_front, _, stored_M = self._tt[tt_key]
            if stored_M >= M_remaining:
                self._err_stats["tt_hit"] += 1
                return stored_front

        # ── stop function：合同已定 ──
        # 取任一合法 world 的 decl/def tricks（所有 worlds 共享同一计数）
        for _, ns_info in next_states:
            if not ns_info.get("impossible"):
                d_t = ns_info.get("decl_tricks", 0)
                f_t = ns_info.get("def_tricks", 0)
                if self._is_our_side_declarer:
                    if d_t >= tricks_needed:
                        result = ParetoFront([OutcomeVector([1] * n)])
                        if tt_key is not None:
                            self._tt[tt_key] = (result, None, M_remaining)
                        return result
                    if f_t >= 14 - tricks_needed:
                        result = ParetoFront([OutcomeVector([0] * n)])
                        if tt_key is not None:
                            self._tt[tt_key] = (result, None, M_remaining)
                        return result
                else:
                    if f_t >= 14 - tricks_needed:
                        result = ParetoFront([OutcomeVector([1] * n)])
                        if tt_key is not None:
                            self._tt[tt_key] = (result, None, M_remaining)
                        return result
                    if d_t >= tricks_needed:
                        result = ParetoFront([OutcomeVector([0] * n)])
                        if tt_key is not None:
                            self._tt[tt_key] = (result, None, M_remaining)
                        return result
                break

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
            # 只剩一个合法 world，策略融合无意义，直接 DDS 评估
            self._err_stats["world_cut_1"] += 1
            result = self._evaluate_leaf(
                next_states, n, declarer, dummy, trump, tricks_needed)
            if tt_key is not None:
                self._tt[tt_key] = (result, None, M_remaining)
            return result

        # ── 论文 §4.3 "Skipping Min nodes" + Alg2 L2 stop function ──
        # M=0 → leaf DDS。对 Min 节点搜一层 DDS 和直接对当前状态做 DDS
        # 结果相同，因 DDS 内部已选择每个 world 下的最优 Min 策略。
        # 因此 M=0 时不区分 Min/Max，一律直接 DDS 评估。
        # 这是之前 DDS 调用爆炸的根因：Min 节点在 M=0 时仍在递归搜索
        # 所有 Min 候选牌，而非直接触发叶子评估。
        if M_remaining <= 0:
            result = self._evaluate_leaf(
                next_states, n, declarer, dummy, trump, tricks_needed)
            if tt_key is not None:
                self._tt[tt_key] = (result, None, M_remaining)
            return result

        is_next_max = next_player in our_side

        if is_next_max:
            candidate_moves = self._collect_candidate_moves(next_states, next_player)
            if not candidate_moves:
                result = self._evaluate_leaf(
                    next_states, n, declarer, dummy, trump, tricks_needed)
                if tt_key is not None:
                    self._tt[tt_key] = (result, None, M_remaining)
                return result
            # 论文 §4.3 Move Ordering: TT best_move 排最前（Alg2 L33）
            if tt_key is not None and tt_key in self._tt:
                _, tt_best_move, _ = self._tt[tt_key]
                if tt_best_move is not None and tt_best_move in candidate_moves:
                    candidate_moves.remove(tt_best_move)
                    candidate_moves.insert(0, tt_best_move)
            updated_worlds, next_world_decl, next_world_def = \
                self._extract_updated_worlds(next_states)
            # 论文 §4.3 Bound Reuse: search_alpha 初始 = 传入的 alpha (M=k-1 的最佳 front)
            # combined_front 仅累积本节点子 move 的结果（用于返回），不含传入 alpha
            # search_alpha = 传入 alpha ∪ 已搜子 move 的 front（用于 Early Cut 剪枝）
            combined_front = ParetoFront()
            search_alpha = alpha  # 起始 = 父节点传入的 bound
            best_child_move = None
            best_child_score = -1.0
            for child_move in candidate_moves:
                if self._time_up():
                    break
                child_state = self._build_child_state(state, next_states, child_move)
                if child_state is None:
                    continue
                # Max 递归：M_remaining - 1，alpha 传下去（论文 §4.3 early cut）
                child_front = self._search_recursive(
                    child_state, updated_worlds,
                    next_world_decl, next_world_def,
                    child_move, next_player, M_remaining - 1,
                    declarer, dummy, trump, tricks_needed, our_side,
                    alpha=search_alpha,
                    deep_alpha=deep_alpha.union(search_alpha),  # 2021 Alg1
                )
                combined_front = combined_front.union(child_front)
                search_alpha = search_alpha.union(child_front)  # 收紧剪枝界限
                # 跟踪 best_move（论文 §4.3：最高成功率的 move）
                child_score = child_front.best_score()
                if child_score > best_child_score:
                    best_child_score = child_score
                    best_child_move = child_move
                # 2021 论文 §Cut on Win: 子节点全赢 → 立即截断
                if any(v.is_all_won() for v in child_front.vectors):
                    self._err_stats["cut_on_win"] += 1
                    break
            result = combined_front if combined_front.vectors else self._evaluate_leaf(
                next_states, n, declarer, dummy, trump, tricks_needed)
            if tt_key is not None:
                self._tt[tt_key] = (result, best_child_move, M_remaining)
            return result
        else:
            # Min 节点：总是递归，M_remaining 不变
            # 论文 §4.3 Early Cuts: Alg2 L9-11 `if t.front ≤ α then return mini`
            # 2021 Alg1 Deep Alpha Cut: 也检查祖先 Max 节点的 front
            if tt_key is not None and tt_key in self._tt:
                t_front, _, stored_M = self._tt[tt_key]
                # 检查 alpha（直接父）和 deep_alpha（所有祖先）
                dominated = self._front_dominated_by(t_front, alpha)
                if not dominated and deep_alpha is not None:
                    dominated = self._front_dominated_by(t_front, deep_alpha)
                if dominated:
                    self._err_stats["early_cut"] += 1
                    if dominated and deep_alpha is not None and deep_alpha.vectors:
                        self._err_stats["deep_alpha_cut"] = self._err_stats.get("deep_alpha_cut", 0) + 1
                    return t_front
                else:
                    self._err_stats["early_cut_miss"] = self._err_stats.get("early_cut_miss", 0) + 1
            result, best_min_move = self._min_node_evaluate(
                next_states, n, next_player,
                state, M_remaining,
                declarer, dummy, trump, tricks_needed,
                our_side,
                alpha=alpha,
                deep_alpha=deep_alpha,  # Min 节点透传祖先 front
                tt_key=tt_key,
            )
            if tt_key is not None:
                self._tt[tt_key] = (result, best_min_move, M_remaining)
            return result

    def _make_tt_key(
        self,
        next_states: List[Tuple[Dict[str, List[Card]], dict]],
        n: int,
        M_remaining: int = None,
    ) -> Optional[Tuple]:
        """生成 transposition table 的 key。

        论文 §4.3: key = (next_player, trick_cards, decl_tricks, def_tricks,
                         useful_worlds_fingerprint)

        M_remaining 不放入 key！这样 M=k 迭代能查到 M=k-1 的结果。
        不同 M 下同一状态的 front 不同（M 越大越精确），TT 存最新（最大 M）的结果。
        Early Cut 用前次迭代的 front 作上界，依赖这个跨 M 共享的 key。
        """
        try:
            next_player = None
            trick_cards = None
            decl_t = None
            def_t = None
            world_fingerprints = []
            for w_idx, (hands, ns_info) in enumerate(next_states):
                if ns_info.get("impossible") or hands is None:
                    continue
                if next_player is None:
                    next_player = ns_info.get("new_current")
                    trick_state = ns_info.get("new_trick")
                    if trick_state is not None:
                        # trick_state 是 dict {"cards": [...], "leader": ..., "trump": ...}
                        if isinstance(trick_state, dict):
                            cards_list = trick_state.get("cards", [])
                        else:
                            cards_list = trick_state
                        trick_cards = tuple(sorted(
                            (p, c.suit, c.rank) for p, c in cards_list
                        ))
                    decl_t = ns_info.get("decl_tricks")
                    def_t = ns_info.get("def_tricks")
                # bitmap 手牌：直接用 int 值哈希（比 Card 元组快 ~10x）
                w_fp = hash(tuple(sorted((pos, bits) for pos, bits in hands.items())))
                world_fingerprints.append(w_fp)
            if next_player is None:
                return None
            world_fingerprints.sort()
            return (next_player, trick_cards, decl_t, def_t,
                    tuple(world_fingerprints))
        except Exception:
            return None

    def _front_dominated_by(self, front: ParetoFront, alpha: ParetoFront) -> bool:
        """论文 §4.3: t.front ≤ α 即 front 被 alpha 支配或相等。
        定义：front 中每个 vector 都被 alpha 中某个 vector 支配或相等。
        """
        if not alpha.vectors:
            return False  # 空 alpha 不剪枝
        if not front.vectors:
            return True  # 空 front 被任何 alpha 支配
        for v in front.vectors:
            dominated = False
            for av in alpha.vectors:
                # av 支配或等于 v
                if self._vec_geq(av, v):
                    dominated = True
                    break
            if not dominated:
                return False
        return True

    def _vec_geq(self, v1: OutcomeVector, v2: OutcomeVector) -> bool:
        """v1 >= v2 (per-index, considering useful_mask)。

        v1 的 useful_mask 必须是 v2 的超集（v1 对 v2 关心的所有 world 都有信息）。
        否则信息不足，无法判定支配。
        """
        if len(v1.values) != len(v2.values):
            return False
        for i in range(len(v1.values)):
            if not v2.useful_mask[i]:
                continue  # v2 不关心此 world，跳过
            if not v1.useful_mask[i]:
                return False  # v2 关心但 v1 无信息 → 无法判定 v1 >= v2
            if v1[i] < v2[i]:
                return False
        return True

    @staticmethod
    def _update_useful_worlds(front: ParetoFront, useful_mask: List[bool]) -> List[bool]:
        """2021 论文 §Maintaining Useful Worlds: 标记 useless 世界。

        若 Pareto front 中某 world 在所有向量中都是 0 → useless
        （Min 节点能保证该 world 一定输，子树中永远是 0）。
        返回更新后的 useful_mask。
        """
        n = len(useful_mask)
        for i in range(n):
            if not useful_mask[i]:
                continue
            # 检查是否有任何向量在这个 world 上是 1
            has_one = any(
                i < len(v.values) and v.useful_mask[i] and v.values[i] == 1
                for v in front.vectors
            )
            if not has_one:
                useful_mask[i] = False
        return useful_mask

    def _min_node_evaluate(
        self,
        next_states: List[Tuple[Dict[str, List[Card]], dict]],
        n: int,
        min_player: str,
        state: PlayState,
        M_remaining: int,
        declarer: str,
        dummy: str,
        trump: str,
        tricks_needed: int,
        our_side: frozenset,
        alpha: ParetoFront = None,
        deep_alpha: ParetoFront = None,
        tt_key: Tuple = None,
    ) -> Tuple[ParetoFront, Optional[Card]]:
        """Min 节点递归（论文 §4.2 + Algorithm 2 lines 7-25）。
        deep_alpha = 祖先 Max 节点 front 并集（2021 Alg1）。

        论文规则（§4.2 关键）：
        - Min 完美信息，每个 world 独立选 move。
        - 每个 Min move 后进入 Max 子树，子树返回 ParetoFront（多个非支配 vectors）。
        - Max 可以从子 front 中任选 vector，且不同 moves 选的 vector 可以不同（组合）。
        - **Min 节点返回的也是 ParetoFront**：
          计算所有 child fronts 的笛卡尔积，每个组合 per-index min（考虑 world cuts），
          支配消除后插入 Min 的 front。

        Algorithm 2 line 22 `mini ← min(mini, f)` 是增量式 front 之间的 min 操作：
        min(A, B) = { min(a, b) for a in A for b in B }，再做支配消除。

        World Cuts：Min 出牌时剔除该 move 不合法的 worlds。

        Returns: (ParetoFront, best_move)
          best_move = 最小化 Max 成功率的 move（Min 视角的"最佳"），用于 TT move ordering。
        """

        # 2021 论文 §Maintaining Useful Worlds: 跟踪 useful_worlds
        useful_worlds = [not ns_info.get("impossible") for _, ns_info in next_states]
        useful_count = sum(useful_worlds)
        if useful_count == 0:
            self._err_stats["world_cut_0"] += 1
            return ParetoFront([OutcomeVector([0] * n, [False] * n)]), None

        # TT 中已存的前端可标记额外 useless worlds（已知必输的 world）
        if tt_key is not None and tt_key in self._tt:
            stored_front, _, _ = self._tt[tt_key]
            useful_worlds = self._update_useful_worlds(stored_front, useful_worlds)

        # 1. 论文 Alg2 L13-16: allMoves = 仅 useful worlds 的合法 move 并集
        from bridge.mcts.bit_hands import get_playable_from_bits, card_to_bit
        all_moves_set = set()
        for w_idx, (hands, ns_info) in enumerate(next_states):
            if not useful_worlds[w_idx] or hands is None:
                continue
            hand_bits = hands.get(min_player, 0)
            if hand_bits == 0:
                continue
            trick_state = ns_info["new_trick"]
            candidate_moves = get_playable_from_bits(hand_bits, trick_state)
            all_moves_set.update(candidate_moves)

        if not all_moves_set:
            return ParetoFront([OutcomeVector([0] * n, [False] * n)]), None

        # 论文 §4.3 Move Ordering: TT best_move 排最前（Alg2 L17）
        all_moves = list(all_moves_set)
        if tt_key is not None and tt_key in self._tt:
            _, tt_best_move, _ = self._tt[tt_key]
            if tt_best_move is not None and tt_best_move in all_moves_set:
                all_moves.remove(tt_best_move)
                all_moves.insert(0, tt_best_move)

        # 2. 对每个 move 做递归，收集 child_front + legal_mask
        move_data = []  # [(child_front, move_legal_mask, min_move)]
        best_min_move = None
        best_min_score = 2.0  # Min 视角：最小化 Max 成功率
        for min_move in all_moves:
            if self._time_up():
                break

            # World Cuts：剔除 min_move 不合法的 worlds（bitmap 手牌）
            from bridge.mcts.bit_hands import apply_play_to_state_bits
            updated_next_states: List[Tuple[Dict[str, int], dict]] = []
            move_legal_mask = [False] * n
            move_bit = card_to_bit(min_move)
            for w_idx, (w_hands, w_ns_info) in enumerate(next_states):
                if w_ns_info.get("impossible") or w_hands is None:
                    updated_next_states.append((None, {"impossible": True}))
                    continue
                w_hand_bits = w_hands.get(min_player, 0)
                if not (w_hand_bits & move_bit):
                    updated_next_states.append((None, {"impossible": True}))
                    continue
                trick_state = w_ns_info["new_trick"]
                new_hands, new_current, new_trick, decl_t, def_t, td = \
                    apply_play_to_state_bits(
                        w_hands, min_player, min_move, trick_state,
                        w_ns_info["decl_tricks"], w_ns_info["def_tricks"],
                        trump, declarer, dummy,
                    )
                updated_next_states.append((new_hands, {
                    "new_current": new_current,
                    "new_trick": new_trick,
                    "decl_tricks": decl_t,
                    "def_tricks": def_t,
                    "trick_done": td,
                    "impossible": False,
                }))
                move_legal_mask[w_idx] = True

            updated_useful = sum(1 for _, ns in updated_next_states
                                 if not ns.get("impossible"))
            if updated_useful == 0:
                continue

            # 递归子节点（M_remaining 不变），alpha 传下去供深层 early cut
            child_state = self._build_min_child_state(state, updated_next_states)
            child_front = self._evaluate_state(
                updated_next_states, n, child_state,
                M_remaining,
                declarer, dummy, trump, tricks_needed,
                our_side,
                alpha=alpha,
                deep_alpha=deep_alpha,  # Min 子节点透传
            )
            move_data.append((child_front, move_legal_mask, min_move))
            # 跟踪 Min 视角的最佳 move（最低 Max 成功率）
            child_score = child_front.best_score()
            if child_score < best_min_score:
                best_min_score = child_score
                best_min_move = min_move

        if not move_data:
            return ParetoFront([OutcomeVector([0] * n, [False] * n)]), None

        # 3. 论文 §4.2：笛卡尔积 + per-index min + 支配消除
        # 增量式 min 操作：min_front 初始 = [全 1 vector]（min 的恒等元素）
        # 每个 move 后：min_front = min(min_front, child_front)
        #   = { per-index min(v1, v2) for v1 in min_front for v2 in child_front }
        #   再做支配消除。
        # per-index min 考虑 world cuts：
        #   - 若 move 在 world i 合法：v_new[i] = min(v1[i], v2[i])
        #   - 若 move 在 world i 不合法：v_new[i] = v1[i]（沿用，Min 不能选此 move）
        # useful_mask 更新：m_new[i] = v1.useful_mask[i] or v2.useful_mask[i]
        #   初始 useful_mask = all False，每个 move 合法后对应 world 变 True
        #   这样不合法 move 的虚假初始值 1 不会参与支配消除
        # 2019 论文补全：mid-computation early cut（每条 move 后检查 alpha/deep_alpha）
        min_front = ParetoFront([OutcomeVector([1] * n, [False] * n, [13] * n)])
        for child_front, legal_mask, _min_move in move_data:
            if self._time_up():
                break
            new_front = ParetoFront()
            for v1 in min_front.vectors:
                for v2 in child_front.vectors:
                    v_new = list(v1.values)
                    t_new = list(v1.tricks_list)
                    m_new = list(v1.useful_mask)
                    for w_idx in range(n):
                        if not legal_mask[w_idx]:
                            continue
                        if w_idx >= len(v2):
                            continue
                        if not v2.useful_mask[w_idx]:
                            continue
                        v_new[w_idx] = min(v1[w_idx], v2[w_idx])
                        if w_idx < len(v2.tricks_list):
                            t_new[w_idx] = min(v1.tricks_list[w_idx],
                                               v2.tricks_list[w_idx])
                        m_new[w_idx] = True
                    new_front.add(OutcomeVector(v_new, m_new, t_new, _copy=False))
            min_front = new_front
            # 2019 论文补全：mid-computation early cut
            # 每处理完一个子 move，检查当前 min_front 是否已被 alpha 支配
            if alpha is not None and self._front_dominated_by(min_front, alpha):
                self._err_stats["early_cut_mid"] = self._err_stats.get("early_cut_mid", 0) + 1
                break
            if deep_alpha is not None and self._front_dominated_by(min_front, deep_alpha):
                self._err_stats["early_cut_mid_deep"] = self._err_stats.get("early_cut_mid_deep", 0) + 1
                break

        return min_front, best_min_move

    def _build_min_child_state(
        self,
        state: PlayState,
        next_states: List[Tuple[Dict[str, int], dict]],
    ) -> PlayState:
        import copy
        from bridge.mcts.bit_hands import hand_bits_to_cards
        for hands, ns_info in next_states:
            if ns_info.get("impossible") or hands is None:
                continue
            child_state = copy.copy(state)
            child_state.hands = {pos: hand_bits_to_cards(bits)
                                for pos, bits in hands.items()}
            child_state.current_trick = Trick_from_dict(ns_info["new_trick"])
            child_state.current_player = ns_info["new_current"]
            child_state.declarer_tricks = ns_info["decl_tricks"]
            child_state.defender_tricks = ns_info["def_tricks"]
            return child_state
        return copy.copy(state)

    def _evaluate_leaf(
        self,
        next_states: List[Tuple[Dict[str, List[Card]], dict]],
        n: int,
        declarer: str,
        dummy: str,
        trump: str,
        tricks_needed: int,
    ) -> ParetoFront:
        """叶子节点：批处理 DDS 评估所有 worlds，转为布尔成功/失败。
        同时保存每个 world 的实际赢墩数用于 tie-break。"""
        _t_leaf_start = time.time()
        useful_count = sum(1 for _, ns_info in next_states
                          if not ns_info.get("impossible"))
        if useful_count == 0:
            self._err_stats["world_cut_0"] += 1
            return ParetoFront([OutcomeVector([0] * n, [False] * n)])

        result_vector = [0] * n
        useful_mask = [True] * n
        tricks_list = [0] * n  # 每个 world 下我方总赢墩数

        # ── DirectDDS Bitmap：bit 手牌直接构造 DDS 结构，零 Card 迭代 ──
        from bridge.mcts.direct_dds import solve_all_boards_bits, dds_result_to_decl_tricks

        _t_build_start = time.time()
        batch_items = []  # [(w_idx, hands_bits, trump, first, trick_cards, trick_count, ns_info)]
        for w_idx, (hands, ns_info) in enumerate(next_states):
            if ns_info.get("impossible") or hands is None:
                useful_mask[w_idx] = False
                continue
            trick_info = ns_info.get("new_trick", {})
            trick_cards = trick_info.get("cards", [])
            first = trick_info.get("leader") or ns_info.get("new_current", "北")
            trick_count = len(trick_cards)
            batch_items.append((w_idx, hands, trump, first, trick_cards, trick_count, ns_info))
        _build_ms = (time.time() - _t_build_start) * 1000

        if not batch_items:
            return ParetoFront([OutcomeVector(result_vector, useful_mask, tricks_list)])

        # 2021 论文 §Leaf Parallelization: 并行求解 DDS 批次
        _t_solve_start = time.time()
        _BATCH = 200
        raw_results = [None] * len(batch_items)

        # 分块
        chunks = []
        chunk_indices = []
        for bi in range(0, len(batch_items), _BATCH):
            chunk = batch_items[bi:bi + _BATCH]
            chunk_data = [(hands_bits, trump, first, cards)
                         for _, hands_bits, trump, first, cards, _, _ in chunk]
            chunks.append(chunk_data)
            chunk_indices.append(list(range(bi, min(bi + _BATCH, len(batch_items)))))

        if not chunks:
            return ParetoFront([OutcomeVector(result_vector, useful_mask, tricks_list)])

        # 单块或已经超时 → 串行
        if len(chunks) == 1 or self._time_up():
            for ci, chunk_data in enumerate(chunks):
                if self._time_up():
                    break
                try:
                    cr = solve_all_boards_bits(chunk_data)
                    for j, idx in enumerate(chunk_indices[ci]):
                        if j < len(cr):
                            raw_results[idx] = cr[j]
                except Exception:
                    pass
        else:
            # 多块并行求解
            from concurrent.futures import ThreadPoolExecutor, as_completed
            _max_workers = min(4, len(chunks))
            with ThreadPoolExecutor(max_workers=_max_workers) as executor:
                futures = {}
                for ci, chunk_data in enumerate(chunks):
                    if self._time_up():
                        break
                    f = executor.submit(solve_all_boards_bits, chunk_data)
                    futures[f] = ci
                for f in as_completed(futures):
                    ci = futures[f]
                    try:
                        cr = f.result()
                        for j, idx in enumerate(chunk_indices[ci]):
                            if cr is not None and j < len(cr):
                                raw_results[idx] = cr[j]
                    except Exception:
                        pass

        self._dds_calls += sum(1 for r in raw_results if r is not None and len(r) > 0)
        _solve_ms = (time.time() - _t_solve_start) * 1000

        for i, (w_idx, hands, trump, first, trick_cards, trick_count, ns_info) in enumerate(batch_items):
            solved = raw_results[i] if i < len(raw_results) else None
            if solved is None:
                useful_mask[w_idx] = False
                continue
            decl_tricks = dds_result_to_decl_tricks(
                solved, ns_info["decl_tricks"], ns_info["def_tricks"],
                declarer, dummy, first, trick_count,
            )
            if decl_tricks is None:
                useful_mask[w_idx] = False
                continue
            our_tricks = decl_tricks if self._is_our_side_declarer else (13 - decl_tricks)
            result_vector[w_idx] = 1 if our_tricks >= self._goal else 0
            tricks_list[w_idx] = our_tricks

        _total_ms = (time.time() - _t_leaf_start) * 1000
        if _total_ms >= 50 and len(batch_items) >= 5:
            print(f"[αμ LEAF] worlds={len(batch_items)}, build={_build_ms:.1f}ms, solve={_solve_ms:.1f}ms, total={_total_ms:.1f}ms")

        return ParetoFront([OutcomeVector(result_vector, useful_mask, tricks_list)])

    # ── DDS 辅助 ──

    # ── 辅助方法 ──

    def _collect_candidate_moves(
        self,
        next_states: List[Tuple[Dict[str, int], dict]],
        next_player: str,
    ) -> List[Card]:
        from bridge.mcts.bit_hands import get_playable_from_bits
        move_set: Set[Card] = set()
        for hands, ns_info in next_states:
            if ns_info.get("impossible") or hands is None:
                continue
            trick_state = ns_info["new_trick"]
            hand_bits = hands.get(next_player, 0) if isinstance(hands, dict) else 0
            moves = get_playable_from_bits(hand_bits, trick_state)
            for m in moves:
                move_set.add(m)
        return list(move_set)

    def _build_child_state(
        self,
        state: PlayState,
        next_states: List[Tuple[Dict[str, int], dict]],
        child_move: Card,
    ) -> Optional[PlayState]:
        import copy
        from bridge.mcts.bit_hands import card_to_bit, hand_bits_to_cards
        move_bit = card_to_bit(child_move)
        for hands, ns_info in next_states:
            if ns_info.get("impossible") or hands is None:
                continue
            world_next = ns_info["new_current"]
            hand_bits = hands.get(world_next, 0)
            if not (hand_bits & move_bit):
                continue
            child_state = copy.copy(state)
            # 边界转换：bitmap → Card 列表（PlayState 使用 Card 对象）
            child_state.hands = {pos: hand_bits_to_cards(bits)
                                 for pos, bits in hands.items()}
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
        """平局 tie-break，bonus 足够小不覆盖真实差异。
        小牌 bonus 更大（保留大牌结构/进张），与 DD 引擎 _compare_candidates 一致。"""
        rank_values = {
            '2': 0.009, '3': 0.008, '4': 0.007, '5': 0.006, '6': 0.005,
            '7': 0.004, '8': 0.003, '9': 0.002, 'T': 0.001,
            'J': 0.0009, 'Q': 0.0008, 'K': 0.0007, 'A': 0.0006,
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
