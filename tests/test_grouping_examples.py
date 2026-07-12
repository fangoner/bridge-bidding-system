"""10个典型分组实例验证。"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from bridge.play_service import PlayService


def make_candidate(card, success_rate, best_vector, avg_tricks=11.0):
    return {
        "card": card,
        "success_rate": success_rate,
        "best_vector": best_vector,
        "avg_tricks": avg_tricks,
        "min_tricks": 11,
        "worst": 0,
        "success_count": int(success_rate * 60),
        "total_useful": 60,
        "front_size": 1,
        "quick": False,
    }


def show_groups(groups, triggered):
    for g in groups:
        cards = " ".join(c["card"] for c in g["cards"])
        vec = g.get("best_vector", "?")
        rate = g["success_rate"]
        print(f"    组{g['group_id']}: {cards} (成功率{rate:.0%}, vec={vec[:20]}...)")
    print(f"    触发LLM: {'是' if triggered else '否'}")


def make_service():
    svc = PlayService.__new__(PlayService)
    return svc


def main():
    svc = make_service()

    examples = [
        {
            "title": "实例1: 将牌大牌vs小牌（飞牌vs清将）",
            "desc": "♠是将牌。♠Q(飞牌方向)和♠2♠3♠4(小牌)vector相同但战术不同",
            "candidates": [
                make_candidate("♠2", 0.65, "vec_A"),
                make_candidate("♠3", 0.65, "vec_A"),
                make_candidate("♠4", 0.65, "vec_A"),
                make_candidate("♠Q", 0.65, "vec_A"),
                make_candidate("♦A", 0.50, "vec_B"),
            ],
            "trump": "♠",
        },
        {
            "title": "实例2: 跨区间连续不拆（7-8）",
            "desc": "♠7和♠8 vector相同，7是low区间，8是mid区间，但连续不拆",
            "candidates": [
                make_candidate("♠7", 0.60, "vec_A"),
                make_candidate("♠8", 0.60, "vec_A"),
                make_candidate("♥K", 0.45, "vec_B"),
            ],
            "trump": "♠",
        },
        {
            "title": "实例3: 跨区间连续不拆（T-J）",
            "desc": "♠T和♠J vector相同，T是mid区间，J是high区间，但连续不拆",
            "candidates": [
                make_candidate("♠T", 0.58, "vec_A"),
                make_candidate("♠J", 0.58, "vec_A"),
                make_candidate("♣2", 0.40, "vec_B"),
            ],
            "trump": "♠",
        },
        {
            "title": "实例4: 跨区间不连续拆分（5-T）",
            "desc": "♠5(low)和♠T(mid) vector相同但不连续，拆成2组",
            "candidates": [
                make_candidate("♠5", 0.55, "vec_A"),
                make_candidate("♠T", 0.55, "vec_A"),
                make_candidate("♥K", 0.40, "vec_B"),
            ],
            "trump": "♠",
        },
        {
            "title": "实例5: 不同花色分开分组",
            "desc": "♠2♠3和♣2♣3 vector相同，但不同花色不合并，各自独立",
            "candidates": [
                make_candidate("♠2", 0.66, "vec_X"),
                make_candidate("♠3", 0.66, "vec_X"),
                make_candidate("♣2", 0.66, "vec_X"),
                make_candidate("♣3", 0.66, "vec_X"),
                make_candidate("♠Q", 0.66, "vec_X"),
                make_candidate("♣K", 0.66, "vec_X"),
                make_candidate("♦A", 0.50, "vec_Y"),
            ],
            "trump": "♠",
        },
        {
            "title": "实例6: 0%过滤 + 低成功率全保留",
            "desc": "♠7-♠J成功率0%被过滤，剩余3组成功率都低但差距<15%，全保留（可能含唯一成局线路）",
            "candidates": [
                make_candidate("♣A", 0.10, "vec_A"),
                make_candidate("♣K", 0.10, "vec_A"),
                make_candidate("♦3", 0.08, "vec_B"),
                make_candidate("♦2", 0.08, "vec_B"),
                make_candidate("♠7", 0.0, "vec_zero"),
                make_candidate("♠8", 0.0, "vec_zero"),
                make_candidate("♠9", 0.0, "vec_zero"),
            ],
            "trump": "♠",
        },
        {
            "title": "实例7: 15%截断",
            "desc": "4组成功率[60%,58%,55%,20%]，20%与前一组差距35%≥15%被截断",
            "candidates": [
                make_candidate("♣A", 0.60, "vec_A"),
                make_candidate("♣K", 0.58, "vec_B"),
                make_candidate("♣Q", 0.55, "vec_C"),
                make_candidate("♦3", 0.20, "vec_D"),
            ],
            "trump": "♠",
        },
        {
            "title": "实例8: 单一vector单张 → 不触发LLM",
            "desc": "只有1组成功率>0%，组数<2不触发LLM",
            "candidates": [
                make_candidate("♠A", 0.25, "vec_A"),
                make_candidate("♠7", 0.0, "vec_zero"),
                make_candidate("♠8", 0.0, "vec_zero"),
            ],
            "trump": "♠",
        },
        {
            "title": "实例9: 三层区间全拆分",
            "desc": "同花色♠2(low)、♠8(mid)、♠K(high) vector相同，三档拆成3组",
            "candidates": [
                make_candidate("♠2", 0.50, "vec_A"),
                make_candidate("♠8", 0.50, "vec_A"),
                make_candidate("♠K", 0.50, "vec_A"),
                make_candidate("♥A", 0.35, "vec_B"),
            ],
            "trump": "♠",
        },
        {
            "title": "实例10: 将牌和非将牌混合（用户案例）",
            "desc": "♠8♠9(将牌)和♣K♣Q(非将牌)vector全相同（全1,100%），按区间拆分",
            "candidates": [
                make_candidate("♠8", 1.0, "vec_ALL1"),
                make_candidate("♠9", 1.0, "vec_ALL1"),
                make_candidate("♣K", 1.0, "vec_ALL1"),
                make_candidate("♣Q", 1.0, "vec_ALL1"),
            ],
            "trump": "♠",
        },
    ]

    for i, ex in enumerate(examples, 1):
        print("=" * 70)
        print(f"{ex['title']}")
        print(f"  说明: {ex['desc']}")
        print(f"  将牌: {ex['trump']}")
        inputs = [(c["card"], f"{c['success_rate']:.0%}", c["best_vector"]) for c in ex["candidates"]]
        print(f"  输入: {inputs}")
        groups = svc._group_candidates_by_vector(ex["candidates"], trump_suit=ex["trump"])
        triggered = svc._should_trigger_llm(groups, ex["candidates"])
        print(f"  分组结果:")
        show_groups(groups, triggered)
        print()


if __name__ == "__main__":
    main()
