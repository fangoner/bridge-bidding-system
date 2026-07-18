"""验证 M bug 修复效果：M=1 应为 PIMC (~260 DDS)，非之前的 8294。
"""
import sys, io, time, traceback
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from bridge.mcts.alpha_mu import AlphaMuSearch, ENDPLAY_AVAILABLE
from bridge.mcts.sampler import DealSampler
from bridge.play_types import Card, PlayState, Contract, PlayPhase, PlayerRole


def build_state(hands, contract_str, declarer, decl_tricks, def_tricks,
                current_player="南"):
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
    state.bidding_sequence = "(S)1NT-(W)pass-(N)pass-"
    return state


def _h(cards_str):
    """'SA SK HQ D2 C3' → [('♠','A'), ('♠','K'), ...]"""
    suit_map = {'S': '♠', 'H': '♥', 'D': '♦', 'C': '♣'}
    result = []
    for token in cards_str.split():
        s = suit_map[token[0]]
        r = token[1:]
        result.append((s, r))
    return result


# ── 场景定义 ──
# 13 张：完整一手牌
S13_HANDS = {
    "北": _h("SA SK SQ SJ HA HJ HT DK DQ DJ C4 C3 C2"),
    "东": _h("S4 S3 S2 H9 H8 H7 H6 D5 D4 D3 D2 C9 C8"),
    "南": _h("S9 S7 S6 S5 HK HQ H4 DA DT CA CK CQ CJ"),
    "西": _h("S8 ST H5 H3 H2 D9 D8 D7 D6 CT C7 C6 C5"),
}

# 8 张：残局
S8_HANDS = {
    "北": _h("SA SK SQ HA HJ DK DQ C4"),
    "东": _h("S4 S3 H9 H8 D5 D4 D3 C9"),
    "南": _h("S9 S7 HK HQ DA DT CA CK"),
    "西": _h("H5 H3 D9 D8 D7 CT C7 C6"),
}

# 4 张：深残局
S4_HANDS = {
    "北": _h("SA SK HA DK"),
    "东": _h("S4 S3 H9 D5"),
    "南": _h("S9 S7 HK DA"),
    "西": _h("H5 D9 CT C7"),
}


def verify_total(hands, decl_tricks, def_tricks):
    total = sum(len(h) for h in hands.values())
    expected = 52 - (decl_tricks + def_tricks) * 4
    return total == expected, total, expected


def run(name, hands, contract_str, declarer, decl_t, def_t, cp,
        num_worlds, M, time_limit):
    ok, total, expected = verify_total(hands, decl_t, def_t)
    if not ok:
        print(f"  SKIP: 牌数={total}, 期望={expected}")
        return None
    if not ENDPLAY_AVAILABLE:
        print(f"  SKIP: endplay 不可用")
        return None

    state = build_state(hands, contract_str, declarer, decl_t, def_t, cp)
    playable = state.get_playable_cards(cp)

    sampler = DealSampler()
    am = AlphaMuSearch(
        sampler=sampler,
        num_worlds=num_worlds,
        M=M,
        time_limit=time_limit,
        dds_budget=50000,
    )

    t0 = time.time()
    try:
        result = am.search(state)
    except Exception as e:
        print(f"  ERROR: {e}")
        traceback.print_exc()
        return None
    elapsed = time.time() - t0

    stats = result.get("full_output", {}).get("mcts_stats", {})
    err = stats.get("err_stats", {})
    card = result.get("card")

    # 计算理论 DDS 下限
    n_w = len([w for w in [None] if False])  # placeholder, 实际 worlds 数从输出取
    # PIMC: 每个候选牌 × N worlds = candidates × num_worlds
    pimc_expected = len(playable) * num_worlds

    return {
        "name": name, "elapsed": elapsed, "M": M,
        "nodes": stats.get("nodes_searched", 0),
        "dds_calls": stats.get("iterations", 0),
        "candidates": len(stats.get("candidates", [])),
        "playable": len(playable),
        "pimc_expected": pimc_expected,
        "tt_hit": err.get("tt_hit", 0),
        "early_cut": err.get("early_cut", 0),
        "root_cut": err.get("root_cut", 0),
        "card": str(card) if card else "?",
        "err_stats": err,
    }


def main():
    print("=" * 80)
    print("M Bug 修复验证")
    print("=" * 80)

    # 关键场景：M=1 修复前后对比
    #   修复前：13张 M=1 → DDS 8294 次 (因为 Min 层在 M=0 仍递归)
    #   修复后：13张 M=1 → DDS ~260 次 (PIMC: 13候选 × 20worlds)
    scenarios = [
        # (name, hands, contract, decl, decl_t, def_t, cp, worlds, M, time_limit)
        ("13张 M=1 (PIMC)",       S13_HANDS, "1NT", "南", 0, 0, "西", 20, 1, 10.0),
        ("13张 M=2",              S13_HANDS, "1NT", "南", 0, 0, "西", 20, 2, 20.0),
        ("8张 M=2 (残局)",         S8_HANDS,  "1NT", "南", 3, 2, "西", 20, 2, 12.0),
        ("4张 M=3 (深残局)",       S4_HANDS,  "1NT", "南", 5, 4, "西", 20, 3, 8.0),
    ]

    results = []
    for args in scenarios:
        name = args[0]
        print(f"\n{'─'*60}")
        print(f"▶ {name}")
        r = run(*args)
        if r:
            results.append(r)
            print(f"  耗时={r['elapsed']:.2f}s | nodes={r['nodes']} | "
                  f"DDS={r['dds_calls']} (PIMC预期={r['pimc_expected']}) | "
                  f"候选={r['candidates']}/{r['playable']}")
            print(f"  TT_hit={r['tt_hit']} | EarlyCut={r['early_cut']} | "
                  f"RootCut={r['root_cut']}")
            print(f"  选牌={r['card']}")

    # 汇总
    print(f"\n{'='*80}")
    print(f"{'场景':20s} {'耗时':>8s} {'DDS调用':>8s} {'PIMC预期':>8s} "
          f"{'TT':>5s} {'ECut':>5s} {'RCut':>5s} {'选牌':>6s}")
    print(f"{'─'*80}")
    for r in results:
        print(f"{r['name']:20s} {r['elapsed']:7.2f}s {r['dds_calls']:8d} "
              f"{r['pimc_expected']:8d} {r['tt_hit']:5d} {r['early_cut']:5d} "
              f"{r['root_cut']:5d} {r['card']:>6s}")

    # 关键断言
    print(f"\n{'='*80}")
    print("关键检查:")
    for r in results:
        if r['M'] == 1:
            ratio = r['dds_calls'] / r['pimc_expected'] if r['pimc_expected'] > 0 else 999
            status = "✅ PASS" if ratio < 2.0 else f"❌ FAIL ({ratio:.1f}x 预期)"
            print(f"  {r['name']}: DDS={r['dds_calls']}, PIMC预期={r['pimc_expected']}, "
                  f"比值={ratio:.1f} → {status}")


if __name__ == "__main__":
    main()
