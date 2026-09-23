import sys
import os
import random
from collections import Counter

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from bridge.play_types import Card

SUITS = list("♠♥♦♣")

south = [Card("♠", "3"), Card("♠", "2"),
         Card("♥", "A"), Card("♥", "K"), Card("♥", "2"),
         Card("♦", "Q"), Card("♦", "3"), Card("♦", "2"),
         Card("♣", "K"), Card("♣", "Q"), Card("♣", "J"), Card("♣", "T"), Card("♣", "9")]
north = [Card("♠", "Q"), Card("♠", "5"), Card("♠", "4"),
         Card("♥", "Q"), Card("♥", "4"), Card("♥", "3"),
         Card("♦", "A"), Card("♦", "K"), Card("♦", "4"),
         Card("♣", "4"), Card("♣", "3"), Card("♣", "2")]

RANKS = ["A", "K", "Q", "J", "T", "9", "8", "7", "6", "5", "4", "3", "2"]
played = {("♠", "8"), ("♠", "T")}


def remaining_cards():
    out = []
    for s in SUITS:
        for r in RANKS:
            c = Card(s, r)
            if any((h.suit == s and h.rank == r) for h in south) or \
               any((h.suit == s and h.rank == r) for h in north) or \
               (s, r) in played:
                continue
            out.append(c)
    return out


def deal_east_west(random):
    rem = remaining_cards()
    random.shuffle(rem)
    return rem[:13], rem[13:]


def main():
    N = 2000
    ECN = 30
    slot = Counter()
    key_slot = {k: Counter() for k in ["A", "K", "J"]}
    key_count = Counter()
    compat = Counter()
    rng = random.Random(12345)
    for i in range(ECN):
        s = rng.getstate()
        for _ in range(N):
            east, west = deal_east_west(rng)
            es = sum(1 for c in east if c.suit == "♠")
            ws = 6 - es  # 东西合计仅剩 6 张♠（A K J 9 7 6）：南北 5 + 已出 2（北T/西8）
            compat[(es, ws)] += 1
            for k in "AKJ":
                if any(c.suit == "♠" and c.rank == k for c in west):
                    key_slot[k]["西"] += 1
                elif any(c.suit == "♠" and c.rank == k for c in east):
                    key_slot[k]["东"] += 1
        rng.setstate(s)
    tot = ECN * N
    print("== 黑桃在两防家手中的张数分布（1000x30 世界） ==")
    for (e, w), c in sorted(compat.items()):
        print(f"东{e}张-西{w}张: {c/tot*100:6.2f}%")
    print()
    print("== ♠A/K/J 归属（赢张位置） ==")
    for k in "AKJ":
        print(f"♠{k}: 西 {key_slot[k]['西']/tot*100:.1f}% / 东 {key_slot[k]['东']/tot*100:.1f}%")


if __name__ == "__main__":
    main()