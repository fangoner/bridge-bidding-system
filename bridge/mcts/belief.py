"""信念状态跟踪器（粒子滤波）。

从双明手确定化走向单明手推理的关键组件。

核心思想：维护一组粒子（每个粒子=一种未知牌分布假设），
根据实际出牌的公开信息更新粒子权重：
- 硬证据：void（不跟花色→该花色为空），违反的粒子权重归零
- 软证据：防守信号（高牌=欢迎长套，低牌=不欢迎），调整权重

DD/MCTS 搜索时按权重抽样，替代均匀随机采样，
使采样分布更接近真实情况，缓解 strategy fusion 问题。
"""

import math
import os
import random
from typing import Dict, List, Set, Tuple, Optional

from bridge.play_types import Card, PlayState, PlayPhase, POSITION_ORDER
from bridge.mcts.constraints import compute_sample_violation_score
from config import (
    BELIEF_NUM_PARTICLES, BELIEF_SIGNAL_WEIGHT, BELIEF_SIGNAL_PENALTY,
    BELIEF_SIGNAL_MIN_RANK,
)


def collect_voids(state: PlayState) -> Dict[str, Set[str]]:
    """从已完成的墩和当前墩中提取 void 信息。

    当某位置不跟领出花色时，该位置在该花色上为 void。

    Returns:
        {position: set(suits)} — 每个位置已知 void 的花色集合
    """
    voids: Dict[str, Set[str]] = {}

    def _check_trick(cards: list):
        if not cards:
            return
        lead_suit = cards[0][1].suit
        for pos, card in cards:
            if card.suit != lead_suit:
                voids.setdefault(pos, set()).add(lead_suit)

    for trick in state.tricks:
        _check_trick(trick.cards)
    _check_trick(state.current_trick.cards)
    return voids


def collect_signal_evidence(state: PlayState) -> List[Tuple[str, str, bool]]:
    """从已完成的墩和当前墩中收集防守方信号证据。

    防守方跟领出花色时：
    - 高牌（≥BELIEF_SIGNAL_MIN_RANK）= 欢迎 → 暗示该花色较长
    - 低牌（<BELIEF_SIGNAL_MIN_RANK）= 不欢迎 → 暗示该花色较短

    Returns:
        [(position, suit, is_high)] — 信号证据列表
    """
    declarer = state.contract.declarer
    dummy = state.dummy
    evidence: List[Tuple[str, str, bool]] = []

    def _check_trick(cards: list):
        if not cards:
            return
        lead_suit = cards[0][1].suit
        for pos, card in cards:
            # 只关注防守方的跟牌信号
            if pos in (declarer, dummy):
                continue
            if card.suit != lead_suit:
                continue  # 不跟花色的牌不作为态度信号
            is_high = card.rank_value >= BELIEF_SIGNAL_MIN_RANK
            evidence.append((pos, lead_suit, is_high))

    for trick in state.tricks:
        _check_trick(trick.cards)
    _check_trick(state.current_trick.cards)
    return evidence


