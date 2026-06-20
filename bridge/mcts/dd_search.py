"""纯蒙特卡洛 + 双明手评估搜索。

采样后把当前墩牌加回手牌使四家张数相等，
deal.play(from_hand=True) 写入当前墩，
solve_board 求解并取期望值选最优出牌。
"""

import itertools
import math
import os
import time
from typing import Dict, List, Optional

from config import BASE_DIR
from bridge.play_types import Card, PlayState, PlayPhase, POSITION_ORDER, PARTNERS
from bridge.mcts.state_utils import (
    cards_to_hand_str, get_current_trick_state, POSITION_TO_PLAYER, PLAYER_TO_POSITION, SUIT_TO_DENOM,
)
from bridge.mcts.sampler import DealSampler, ALL_CARDS
from bridge.mcts.constraints import validate_sample

_DEBUG_LOG = os.path.join(BASE_DIR, "dd_debug.log")

RANK_ORDER = {"A": 14, "K": 13, "Q": 12, "J": 11, "T": 10,
              "9": 9, "8": 8, "7": 7, "6": 6, "5": 5, "4": 4, "3": 3, "2": 2}


def _has_duplicates(hands: Dict[str, List[Card]]) -> bool:
    """检测采样手牌中是否存在同一张牌出现在多个位置的情况。"""
    seen = set()
    for pos, cards in hands.items():
        for c in cards:
            key = (c.suit, c.rank)
            if key in seen:
                return True
            seen.add(key)
    return False

try:
    from endplay import Deal
    from endplay.dds import solve_board
    from endplay.types import Card as EpCard, Denom, Player, Rank
    ENDPLAY_AVAILABLE = True
except ImportError:
    ENDPLAY_AVAILABLE = False

_SUIT_MAP = {}
_RANK_MAP = {}
_DENOM_TO_SUIT = {}
_RANK_TO_CHAR = {}

if ENDPLAY_AVAILABLE:
    _SUIT_MAP = {"♠": Denom.spades, "♥": Denom.hearts, "♦": Denom.diamonds, "♣": Denom.clubs}
    _RANK_MAP = {r: getattr(Rank, "R" + r) for r in ["A", "K", "Q", "J", "T", "9", "8", "7", "6", "5", "4", "3", "2"]}
    _DENOM_TO_SUIT = {Denom.spades: "♠", Denom.hearts: "♥", Denom.diamonds: "♦", Denom.clubs: "♣"}
    _RANK_TO_CHAR = {getattr(Rank, "R" + c): c for c in ["A", "K", "Q", "J", "T", "9", "8", "7", "6", "5", "4", "3", "2"]}


def _to_ep(card: Card) -> EpCard:
    return EpCard(suit=_SUIT_MAP[card.suit], rank=_RANK_MAP[card.rank])


def _hands_to_pbn(hands: Dict[str, List[Card]]) -> str:
    parts = []
    for pos in ["北", "东", "南", "西"]:
        cards = hands.get(pos, [])
        hand_str = cards_to_hand_str(cards)
        suits = []
        for s in hand_str.split():
            if s and s != "-":
                s = s[1:] if s[0] in "♠♥♦♣" else s
            suits.append(s)
        while len(suits) < 4:
            suits.append("")
        suits = ["" if s == "-" else s for s in suits]
        parts.append(".".join(suits))
    return f"N:{' '.join(parts)}"


