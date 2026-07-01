"""复杂场景下 alpha_mu 候选牌超时测试
模拟真实的缺门+多花色局面，DDS 评估耗时应显著增加
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
from bridge.play_service import PlayService
from bridge.play_types import Card, PlayerRole, POSITION_ORDER


class MockLLMClient:
    def chat(self, *args, **kwargs):
        return ""
    def chat_json(self, *args, **kwargs):
        return {}


def test_complex_scenario():
    """构造复杂残局：多花色、缺门、将吃可能"""
    print("=" * 70)
    print("Test: Complex scenario — multi-suit, voids, trump possibilities")
    print("=" * 70)
    print(f"endplay available: {ENDPLAY_AVAILABLE}")

    # 南打 4♠，还剩大量牌
    # 设计一个有多花色选择的局面
    hands = {
        '南': {
            'spades': 'AKQJT9',    # 6 spades
            'hearts': 'A',
            'diamonds': 'KQ',
            'clubs': 'AK',
        },
        '北': {  # dummy
            'spades': '876',
            'hearts': 'KQJT',
            'diamonds': 'AJT',
            'clubs': 'QJT',
        },
        '西': {
            'spades': '5432',
            'hearts': '9876',
            'diamonds': '987',
            'clubs': '98',
        },
        '东': {
            'spades': '',
            'hearts': '5432',
            'diamonds': '65432',
            'clubs': '765432',
        },
    }

    service = PlayService(llm_client=MockLLMClient())
    player_roles = {pos: PlayerRole.AI.value for pos in POSITION_ORDER}

    state = service.initialize(
        hands=hands, contract_str='4♠', declarer='南',
        player_roles=player_roles, bidding_sequence='',
        bid_history='(南)1♠-(西)pass-(北)4♠',
    )

    cp = state.current_player
    sizes = {p: len(state.hands.get(p, [])) for p in POSITION_ORDER}
    print(f"\nCurrent player: {cp}")
    print(f"Hand sizes: {sizes}")

    for p in POSITION_ORDER:
        cards = state.hands.get(p, [])
        print(f"  {p}: {len(cards)} cards")

    playable = state.get_playable_cards(cp)
    print(f"\nPlayable cards ({len(playable)}):")
    trump = state.contract.suit
    for c in playable:
        print(f"  {c} suit={c.suit} rank={c.rank} {'(trump)' if c.suit == trump else ''}")

    # Test with limited time to force timeout
    test_configs = [
        {"name": "10s limit", "worlds": 20, "depth": 1, "time": 10.0},
        {"name": "5s limit", "worlds": 20, "depth": 1, "time": 5.0},
        {"name": "3s limit", "worlds": 20, "depth": 1, "time": 3.0},
    ]

    for cfg in test_configs:
        print(f"\n{'='*60}")
        print(f"Config: {cfg['name']} — worlds={cfg['worlds']} depth={cfg['depth']} time={cfg['time']}s")

        sampler = DealSampler()
        am = AlphaMuSearch(
            sampler=sampler,
            num_worlds=cfg['worlds'],
            max_depth=cfg['depth'],
            time_limit=cfg['time'],
            dds_budget=20000,
        )

        t0 = time.time()
        try:
            result = am.search(state)
            elapsed = time.time() - t0
            card = result.get("card")
            print(f"  Result card: {card}")
            print(f"  Elapsed: {elapsed:.2f}s")
            reasoning = result.get("reasoning", "")
            # Extract top info
            print(f"  Reasoning (first 150 chars): {reasoning[:150]}")

            stats = result.get("full_output", {}).get("mcts_stats", {})
            candidates = stats.get("candidates", [])
            err_stats = stats.get("err_stats", {})
            print(f"  Candidates evaluated: {len(candidates)}/{len(playable)}")
            print(f"  DDS calls: {stats.get('dds_calls', '?')}")
            print(f"  Nodes searched: {stats.get('nodes_searched', '?')}")
            print(f"  Errors: {err_stats}")

            for c in candidates:
                print(f"    {c['card']:6s} worst={c['worst']} rate={c['success_rate']:.3f} "
                      f"min_t={c['min_tricks']} avg_t={c['avg_tricks']} front={c['front_size']}")

            if len(candidates) < len(playable):
                print(f"  ⚠️  TIMEOUT: Only {len(candidates)}/{len(playable)} evaluated!")
                missing = [str(c) for c in playable
                           if str(c) not in [x['card'] for x in candidates]]
                print(f"  Missing: {missing}")
            else:
                print(f"  ✅ All candidates evaluated")

        except Exception as e:
            traceback.print_exc()

    print("\n" + "=" * 70)
    print("Test complete")


if __name__ == "__main__":
    test_complex_scenario()