class BeliefTracker:
    """粒子滤波信念状态跟踪器。

    在 DD/MCTS 搜索前调用 prepare() 生成一组加权粒子，
    搜索中调用 draw() 按权重抽样。

    粒子权重基于两类证据：
    1. 硬证据（void）：违反 → 权重归零
    2. 软证据（信号）：一致 → 权重×SIGNAL_WEIGHT，不一致 → 权重×SIGNAL_PENALTY
    """

    def __init__(self, sampler, num_particles: int = BELIEF_NUM_PARTICLES):
        self.sampler = sampler
        self.num_particles = num_particles
        self.particles: List[Dict[str, List[Card]]] = []
        self.weights: List[float] = []
        self.constraints = None  # 叫牌约束
        self._last_state_id: Optional[int] = None  # 避免重复 prepare

    def set_constraints(self, constraints):
        """设置叫牌约束，用于粒子软加权"""
        self.constraints = constraints

    def prepare(self, state: PlayState, perspective: str) -> None:
        """在 DD/MCTS 搜索前生成并加权一组粒子。

        Args:
            state: 当前 PlayState
            perspective: 当前出牌者位置
        """
        # 缓存检查：如果已出牌数量、当前出牌玩家、搜索视角都没变，直接复用已有粒子
        played_count = sum(len(t.cards) for t in state.tricks) + len(state.current_trick.cards)
        state_key = (played_count, state.current_player, perspective)
        if state_key == self._last_state_id and self.particles:
            return

        # 收集证据
        known_voids = collect_voids(state)

        # 使用扩展信号模型（态度+张数+花色偏好），回退到基础态度信号
        try:
            from bridge.mcts.signals import collect_all_signals
            extended_signals = collect_all_signals(state)
            # 转换为兼容格式：(position, suit, is_high, signal_type)
            signal_evidence = [(s.position, s.suit, s.is_high, s.signal_type)
                               for s in extended_signals]
        except Exception:
            signal_evidence = [(p, s, h, "attitude")
                               for p, s, h in collect_signal_evidence(state)]

        # 生成粒子（sampler._sample_once 带约束，这里做二次验证 + 信号加权 + 约束软惩罚）
        # 注意：直接调用 _sample_once，跳过sample()中的硬验证重试（中局剩余牌不满足整手约束，重试无意义，权重会软惩罚）
        import time as _time
        from bridge.mcts.sampler import reset_dist_stats, dump_dist_stats
        reset_dist_stats()
        _prep_t0 = _time.time()
        self.particles = []
        self.weights = []
        _slow_samples = 0
        _slowest_sample_t = 0.0
        for _ in range(self.num_particles):
            _t_s0 = _time.time()
            sample = self.sampler._sample_once(state, perspective)
            _dt_sample = _time.time() - _t_s0
            if _dt_sample > _slowest_sample_t:
                _slowest_sample_t = _dt_sample
            if _dt_sample > 0.1:
                _slow_samples += 1
            self.particles.append(sample)
            w = self._particle_weight(sample, known_voids, signal_evidence, self.constraints)
            self.weights.append(w)
        _prep_total = _time.time() - _prep_t0
        _log_path = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), "dd_debug.log")
        with open(_log_path, "a", encoding="utf-8") as _f:
            _f.write(f"[PREP] particles={self.num_particles} total={_prep_total:.2f}s "
                     f"slowest_sample={_slowest_sample_t:.3f}s slow_samples={_slow_samples}\n")
        dump_dist_stats()

        # 归一化
        total = sum(self.weights)
        if total == 0:
            # 全部粒子违反 void（理论上不应发生，因 sampler 已强制 void）
            # 回退到均匀权重
            self.weights = [1.0] * len(self.particles)
        else:
            self.weights = [w / total for w in self.weights]

        self._last_state_id = state_key

    def draw(self) -> Dict[str, List[Card]]:
        """从粒子集中按权重抽取一个样本（MCTS用）。"""
        if not self.particles:
            raise RuntimeError("BeliefTracker.prepare() 未调用")
        idx = random.choices(range(len(self.particles)),
                             weights=self.weights, k=1)[0]
        # 返回深拷贝，避免调用方修改粒子
        return {pos: [Card(suit=c.suit, rank=c.rank) for c in hand]
                for pos, hand in self.particles[idx].items()}

    def get_all_particles(self) -> List[Tuple[Dict[str, List[Card]], float]]:
        """获取全部粒子及其权重（DD / αμ 全量使用，不抽取）。"""
        if not self.particles:
            return []
        result = []
        for i, particle in enumerate(self.particles):
            w = self.weights[i] if i < len(self.weights) else 1.0
            # 权重开根号平滑：避免某个粒子一家独大降低有效样本量
            w_smooth = w ** 0.5
            # 深拷贝
            world = {pos: [Card(suit=c.suit, rank=c.rank) for c in hand]
                     for pos, hand in particle.items()}
            result.append((world, w_smooth))
        return result

    def _particle_weight(self, particle: Dict[str, List[Card]],
                         known_voids: Dict[str, Set[str]],
                         signal_evidence: List[Tuple],
                         constraints=None) -> float:
        """计算单个粒子的权重。

        硬证据（void）违反 → 权重 0
        叫牌约束违反 → 根据违反程度指数衰减权重

        注意：防守信号不参与粒子权重计算（态度信号是意愿表达非张数信息，
        张数信号判断可靠性低）。信号仅通过 format_partner_signals_for_prompt
        注入LLM提示词，由LLM解读使用。
        """
        for pos, void_suits in known_voids.items():
            hand = particle.get(pos, [])
            for card in hand:
                if card.suit in void_suits:
                    return 0.0

        weight = 1.0

        if constraints:
            violation_score = compute_sample_violation_score(particle, constraints)
            if violation_score > 0:
                weight *= math.exp(-violation_score * 0.3)

        return weight

    def stats(self) -> dict:
        """返回粒子集统计信息（调试用）。"""
        if not self.particles:
            return {"prepared": False}
        active = sum(1 for w in self.weights if w > 0)
        return {
            "prepared": True,
            "num_particles": len(self.particles),
            "active_particles": active,
            "void_filtered": len(self.particles) - active,
            "max_weight": max(self.weights) if self.weights else 0,
            "min_weight": min(self.weights) if self.weights else 0,
        }
