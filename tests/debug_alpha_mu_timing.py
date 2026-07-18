"""实测 αμ 搜索在不同剩余牌数下的 nodes/dds_calls/elapsed。

直接构造 PlayState，确保 declarer_tricks + defender_tricks + 每家手牌数 = 13。
sampler 采样时会根据已打墩数正确分配牌张。
"""
import sys
import io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
import time
import traceback
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from bridge.mcts.alpha_mu import AlphaMuSearch
from bridge.mcts.dd_search import ENDPLAY_AVAILABLE
from bridge.mcts.sampler import DealSampler
from bridge.play_types import Card, PlayState, Contract, PlayPhase, PlayerRole


def build_state(hands, contract_str, declarer, decl_tricks, def_tricks,
                current_player="南"):
    """直接构造 PlayState，tricks 历史用占位（sampler 只关心 tricks 里的牌张，不需要完整历史）。

    关键：decl_tricks + def_tricks = 13 - 每家手牌数
    """
    level = int(contract_str[0])
    suit = contract_str[1:]
    contract = Contract(level=level, suit=suit, declarer=declarer)
    state = PlayState(
        contract=contract,
        hands={pos: [Card(s, r) for s, r in cards] for pos, cards in hands.items()},
        player_roles={pos: PlayerRole.AI.value for pos in ["南", "西", "北", "东"]},
        declarer_tricks=decl_tricks,
        defender_tricks=def_tricks,
        phase=PlayPhase.PLAYING,
    )
    state.current_player = current_player
    state.lead_player = current_player
    state.bidding_sequence = "(S)" + contract_str + "-(W)pass-(N)pass-"
    return state


def scenario_13_cards():
    """13张牌：开局，每家13张，已打0墩"""
    hands = {
        "北": [("♠", "A"), ("♠", "K"), ("♠", "Q"), ("♠", "J"),
               ("♥", "A"), ("♥", "J"), ("♥", "T"),
               ("♦", "K"), ("♦", "Q"), ("♦", "J"),
               ("♣", "4"), ("♣", "3"), ("♣", "2")],
        "东": [("♠", "4"), ("♠", "3"), ("♠", "2"),
               ("♥", "9"), ("♥", "8"), ("♥", "7"), ("♥", "6"),
               ("♦", "5"), ("♦", "4"), ("♦", "3"), ("♦", "2"),
               ("♣", "9"), ("♣", "8")],
        "南": [("♠", "9"), ("♠", "7"), ("♠", "6"), ("♠", "5"),
               ("♥", "K"), ("♥", "Q"), ("♥", "4"),
               ("♦", "A"), ("♦", "T"),
               ("♣", "A"), ("♣", "K"), ("♣", "Q"), ("♣", "J")],
        "西": [("♠", "8"),
               ("♥", "5"), ("♥", "3"), ("♥", "2"),
               ("♦", "9"), ("♦", "8"), ("♦", "7"), ("♦", "6"),
               ("♣", "T"), ("♣", "7"), ("♣", "6"), ("♣", "5"), ("♣", "4")],
    }
    return hands, "1NT", "南", 0, 0, "西"


def scenario_10_cards():
    """10张牌：已打3墩（12张牌已出），每家剩10张"""
    hands = {
        "北": [("♠", "A"), ("♠", "K"), ("♠", "Q"), ("♠", "J"),
               ("♥", "A"), ("♥", "J"),
               ("♦", "K"), ("♦", "Q"),
               ("♣", "4"), ("♣", "3")],
        "东": [("♠", "4"), ("♠", "3"), ("♠", "2"),
               ("♥", "9"), ("♥", "8"),
               ("♦", "5"), ("♦", "4"), ("♦", "3"),
               ("♣", "9"), ("♣", "8")],
        "南": [("♠", "9"), ("♠", "7"),
               ("♥", "K"), ("♥", "Q"),
               ("♦", "A"), ("♦", "T"),
               ("♣", "A"), ("♣", "K"), ("♣", "Q"), ("♣", "J")],
        "西": [("♥", "5"), ("♥", "3"),
               ("♦", "9"), ("♦", "8"), ("♦", "7"),
               ("♣", "T"), ("♣", "7"), ("♣", "6"), ("♣", "5"), ("♣", "4")],
    }
    return hands, "1NT", "南", 2, 1, "西"


def scenario_8_cards():
    """8张牌：已打5墩（20张牌已出），每家剩8张"""
    hands = {
        "北": [("♠", "A"), ("♠", "K"), ("♠", "Q"),
               ("♥", "A"), ("♥", "J"),
               ("♦", "K"), ("♦", "Q"),
               ("♣", "4")],
        "东": [("♠", "4"), ("♠", "3"),
               ("♥", "9"), ("♥", "8"),
               ("♦", "5"), ("♦", "4"), ("♦", "3"),
               ("♣", "9")],
        "南": [("♠", "9"), ("♠", "7"),
               ("♥", "K"), ("♥", "Q"),
               ("♦", "A"), ("♦", "T"),
               ("♣", "A"), ("♣", "K")],
        "西": [("♥", "5"), ("♥", "3"),
               ("♦", "9"), ("♦", "8"), ("♦", "7"),
               ("♣", "T"), ("♣", "7"), ("♣", "6")],
    }
    return hands, "1NT", "南", 3, 2, "西"