class DDSearch:

    def __init__(self, sampler: DealSampler = None, num_samples: int = 100,
                 min_samples: int = 15, time_limit: float = 5.0,
                 endgame_card_threshold: int = 10, max_enumerations: int = 5000):
        if not ENDPLAY_AVAILABLE:
            raise RuntimeError("endplay library not available (pip install endplay)")
        self.sampler = sampler or DealSampler()
        self.num_samples = num_samples
        self.min_samples = min_samples
        self.time_limit = time_limit
        self.endgame_card_threshold = endgame_card_threshold
        self.max_enumerations = max_enumerations

    def search(self, state: PlayState) -> dict:
        perspective = state.current_player
        playable = state.get_playable_cards(perspective)

        if len(playable) == 1:
            return {
                "card": playable[0],
                "reasoning": "唯一选择",
                "full_output": {"推荐出牌": str(playable[0])},
            }

        declarer = state.contract.declarer
        dummy = state.dummy
        trump = state.contract.suit
        is_declarer_side = perspective in (declarer, dummy)

        # 残局判定：用剩余墩数（=每手牌数），与模式无关
        remaining_tricks = 13 - (state.declarer_tricks + state.defender_tricks)

        # 残局：尝试精确枚举所有分布
        if remaining_tricks <= self.endgame_card_threshold:
            enum_result = self._enumerate_endgame(state, perspective, playable,
                                                   declarer, dummy, trump, is_declarer_side)
            if enum_result is not None:
                return enum_result

        ratio = max(0, remaining_tricks / 13)
        adaptive_samples = int(self.min_samples + (self.num_samples - self.min_samples) * ratio)
        adaptive_samples = max(self.min_samples, min(self.num_samples, adaptive_samples))

        card_scores = {str(c): [] for c in playable}
        start_time = time.time()
        samples_done = 0

        # 当前墩信息（补回手牌 + 写入 Deal 当前墩）
        trick_state = get_current_trick_state(state)
        trick_cards = trick_state["cards"]  # [(pos, Card), ...]
        trick_leader = trick_state.get("leader")

        # 收集所有已出牌（已完成墩 + 当前墩），按出牌顺序
        all_played = []
        for trick in state.tricks:
            all_played.extend(trick.cards)
        all_played.extend(trick_cards)

        # 信念跟踪器：在采样循环前生成加权粒子集
        # sampler.sample() 会自动从粒子集按权重抽样
        belief_stats = None
        if self.sampler.belief_tracker is not None:
            self.sampler.belief_tracker.prepare(state, perspective)
            belief_stats = self.sampler.belief_tracker.stats()

        while samples_done < adaptive_samples:
            if time.time() - start_time > self.time_limit:
                break

            sampled = self.sampler.sample(state, perspective)
            samples_done += 1

            try:
                # 1. 安全网：只从打出牌的位置移除已出牌（不跨位置移除，避免重复牌污染其他手牌）
                for pos, card in all_played:
                    if pos in sampled:
                        sampled[pos] = [c for c in sampled[pos] if not (c.suit == card.suit and c.rank == card.rank)]

                # 1.5 验证：检测采样手牌中是否有重复牌，有则跳过
                if _has_duplicates(sampled):
                    if samples_done <= 3:
                        with open(_DEBUG_LOG, "a", encoding="utf-8") as f:
                            f.write(f"\n--- sample {samples_done} SKIPPED (duplicates in sampled hands) ---\n")
                            for p in ["北", "东", "南", "西"]:
                                cs = sampled.get(p, [])
                                f.write(f"  sampled[{p}]({len(cs)}): {sorted(str(c) for c in cs)}\n")
                    continue

                # 2. 只加回当前墩的牌（已完成墩的牌不保留），使每个位置均为 13-已完成墩出牌 张
                for pos, card in trick_cards:
                    sampled[pos].append(card)

                # 3. PBN → Deal（含当前墩出牌在手，不含已完成墩出牌）
                pbn = _hands_to_pbn(sampled)
                deal = Deal(pbn)
                deal.trump = SUIT_TO_DENOM.get(trump, Denom.nt)

                # 4. 只重放当前墩（避免重放已完成墩时 curplayer 墩间轮转不一致）
                if trick_cards:
                    deal.first = POSITION_TO_PLAYER.get(trick_leader, Player.north)
                    for _pos, card in trick_cards:
                        deal.play(_to_ep(card), from_hand=True)
                else:
                    deal.first = POSITION_TO_PLAYER.get(perspective, Player.north)

                result = solve_board(deal)
                score_map = {}
                for ep_card, side_score in result:
                    key = (_DENOM_TO_SUIT.get(ep_card.suit), _RANK_TO_CHAR.get(ep_card.rank))
                    score_map[key] = side_score

                total_played = state.declarer_tricks + state.defender_tricks
                remaining_tricks = 13 - total_played

                # solve_board 返回 deal.curplayer（当前出牌人）所在方的赢墩
                curplayer_pos = PLAYER_TO_POSITION.get(deal.curplayer, perspective)
                curplayer_is_declarer = curplayer_pos in (declarer, dummy)

                for card in playable:
                    key = (card.suit, card.rank)
                    target_tricks = score_map.get(key, 0)
                    if curplayer_is_declarer:
                        decl_side_tricks = target_tricks
                    else:
                        decl_side_tricks = remaining_tricks - target_tricks
                    total = state.declarer_tricks + decl_side_tricks
                    card_scores[str(card)].append(total)

                # DEBUG
                if samples_done <= 3:
                    scores = list(score_map.values())
                    hand_lens = [len(deal.north), len(deal.east), len(deal.south), len(deal.west)]
                    with open(_DEBUG_LOG, "a", encoding="utf-8") as f:
                        f.write(f"\n--- sample {samples_done} OK ---\n")
                        f.write(f"perspective={perspective} is_decl={is_declarer_side} "
                                f"curplayer={deal.curplayer} curplayer_is_decl={curplayer_is_declarer} "
                                f"decl_done={state.declarer_tricks} def_done={state.defender_tricks} "
                                f"remaining={remaining_tricks} "
                                f"trump={deal.trump} first={deal.first}\n")
                        f.write(f"deal hand_lens(N/E/S/W): {hand_lens}  playable={len(playable)}\n")
                        f.write(f"PBN: {pbn}\n")
                        f.write(f"solve_board: {len(scores)} results "
                                f"min={min(scores)} max={max(scores)} mean={sum(scores)/len(scores):.1f}"
                                f" ({curplayer_pos} side tricks)\n")
                        for card in playable[:5]:
                            k = (card.suit, card.rank)
                            target = score_map.get(k, -999)
                            dt = target if curplayer_is_declarer else remaining_tricks - target if target != -999 else -999
                            t = card_scores[str(card)][-1]
                            f.write(f"  {card}: target={target} decl_side={dt} -> total={t}\n")

            except Exception as e:
                with open(_DEBUG_LOG, "a", encoding="utf-8") as f:
                    f.write(f"\n--- sample {samples_done} ERROR: {e} ---\n")
                    # 真实 state.hands
                    for p in ["北", "东", "南", "西"]:
                        sh = state.hands.get(p, [])
                        f.write(f"  state.hands[{p}]({len(sh)}): {sorted(str(c) for c in sh)}\n")
                    f.write(f"  --- sampled ---\n")
                    for p in ["北", "东", "南", "西"]:
                        cs = sampled.get(p, [])
                        f.write(f"  sampled[{p}]({len(cs)}): {sorted(str(c) for c in cs)}\n")
                    f.write(f"  PBN: {pbn}\n")
                    f.write(f"  all_played: {[(pos, str(c)) for pos, c in all_played]}\n")
                    f.write(f"  declarer={declarer} dummy={dummy} perspective={perspective} phase={state.phase}\n")
                    import traceback
                    f.write(traceback.format_exc())
                print(f"[DD] sample {samples_done} ERROR: {e}")

        # DEBUG success
        if samples_done == 1 and card_scores:
            first_key = list(card_scores.keys())[0]
            print(f"[DD] sample 1 OK: card_scores example {first_key} = {card_scores[first_key][:3]}...")
        elif samples_done > 0 and not any(card_scores.values()):
            print(f"[DD] WARNING: {samples_done} samples but all scores empty!")

        # 信念跟踪器统计
        if belief_stats and belief_stats.get("prepared"):
            active = belief_stats["active_particles"]
            total = belief_stats["num_particles"]
            filtered = belief_stats["void_filtered"]
            print(f"[DD] 信念跟踪: {active}/{total} 粒子有效, {filtered} 被 void 过滤")

        elapsed = time.time() - start_time

        best_card = None
        best_score = -float("inf")
        child_stats = []

        for card in playable:
            scores = card_scores[str(card)]
            avg = sum(scores) / len(scores) if scores else 0.0
            mn = min(scores) if scores else 0
            mx = max(scores) if scores else 0
            child_stats.append({
                "card": str(card),
                "samples": len(scores),
                "avg_tricks": round(avg, 2),
                "min_tricks": mn,
                "max_tricks": mx,
            })
            # Rank偏置打破平局：庄家方偏好大牌赢墩，防守方偏好小牌保留实力
            # Ace=0.28, 3=0.06 → 最大差异0.22墩，足以破平但不颠覆明显差距
            rank_bonus = RANK_ORDER.get(card.rank, 0) / 50.0
            score = (avg + rank_bonus) if is_declarer_side else -(avg + rank_bonus)
            if score > best_score:
                best_score = score
                best_card = card

        child_stats.sort(key=lambda s: s["avg_tricks"], reverse=is_declarer_side)

        top_plays_str = ", ".join(
            f"{s['card']}({s['avg_tricks']}[{s['min_tricks']}-{s['max_tricks']}])"
            for s in child_stats[:5]
        )
        reasoning = (
            f"DDMC: {samples_done} samples in {elapsed:.1f}s. "
            f"Top plays: {top_plays_str}"
        )

        return {
            "card": best_card,
            "reasoning": reasoning,
            "full_output": {
                "推荐出牌": str(best_card),
                "核心逻辑": reasoning,
                "候选对比": str(child_stats),
                "局面评估": (
                    f"DDMC searched {samples_done} samples in {elapsed:.1f}s"
                ),
                "mcts_stats": {
                    "iterations": samples_done,
                    "time_sec": round(elapsed, 2),
                    "iters_per_sec": round(samples_done / elapsed, 1) if elapsed > 0 else 0,
                    "adaptive_cap": self.num_samples,
                    "remaining_cards": remaining_tricks * 4,
                    "candidates": child_stats,
                },
            },
        }

    def _enumerate_endgame(self, state: PlayState, perspective: str,
                           playable: List[Card], declarer: str, dummy: str,
                           trump: str, is_declarer_side: bool) -> Optional[dict]:
        """残局精确枚举：枚举所有可能的未知牌分布，对每个做双明手求解。

        返回同 search() 的 dict 格式，若枚举不可行则返回 None（回退采样）。
        """
        start_time = time.time()

        # ── 1. 识别已知/未知位置和未知牌池 ──
        known_positions = {perspective}
        if dummy and state.phase != PlayPhase.LEAD:
            known_positions.add(dummy)
        if dummy and perspective in (declarer, dummy):
            known_positions.add(declarer)

        unknown_positions = [p for p in POSITION_ORDER if p not in known_positions]

        # 收集已知牌
        known_card_set = set()
        for pos in known_positions:
            known_card_set.update(state.hands.get(pos, []))
        for trick in state.tricks:
            for _, card in trick.cards:
                known_card_set.add(card)
        for _, card in state.current_trick.cards:
            known_card_set.add(card)

        # 未知牌池（排序确保确定性）
        pool = sorted(
            [c for c in ALL_CARDS if c not in known_card_set],
            key=lambda c: (c.suit, ["A","K","Q","J","T","9","8","7","6","5","4","3","2"].index(c.rank))
        )

        # 每个未知位置还需出多少张牌
        remaining_counts = {}
        for pos in unknown_positions:
            remaining_counts[pos] = 13 - self.sampler._count_played(state, pos)

        total_needed = sum(remaining_counts.values())
        if total_needed != len(pool):
            # 一致性检查失败
            return None

        # ── 2. 估算枚举总数 ──
        counts = [remaining_counts[p] for p in unknown_positions]
        est = 1
        rem = len(pool)
        for c in counts[:-1]:  # 最后一个位置拿剩余全部
            est *= math.comb(rem, c)
            rem -= c
        if est > self.max_enumerations:
            print(f"[DD] Enumeration count {est} > max {self.max_enumerations}, "
                  f"falling back to sampling")
            return None

        # ── 3. 预计算共享状态 ──
        trick_state = get_current_trick_state(state)
        trick_cards = trick_state["cards"]
        trick_leader = trick_state.get("leader")

        all_played = []
        for trick in state.tricks:
            all_played.extend(trick.cards)
        all_played.extend(trick_cards)

        total_played_tricks = state.declarer_tricks + state.defender_tricks
        remaining_tricks = 13 - total_played_tricks

        card_scores = {str(c): [] for c in playable}
        constraints = self.sampler.constraints

        n_pool = len(pool)
        indices = list(range(n_pool))
        n1 = remaining_counts[unknown_positions[0]]
        enum_count = 0
        valid_count = 0

        # ── 4. 枚举所有分布 ──
        for combo1_idx in itertools.combinations(indices, n1):
            if time.time() - start_time > self.time_limit:
                break

            cards1 = [pool[i] for i in combo1_idx]
            combo1_set = set(combo1_idx)
            remaining_idx = [i for i in indices if i not in combo1_set]

            # 构建分布迭代器
            if len(unknown_positions) == 2:
                cards2 = [pool[i] for i in remaining_idx]
                distributions = [{unknown_positions[0]: cards1,
                                  unknown_positions[1]: cards2}]
            elif len(unknown_positions) == 3:
                n2 = remaining_counts[unknown_positions[1]]
                distributions = []
                for combo2_idx in itertools.combinations(remaining_idx, n2):
                    combo2_set = set(combo2_idx)
                    cards2 = [pool[i] for i in combo2_idx]
                    cards3 = [pool[i] for i in remaining_idx if i not in combo2_set]
                    distributions.append({unknown_positions[0]: cards1,
                                          unknown_positions[1]: cards2,
                                          unknown_positions[2]: cards3})
            else:
                # 1或4个未知位置（极端情况），回退
                return None

            for dist in distributions:
                enum_count += 1
                if time.time() - start_time > self.time_limit:
                    break

                # 构建完整四家手牌
                hands = {}
                for pos in known_positions:
                    hands[pos] = list(state.hands.get(pos, []))
                for pos, cards in dist.items():
                    hands[pos] = list(cards)

                # 约束验证
                if constraints:
                    if not validate_sample(hands, constraints):
                        continue
                valid_count += 1

                try:
                    # 安全网清除已出牌（只从打出位置移除）
                    for pos, card in all_played:
                        if pos in hands:
                            hands[pos] = [c for c in hands[pos]
                                          if not (c.suit == card.suit and c.rank == card.rank)]
                    # 验证无重复牌
                    if _has_duplicates(hands):
                        continue
                    # 加回当前墩牌
                    for pos, card in trick_cards:
                        hands[pos].append(card)

                    # PBN → Deal → solve_board
                    pbn = _hands_to_pbn(hands)
                    deal = Deal(pbn)
                    deal.trump = SUIT_TO_DENOM.get(trump, Denom.nt)

                    if trick_cards:
                        deal.first = POSITION_TO_PLAYER.get(trick_leader, Player.north)
                        for _pos, card in trick_cards:
                            deal.play(_to_ep(card), from_hand=True)
                    else:
                        deal.first = POSITION_TO_PLAYER.get(perspective, Player.north)

                    result = solve_board(deal)
                    score_map = {}
                    for ep_card, side_score in result:
                        key = (_DENOM_TO_SUIT.get(ep_card.suit),
                               _RANK_TO_CHAR.get(ep_card.rank))
                        score_map[key] = side_score

                    curplayer_pos = PLAYER_TO_POSITION.get(deal.curplayer, perspective)
                    curplayer_is_declarer = curplayer_pos in (declarer, dummy)

                    for card in playable:
                        key = (card.suit, card.rank)
                        target_tricks = score_map.get(key, 0)
                        if curplayer_is_declarer:
                            decl_side_tricks = target_tricks
                        else:
                            decl_side_tricks = remaining_tricks - target_tricks
                        total = state.declarer_tricks + decl_side_tricks
                        card_scores[str(card)].append(total)

                except Exception:
                    continue  # 跳过无效分布

            if time.time() - start_time > self.time_limit:
                break

        # ── 5. 汇总结果 ──
        elapsed = time.time() - start_time

        if not any(card_scores.values()):
            return None  # 无有效分布，回退采样

        best_card = None
        best_score = -float("inf")
        child_stats = []

        for card in playable:
            scores = card_scores[str(card)]
            avg = sum(scores) / len(scores) if scores else 0.0
            mn = min(scores) if scores else 0
            mx = max(scores) if scores else 0
            child_stats.append({
                "card": str(card),
                "samples": len(scores),
                "avg_tricks": round(avg, 2),
                "min_tricks": mn,
                "max_tricks": mx,
            })
            rank_bonus = RANK_ORDER.get(card.rank, 0) / 50.0
            score = (avg + rank_bonus) if is_declarer_side else -(avg + rank_bonus)
            if score > best_score:
                best_score = score
                best_card = card

        child_stats.sort(key=lambda s: s["avg_tricks"], reverse=is_declarer_side)

        top_plays_str = ", ".join(
            f"{s['card']}({s['avg_tricks']}[{s['min_tricks']}-{s['max_tricks']}])"
            for s in child_stats[:5]
        )
        reasoning = (
            f"DD-endgame: {enum_count} enumerations ({valid_count} valid) "
            f"in {elapsed:.1f}s. Top plays: {top_plays_str}"
        )

        return {
            "card": best_card,
            "reasoning": reasoning,
            "full_output": {
                "推荐出牌": str(best_card),
                "核心逻辑": reasoning,
                "候选对比": str(child_stats),
                "局面评估": (
                    f"DD-endgame enumerated {enum_count} distributions "
                    f"({valid_count} valid) in {elapsed:.1f}s"
                ),
                "mcts_stats": {
                    "iterations": enum_count,
                    "valid_distributions": valid_count,
                    "time_sec": round(elapsed, 2),
                    "remaining_cards": len(pool),
                    "candidates": child_stats,
                },
            },
        }

    def search_perfect(self, state: PlayState) -> dict:
        """全知双明手搜索：AI 知道四家手牌，一次 solve_board 得所有候选精确分。

        与 search() 不同，此方法不采样，直接使用 state.hands 中的全部手牌。
        每次出牌只需一次 solve_board 调用，极快且确定。
        """
        if not ENDPLAY_AVAILABLE:
            raise RuntimeError("endplay 库不可用，无法运行完美DD搜索")

        perspective = state.current_player
        playable = state.get_playable_cards(perspective)

        if len(playable) == 1:
            return {
                "card": playable[0],
                "reasoning": "唯一选择",
                "full_output": {"推荐出牌": str(playable[0])},
            }

        declarer = state.contract.declarer
        dummy = state.dummy
        trump = state.contract.suit
        is_declarer_side = perspective in (declarer, dummy)

        trick_state = get_current_trick_state(state)
        trick_cards = trick_state["cards"]
        trick_leader = trick_state.get("leader")

        total_played = state.declarer_tricks + state.defender_tricks
        remaining_tricks = 13 - total_played

        # 从 state.hands 直接取全四家手牌（完整信息）
        hands = {}
        for pos in POSITION_ORDER:
            hands[pos] = list(state.hands.get(pos, []))

        # 移除当前墩已打出的牌（避免 PBN 中重复，之后通过 deal.play 重放）
        for pos, card in trick_cards:
            hands[pos] = [c for c in hands[pos]
                          if not (c.suit == card.suit and c.rank == card.rank)]
        # 加回当前墩牌（PBN 构建用）
        for pos, card in trick_cards:
            hands[pos].append(card)

        pbn = _hands_to_pbn(hands)
        deal = Deal(pbn)
        deal.trump = SUIT_TO_DENOM.get(trump, Denom.nt)

        if trick_cards:
            deal.first = POSITION_TO_PLAYER.get(trick_leader, Player.north)
            for _pos, card in trick_cards:
                deal.play(_to_ep(card), from_hand=True)
        else:
            deal.first = POSITION_TO_PLAYER.get(perspective, Player.north)

        result = solve_board(deal)
        score_map = {}
        for ep_card, side_score in result:
            key = (_DENOM_TO_SUIT.get(ep_card.suit),
                   _RANK_TO_CHAR.get(ep_card.rank))
            score_map[key] = side_score

        curplayer_pos = PLAYER_TO_POSITION.get(deal.curplayer, perspective)
        curplayer_is_declarer = curplayer_pos in (declarer, dummy)

        best_card = None
        best_score = -float("inf")
        child_stats = []

        for card in playable:
            key = (card.suit, card.rank)
            target_tricks = score_map.get(key, 0)
            if curplayer_is_declarer:
                decl_side_tricks = target_tricks
            else:
                decl_side_tricks = remaining_tricks - target_tricks
            total = state.declarer_tricks + decl_side_tricks
            child_stats.append({
                "card": str(card),
                "samples": 1,
                "avg_tricks": total,
                "min_tricks": total,
                "max_tricks": total,
            })
            rank_bonus = RANK_ORDER.get(card.rank, 0) / 50.0
            score = (total + rank_bonus) if is_declarer_side else -(total + rank_bonus)
            if score > best_score:
                best_score = score
                best_card = card

        child_stats.sort(key=lambda s: s["avg_tricks"], reverse=is_declarer_side)

        top_plays_str = ", ".join(
            f"{s['card']}({s['avg_tricks']})" for s in child_stats[:5]
        )
        reasoning = (
            f"DD·完美: 全知双明手分析 {len(playable)} 个候选. "
            f"Top: {top_plays_str}"
        )

        return {
            "card": best_card,
            "reasoning": reasoning,
            "full_output": {
                "推荐出牌": str(best_card),
                "核心逻辑": reasoning,
                "候选对比": str(child_stats),
                "局面评估": "DD·完美：基于全知四家手牌的双明手精确分析",
                "mcts_stats": {
                    "iterations": 1,
                    "time_sec": 0,
                    "candidates": child_stats,
                },
            },
            "prompt": "[DD·完美] no prompt",
        }
