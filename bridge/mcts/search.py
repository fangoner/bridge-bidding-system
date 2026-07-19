import math
import random
import time
import os
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

from bridge.play_types import Card, PlayState, PlayPhase, POSITION_ORDER
from bridge.mcts.state_utils import (
    clone_hands, get_playable_from_hands, apply_play_to_state,
    get_current_trick_state, trick_winner,
)
from bridge.mcts.sampler import DealSampler
from bridge.mcts.rollout import HeuristicRollout
from config import MCTS_MIN_ITERATIONS, BASE_DIR

_DEBUG_LOG = os.path.join(BASE_DIR, "dd_debug.log")


@dataclass
class MctsNode:
    """MCTS搜索树节点"""
    position: str  # 当前出牌者
    trick_cards: Tuple[Tuple[str, Card], ...]  # 当前墩已出的牌
    trick_leader: Optional[str]  # 本墩领出者
    trump: str  # 将牌花色
    declarer: str  # 庄家
    dummy: str  # 明手
    declarer_tricks: int = 0  # 已完成墩中庄家方赢墩数
    defender_tricks: int = 0  # 已完成墩中防守方赢墩数
    visits: int = 0
    value: float = 0.0
    parent: Optional["MctsNode"] = None
    parent_card: Optional[Card] = None
    children: Dict[str, "MctsNode"] = field(default_factory=dict)


