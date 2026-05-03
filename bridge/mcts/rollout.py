import random
from typing import Dict, List, Optional

from bridge.play_types import Card, POSITION_ORDER, PARTNERS
from bridge.mcts.state_utils import clone_hands, get_playable_from_hands, apply_play_to_state, trick_winner


class HeuristicRollout:
    """启发式快速模拟打牌到底。

    规则：
    - 领出：从最长套选最大牌攻出
    - 跟牌（能赢）：用恰好能赢的最小牌
    - 跟牌（不能赢）：跟最小牌
    - 将吃：只在必须跟花色出不了时才将吃，用最小将牌
    """

    def rollout(
        self,
        hands: Dict[str, List[Card]],
        trump: str,
        current_player: str,
        current_trick: dict,
        declarer_tricks: int,
        defender_tricks: int,
        contract_declarer: str,
        dummy: str,
    ) -> int:
        """从当前位置模拟到底，返回庄家方最终赢墩数。不修改输入。"""
        h = clone_hands(hands)
        cur = current_player
        trick = {
            "cards": list(current_trick.get("cards", [])),
            "leader": current_trick.get("leader"),
            "trump": current_trick.get("trump", trump),
        }
        decl_tricks = declarer_tricks
        def_tricks = defender_tricks

        tricks_played = 0
        max_remaining = sum(len(cards) for cards in h.values()) // 4

        for _ in range(max_remaining + 1):
            # 如果手牌为空，结束
            if all(len(cs) == 0 for cs in h.values()):
                break

            playable = get_playable_from_hands(h, cur, trick)
            if not playable:
                break

            card = self._pick_card(playable, h, cur, trick, trump,
                                   contract_declarer, dummy)
            h, cur, trick, decl_tricks, def_tricks, complete = apply_play_to_state(
                h, cur, card, trick, decl_tricks, def_tricks,
                trump, contract_declarer, dummy)

            if complete:
                tricks_played += 1

        return decl_tricks  # 返回庄家方最终赢墩数

    def _pick_card(
        self,
        playable: List[Card],
        hands: Dict[str, List[Card]],
        position: str,
        current_trick: dict,
        trump: str,
        declarer: str,
        dummy: str,
    ) -> Card:
        if len(playable) == 1:
            return playable[0]

        trick_cards = current_trick.get("cards", [])

        if not trick_cards:
            # 领出：选最长套中最大的牌
            return self._lead_card(playable, hands[position])
        else:
            lead_suit = trick_cards[0][1].suit
            if playable[0].suit == lead_suit:
                # 跟领出花色
                return self._follow_suit(playable, trick_cards, trump)
            else:
                # 将吃或垫牌
                return self._discard_or_trump(playable, trick_cards, trump, position)

    def _lead_card(self, playable: List[Card], hand: List[Card]) -> Card:
        """领出：从最长套中选最大牌"""
        suit_counts = {}
        for c in hand:
            suit_counts[c.suit] = suit_counts.get(c.suit, 0) + 1
        longest = max(suit_counts, key=lambda s: suit_counts[s])
        longest_cards = [c for c in playable if c.suit == longest]
        if longest_cards:
            return max(longest_cards, key=lambda c: c.rank_value)
        return max(playable, key=lambda c: c.rank_value)

    def _follow_suit(self, playable: List[Card], trick_cards: list, trump: str) -> Card:
        """跟领出花色"""
        # 找到当前墩已出的最大同花色牌
        lead_suit = trick_cards[0][1].suit
        best = None
        for _, c in trick_cards:
            if c.suit == lead_suit:
                if best is None or c.rank_value > best:
                    best = c.rank_value
            elif trump and trump != "NT" and c.suit == trump:
                # 有将吃，不考虑同花色比较
                pass

        if best is None:
            return min(playable, key=lambda c: c.rank_value)

        # 找能赢的牌中最小的一张
        winners = [c for c in playable if c.rank_value > best]
        if winners:
            return min(winners, key=lambda c: c.rank_value)
        # 不能赢，跟最小
        return min(playable, key=lambda c: c.rank_value)

    def _discard_or_trump(self, playable: List[Card], trick_cards: list, trump: str,
                          position: str = "") -> Card:
        """不能跟领出花色时：将吃或垫牌。同伴赢则垫，敌方赢则将。"""
        if trump and trump != "NT":
            trump_cards = [c for c in playable if c.suit == trump]
            if trump_cards:
                # 判断当前谁在赢这墩
                partner = PARTNERS.get(position, "")
                current_winner = trick_winner(trick_cards, trump)
                if current_winner in (partner, position):
                    # 同伴或自己已经在赢，不浪费将牌，垫牌
                    return min(playable, key=lambda c: (c.suit_order, c.rank_value))
                # 检查是否已有将吃 需要超将吃
                best_trump_played = None
                for _, c in trick_cards:
                    if c.suit == trump:
                        if best_trump_played is None or c.rank_value > best_trump_played:
                            best_trump_played = c.rank_value
                if best_trump_played is not None:
                    over = [c for c in trump_cards if c.rank_value > best_trump_played]
                    if over:
                        return min(over, key=lambda c: c.rank_value)
                # 将吃——用最小将牌
                return min(trump_cards, key=lambda c: c.rank_value)
        # 垫牌：垫最小
        return min(playable, key=lambda c: (c.suit_order, c.rank_value))



