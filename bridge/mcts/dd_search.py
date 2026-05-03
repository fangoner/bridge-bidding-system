"""纯蒙特卡洛 + 双明手评估搜索。

采样后把当前墩牌加回手牌使四家张数相等，
deal.play(from_hand=True) 写入当前墩，
solve_board 求解并取期望值选最优出牌。
"""

import os
import time
from typing import Dict, List

from config import BASE_DIR
from bridge.play_types import Card, PlayState, PlayPhase
from bridge.mcts.state_utils import (
    cards_to_hand_str, get_current_trick_state, POSITION_TO_PLAYER, PLAYER_TO_POSITION, SUIT_TO_DENOM,
)
from bridge.mcts.sampler import DealSampler

_DEBUG_LOG = os.path.join(BASE_DIR, "dd_debug.log")

RANK_ORDER = {"A": 14, "K": 13, "Q": 12, "J": 11, "T": 10,
              "9": 9, "8": 8, "7": 7, "6": 6, "5": 5, "4": 4, "3": 3, "2": 2}

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
                 min_samples: int = 15, time_limit: float = 5.0):
        if not ENDPLAY_AVAILABLE:
            raise RuntimeError("endplay library not available (pip install endplay)")
        self.sampler = sampler or DealSampler()
        self.num_samples = num_samples
        self.min_samples = min_samples
        self.time_limit = time_limit

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

        known_positions = {perspective}
        if dummy and state.phase != PlayPhase.LEAD:
            known_positions.add(dummy)
        elif dummy and perspective in (declarer, dummy):
            known_positions.add(dummy)
        known_cards = sum(len(state.hands.get(p, [])) for p in known_positions)
        played_cards = sum(len(t.cards) for t in state.tricks) + len(state.current_trick.cards)
        remaining_cards = 52 - known_cards - played_cards

        ratio = max(0, remaining_cards / 52)
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

        while samples_done < adaptive_samples:
            if time.time() - start_time > self.time_limit:
                break

            sampled = self.sampler.sample(state, perspective)
            samples_done += 1

            try:
                # 1. 从所有采样手牌中清除已出牌（无论谁出的），再按正确位置加回
                for _, card in all_played:
                    for p in sampled:
                        sampled[p] = [c for c in sampled[p] if not (c.suit == card.suit and c.rank == card.rank)]
                for pos, card in all_played:
                    sampled[pos].append(card)

                # 2. PBN → Deal
                pbn = _hands_to_pbn(sampled)
                deal = Deal(pbn)
                deal.trump = SUIT_TO_DENOM.get(trump, Denom.nt)

                # 3. 按顺序重放所有已出牌
                if all_played:
                    deal.first = POSITION_TO_PLAYER.get(all_played[0][0], Player.north)
                    for _pos, card in all_played:
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
                    "remaining_cards": remaining_cards,
                    "candidates": child_stats,
                },
            },
        }