class MctsSearch:
    """单明手MCTS搜索（Determinization + UCT）。

    每次迭代：
    1. 采样未知手牌分布
    2. 在确定化手牌上做Selection→Expansion→Simulation→Backpropagation
    """

    def __init__(
        self,
        sampler: DealSampler = None,
        rollout: HeuristicRollout = None,
        iterations: int = 5000,
        time_limit: float = 10.0,
        exploration: float = 1.414,
    ):
        self.sampler = sampler or DealSampler()
        self.rollout = rollout or HeuristicRollout()
        self.iterations = iterations
        self.time_limit = time_limit
        self.exploration = exploration

    def search(self, state: PlayState) -> dict:
        """执行MCTS搜索，返回最优出牌和统计信息。

        Returns:
            {"card": Card, "reasoning": str, "full_output": dict}
        """
        perspective = state.current_player
        # 明手不做决策：如果当前轮到明手出牌，搜索视角改为庄家（庄家替明手决策）
        declarer = state.contract.declarer
        dummy = state.dummy
        actual_turn = state.current_player
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

        # 计算剩余未知牌张数（用于自适应迭代）
        known_positions = {perspective}
        if dummy and state.phase != PlayPhase.LEAD:
            known_positions.add(dummy)
        elif dummy and perspective in (declarer, dummy):
            known_positions.add(dummy)
        known_cards = sum(len(state.hands.get(p, [])) for p in known_positions)
        played_cards = sum(len(t.cards) for t in state.tricks) + len(state.current_trick.cards)
        remaining_cards = 52 - known_cards - played_cards

        ratio = max(0, remaining_cards / 52)
        adaptive_iterations = int(MCTS_MIN_ITERATIONS + (self.iterations - MCTS_MIN_ITERATIONS) * ratio)
        adaptive_iterations = max(MCTS_MIN_ITERATIONS, min(self.iterations, adaptive_iterations))

        trick_state = get_current_trick_state(state)

        root = MctsNode(
            position=actual_turn,
            trick_cards=tuple(trick_state["cards"]),
            trick_leader=trick_state["leader"],
            trump=trump,
            declarer=declarer,
            dummy=dummy,
            declarer_tricks=state.declarer_tricks,
            defender_tricks=state.defender_tricks,
        )

        start_time = time.time()
        iteration = 0

        while iteration < adaptive_iterations:
            if time.time() - start_time > self.time_limit:
                break

            # 1. Determinization：采样未知手牌
            sampled_hands = self.sampler.sample(state, perspective)

            # 2. Selection + Expansion
            leaf, hands_at_leaf = self._select_and_expand(
                root, sampled_hands, trump, declarer, dummy)

            # 3. Simulation
            final_declarer_tricks = self.rollout.rollout(
                hands_at_leaf, trump,
                leaf.position,
                {"cards": list(leaf.trick_cards),
                 "leader": leaf.trick_leader, "trump": trump},
                leaf.declarer_tricks, leaf.defender_tricks,
                declarer, dummy,
            )
            total_declarer = final_declarer_tricks

            # 4. Backpropagation
            node = leaf
            while node is not None:
                node.visits += 1
                node.value += total_declarer
                node = node.parent

            iteration += 1

        elapsed = time.time() - start_time
        iters_per_sec = iteration / elapsed if elapsed > 0 else 0
        mcts_summary = (f"[MCTS] {iteration} iters in {elapsed:.1f}s ({iters_per_sec:.0f} it/s) "
                        f"adaptive={adaptive_iterations} remaining={remaining_cards}")
        print(mcts_summary)
        with open(_DEBUG_LOG, "a", encoding="utf-8") as f:
            f.write(f"\n{mcts_summary}\n")

        # 选择最优出牌
        is_root_declarer_side = perspective in (declarer, dummy)
        best_card_str = None
        best_score = -float("inf")
        child_stats = []

        for card_str, child in root.children.items():
            avg_value = child.value / child.visits if child.visits > 0 else 0
            child_stats.append({
                "card": card_str,
                "visits": child.visits,
                "avg_tricks": round(avg_value, 2),
            })
            # 双方均使用 avg_value（exploitation），与 UCB 探索项解耦
            # 庄家方：avg_value 越大越好（赢墩多）
            # 防守方：avg_value 越小越好（庄家赢墩少 = 防守赢墩多）
            if is_root_declarer_side:
                score = avg_value
            else:
                score = -avg_value
            if score > best_score:
                best_score = score
                best_card_str = card_str

        # 排序也改为按 avg_value（与选牌标准一致），庄家方降序、防守方升序
        if is_root_declarer_side:
            child_stats.sort(key=lambda s: s["avg_tricks"], reverse=True)
        else:
            child_stats.sort(key=lambda s: s["avg_tricks"])

        selected_card = None
        if best_card_str:
            for c in playable:
                if str(c) == best_card_str:
                    selected_card = c
                    break
        if selected_card is None:
            selected_card = playable[0]

        top_plays_str = ", ".join(
            f"{s['card']}({s['visits']}v/{s['avg_tricks']}t)"
            for s in child_stats[:5]
        )
        reasoning = (
            f"MCTS: {iteration} iterations in {elapsed:.1f}s "
            f"({iters_per_sec:.0f} it/s). "
            f"Top plays: {top_plays_str}"
        )

        print(reasoning)
        # Write MCTS result to debug log
        with open(_DEBUG_LOG, "a", encoding="utf-8") as f:
            f.write(f"  perspective={perspective} is_decl={is_root_declarer_side} "
                    f"decl_done={state.declarer_tricks} def_done={state.defender_tricks} "
                    f"remaining={remaining_cards}\n")
            f.write(f"  candidates: {child_stats[:5]}\n")

        return {
            "card": selected_card,
            "reasoning": reasoning,
            "full_output": {
                "推荐出牌": str(selected_card),
                "核心逻辑": reasoning,
                "候选对比": str(child_stats),
                "局面评估": (
                    f"MCTS searched {iteration} iterations in {elapsed:.1f}s "
                    f"({iters_per_sec:.0f} it/s, adaptive cap={adaptive_iterations}, "
                    f"remaining={remaining_cards})"
                ),
                "mcts_stats": {
                    "iterations": iteration,
                    "time_sec": round(elapsed, 2),
                    "iters_per_sec": round(iters_per_sec, 1),
                    "adaptive_cap": adaptive_iterations,
                    "remaining_cards": remaining_cards,
                    "candidates": child_stats[:5],
                },
            },
        }

    def _select_and_expand(
        self,
        root: MctsNode,
        sampled_hands: Dict[str, List[Card]],
        trump: str,
        declarer: str,
        dummy: str,
    ) -> Tuple[MctsNode, Dict[str, List[Card]]]:
        """Selection + Expansion：从根节点沿UCT走到可扩展节点并扩展一个子节点。

        Returns:
            (leaf_node, hands_at_leaf)
        """
        node = root
        hands = clone_hands(sampled_hands)

        while True:
            legal = get_playable_from_hands(hands, node.position,
                                            {"cards": list(node.trick_cards),
                                             "leader": node.trick_leader})

            if not legal:
                # 不应发生；作为叶子返回
                return node, hands

            # 检查是否有未扩展的合法出牌
            untried = [c for c in legal if str(c) not in node.children]

            if untried:
                # Expansion：随机选一个未尝试的出牌扩展
                card = random.choice(untried)
                child = self._create_child(node, card, trump, declarer, dummy)
                node.children[str(card)] = child

                # Apply the play to hands
                hands, _, _, _, _, _ = apply_play_to_state(
                    hands, node.position, card,
                    {"cards": list(node.trick_cards),
                     "leader": node.trick_leader, "trump": trump},
                    node.declarer_tricks, node.defender_tricks,
                    trump, declarer, dummy,
                )
                return child, hands

            # 所有合法出牌已扩展 → UCT选择
            best_card = self._uct_select(node, legal, declarer, dummy)
            node = node.children[str(best_card)]

            # Apply play to hands (child node already tracks post-play state)
            prev = node.parent if node.parent else node
            hands, *_ = apply_play_to_state(
                hands, prev.position, best_card,
                {"cards": list(prev.trick_cards),
                 "leader": prev.trick_leader, "trump": trump},
                prev.declarer_tricks, prev.defender_tricks,
                trump, declarer, dummy,
            )

    def _create_child(
        self,
        parent: MctsNode,
        card: Card,
        trump: str,
        declarer: str,
        dummy: str,
    ) -> MctsNode:
        """从父节点出card创建子节点"""
        new_trick_cards = list(parent.trick_cards)
        new_trick_cards.append((parent.position, card))

        new_dt, new_dft = parent.declarer_tricks, parent.defender_tricks

        if len(new_trick_cards) == 4:
            # 墩完成，判断赢家
            winner = trick_winner(new_trick_cards, trump)
            if winner in (declarer, dummy):
                new_dt += 1
            else:
                new_dft += 1
            child_position = winner
            child_trick_cards = ()
            child_leader = None
        else:
            idx = POSITION_ORDER.index(parent.position)
            child_position = POSITION_ORDER[(idx + 1) % 4]
            child_trick_cards = tuple(new_trick_cards)
            child_leader = parent.trick_leader if parent.trick_leader else parent.position

        return MctsNode(
            position=child_position,
            trick_cards=child_trick_cards,
            trick_leader=child_leader,
            trump=trump,
            declarer=declarer,
            dummy=dummy,
            declarer_tricks=new_dt,
            defender_tricks=new_dft,
            parent=parent,
            parent_card=card,
        )

    def _uct_select(self, node: MctsNode, legal: List[Card],
                    declarer: str, dummy: str) -> Card:
        """UCT公式选择最优子节点。

        庄家方最大化庄家赢墩，防守方最小化庄家赢墩（即最大化防守赢墩）。
        """
        best_card = None
        best_uct = -float("inf")
        parent_visits = node.visits
        is_declarer_side = node.position in (declarer, dummy)

        for card in legal:
            child = node.children.get(str(card))
            if child is None:
                return card
            if child.visits == 0:
                return card
            avg_declarer = child.value / child.visits
            if is_declarer_side:
                exploitation = avg_declarer
            else:
                exploitation = 13 - avg_declarer  # 防守方最大化防守赢墩
            exploration = self.exploration * math.sqrt(
                math.log(parent_visits + 1) / child.visits
            )
            uct = exploitation + exploration
            if uct > best_uct:
                best_uct = uct
                best_card = card

        return best_card if best_card else legal[0]