def scenario_4_cards():
    """4张牌：已打9墩（36张牌已出），每家剩4张"""
    hands = {
        "北": [("♠", "A"), ("♠", "K"), ("♥", "A"), ("♦", "K")],
        "东": [("♠", "4"), ("♠", "3"), ("♥", "9"), ("♦", "5")],
        "南": [("♠", "9"), ("♠", "7"), ("♥", "K"), ("♦", "A")],
        "西": [("♥", "5"), ("♦", "9"), ("♣", "T"), ("♣", "7")],
    }
    return hands, "1NT", "南", 5, 4, "西"


def verify_state(hands, decl_tricks, def_tricks):
    total_cards = sum(len(h) for h in hands.values())
    expected = 52 - (decl_tricks + def_tricks) * 4
    return total_cards, expected


def run_scenario(name, hands, contract_str, declarer, decl_tricks, def_tricks,
                 current_player, num_worlds, max_depth, time_limit, dds_budget):
    print("\n" + "=" * 70)
    print(f"场景: {name}")
    print(f"参数: worlds={num_worlds}, depth={max_depth}, "
          f"time_limit={time_limit}s, dds_budget={dds_budget}")
    print(f"endplay: {ENDPLAY_AVAILABLE}")

    total, expected = verify_state(hands, decl_tricks, def_tricks)
    print(f"总牌数: {total} (期望 {expected}), decl_tricks={decl_tricks}, def_tricks={def_tricks}")
    print("=" * 70)

    if not ENDPLAY_AVAILABLE:
        print("跳过：endplay 不可用")
        return None

    if total != expected:
        print(f"跳过：牌数不一致（{total} != {expected}）")
        return None

    state = build_state(hands, contract_str, declarer, decl_tricks, def_tricks,
                       current_player)

    sizes = {p: len(state.hands.get(p, [])) for p in ["南", "西", "北", "东"]}
    cp = state.current_player
    print(f"current_player={cp}, hand_sizes={sizes}")

    playable = state.get_playable_cards(cp)
    print(f"playable={len(playable)}: {[str(c) for c in playable]}")

    sampler = DealSampler()

    am = AlphaMuSearch(
        sampler=sampler,
        num_worlds=num_worlds,
        M=max_depth,
        time_limit=time_limit,
        dds_budget=dds_budget,
    )

    t0 = time.time()
    try:
        result = am.search(state)
    except Exception as e:
        print(f"搜索异常: {e}")
        traceback.print_exc()
        return None
    elapsed = time.time() - t0

    stats = result.get("full_output", {}).get("mcts_stats", {})
    candidates = stats.get("candidates", [])
    quick_fb = stats.get("quick_fallback", False)
    nodes = stats.get("nodes_searched", 0)
    dds_calls = stats.get("iterations", 0)
    err_stats = stats.get("err_stats", {})

    print(f"\n--- 结果 ---")
    print(f"elapsed={elapsed:.2f}s (limit={time_limit}s)")
    print(f"nodes_searched={nodes}")
    print(f"dds_calls={dds_calls}")
    print(f"candidates={len(candidates)}/{len(playable)}")
    print(f"quick_fallback={quick_fb}")
    if err_stats:
        print(f"err_stats={err_stats}")
    err_samples = stats.get("err_samples", {})
    if err_samples:
        print(f"\n--- err_samples ---")
        for k, v in err_samples.items():
            print(f"[{k}]: {v[:400]}")
    print(f"card={result.get('card')}")
    print(f"reasoning={result.get('reasoning', '')[:300]}")

    if quick_fb:
        print(f"\n⚠️ 触发 quick-DD 兜底")

    return {
        "name": name,
        "elapsed": elapsed,
        "nodes": nodes,
        "dds_calls": dds_calls,
        "candidates": len(candidates),
        "playable": len(playable),
        "quick_fallback": quick_fb,
        "time_limit": time_limit,
        "err_stats": err_stats,
    }


def main():
    print("αμ 搜索时间实测")
    print(f"Python: {sys.version.split()[0]}")

    # 与 _alpha_mu_play 自适应参数一致（生产环境 M=2 全覆盖）
    # M=1 场景用于对比（M=1 = PIMC，论文 baseline）
    scenarios = [
        ("4张 M=3",   scenario_4_cards(),  20, 3, 8.0,  5000),
        ("8张 M=2",   scenario_8_cards(),  20, 2, 12.0, 8000),
        ("10张 M=2",  scenario_10_cards(), 20, 2, 20.0, 15000),
        ("13张 M=1",  scenario_13_cards(), 20, 1, 30.0, 20000),
        ("13张 M=2",  scenario_13_cards(), 20, 2, 60.0, 20000),
    ]

    results = []
    for name, (hands, contract_str, decl, decl_t, def_t, cp), n_worlds, depth, t_lim, dds_b in scenarios:
        r = run_scenario(name, hands, contract_str, decl, decl_t, def_t, cp,
                         n_worlds, depth, t_lim, dds_b)
        if r:
            results.append(r)

    print("\n" + "=" * 70)
    print("汇总")
    print("=" * 70)
    print(f"{'场景':12s} {'limit':8s} {'elapsed':10s} {'nodes':10s} {'dds':10s} {'cand':10s} {'quick':8s}")
    for r in results:
        print(f"{r['name']:12s} {r['time_limit']:6.0f}s   {r['elapsed']:7.2f}s   {r['nodes']:8d}   {r['dds_calls']:8d}   {r['candidates']:3d}/{r['playable']:<3d}    {str(r['quick_fallback']):8s}")


if __name__ == "__main__":
    main()