class RandomizedRollout:
    """带随机性的启发式模拟，提升估值多样性。

    与 HeuristicRollout 的区别：
    - 领出：长套加权随机选花色 → 4th best（而非"最长套最大牌"）
    - 跟牌：第二家小 / 第三家大（而非一律最小）
    - 将吃/垫牌：同伴赢则垫，敌方赢则将；垫最短套（而非最小张）
    - 全局 20% 概率随机合法出牌，增加模拟多样性
    """

    def __init__(self, greedy_prob: float = 0.80):
        self.greedy_prob = greedy_prob

    def rollout(
        self,
        hands: Dict[str, List[Card]],
        trump: str,
        current_player: str,
        current_trick: dict,
        declarer_tricks: int,
        defender_tricks: int,
        contract_declarer: str,
        dummy: str,
    ) -> int:
        h = clone_hands(hands)
        cur = current_player
        trick = {
            "cards": list(current_trick.get("cards", [])),
            "leader": current_trick.get("leader"),
            "trump": current_trick.get("trump", trump),
        }
        decl_tricks = declarer_tricks
        def_tricks = defender_tricks

        max_remaining = sum(len(cards) for cards in h.values()) // 4

        for _ in range(max_remaining + 1):
            if all(len(cs) == 0 for cs in h.values()):
                break
            playable = get_playable_from_hands(h, cur, trick)
            if not playable:
                break

            card = self._pick_card(playable, h, cur, trick, trump,
                                   contract_declarer, dummy)
            h, cur, trick, decl_tricks, def_tricks, complete = apply_play_to_state(
                h, cur, card, trick, decl_tricks, def_tricks,
                trump, contract_declarer, dummy)
        return decl_tricks

    def _pick_card(
        self,
        playable: List[Card],
        hands: Dict[str, List[Card]],
        position: str,
        current_trick: dict,
        trump: str,
        declarer: str,
        dummy: str,
    ) -> Card:
        if len(playable) == 1:
            return playable[0]

        # 全局随机性：20% 概率随机出牌
        if random.random() > self.greedy_prob:
            return random.choice(playable)

        trick_cards = current_trick.get("cards", [])
        if not trick_cards:
            return self._lead_card(playable, hands[position])
        else:
            lead_suit = trick_cards[0][1].suit
            if playable[0].suit == lead_suit:
                return self._follow_suit(playable, trick_cards, trump, position)
            else:
                return self._discard_or_trump(
                    playable, trick_cards, trump, hands[position], position, declarer, dummy)

    def _lead_card(self, playable: List[Card], hand: List[Card]) -> Card:
        """领出：按花色张数加权选花色，长四首攻。"""
        suit_counts = {}
        for c in hand:
            suit_counts[c.suit] = suit_counts.get(c.suit, 0) + 1

        # 按张数²加权选花色（长套优先但不绝对）
        suits = list(suit_counts.keys())
        weights = [suit_counts[s] ** 2 for s in suits]
        chosen_suit = random.choices(suits, weights=weights, k=1)[0]

        suited = [c for c in playable if c.suit == chosen_suit]
        if not suited:
            return max(playable, key=lambda c: c.rank_value)

        sorted_cards = sorted(suited, key=lambda c: c.rank_value, reverse=True)
        if suit_counts.get(chosen_suit, 0) >= 4 and len(sorted_cards) >= 4:
            # 长四首攻
            return sorted_cards[3]
        # 否则出最小的大牌
        honors = [c for c in sorted_cards if c.rank_value >= 9]  # J=9 以上
        if honors:
            return honors[-1]
        return sorted_cards[-1]

    def _follow_suit(
        self, playable: List[Card], trick_cards: list, trump: str, position: str,
    ) -> Card:
        """跟领出花色：第二家小 / 第三家大。"""
        lead_suit = trick_cards[0][1].suit
        num_played = len(trick_cards)

        # 计算当前墩已出的最大同花色
        best = None
        for _, c in trick_cards:
            if c.suit == lead_suit:
                if best is None or c.rank_value > best:
                    best = c.rank_value
            elif trump and trump != "NT" and c.suit == trump:
                pass  # 有人将吃不参与比较

        winners = [c for c in playable if c.rank_value > best] if best is not None else playable

        if num_played == 1:
            # 第二家：能赢则最小赢张，不能则最小
            if winners:
                return min(winners, key=lambda c: c.rank_value)
            return min(playable, key=lambda c: c.rank_value)
        else:
            # 第三家或第四家：能赢则最小赢张，不能则最大（帮同伴提升）
            if winners:
                return min(winners, key=lambda c: c.rank_value)
            return max(playable, key=lambda c: c.rank_value)

    def _discard_or_trump(
        self, playable: List[Card], trick_cards: list, trump: str,
        hand: List[Card], position: str, declarer: str, dummy: str,
    ) -> Card:
        """将吃或垫牌：同伴赢则垫，敌方赢则将，垫最短套。"""
        if trump and trump != "NT":
            trump_cards = [c for c in playable if c.suit == trump]
            if trump_cards:
                # 判断当前谁在赢这墩
                current_winner = trick_winner(trick_cards, trump)
                partner = PARTNERS.get(position, "")
                is_partner_winning = current_winner in (partner, position)

                if is_partner_winning and current_winner != position:
                    # 同伴已经在赢，不浪费将牌，垫牌
                    return self._discard(playable, hand)
                else:
                    # 需要将吃
                    best_trump_played = None
                    for _, c in trick_cards:
                        if c.suit == trump:
                            if best_trump_played is None or c.rank_value > best_trump_played:
                                best_trump_played = c.rank_value
                    if best_trump_played is not None:
                        over = [c for c in trump_cards if c.rank_value > best_trump_played]
                        if over:
                            return min(over, key=lambda c: c.rank_value)
                        # 无法超将吃，垫牌
                        return self._discard(playable, hand)
                    # 没有已有将吃，最小将牌即可
                    return min(trump_cards, key=lambda c: c.rank_value)
        return self._discard(playable, hand)

    def _discard(self, playable: List[Card], hand: List[Card]) -> Card:
        """垫牌：垫最短套（保留长套实力），排除将牌花色。"""
        suit_counts = {}
        for c in hand:
            suit_counts[c.suit] = suit_counts.get(c.suit, 0) + 1
        # 按手牌张数升序（先垫短套），张数相同时垫小牌
        return min(playable, key=lambda c: (suit_counts.get(c.suit, 0), c.rank_value))

