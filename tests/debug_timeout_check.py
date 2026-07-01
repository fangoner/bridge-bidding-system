"""检查 alpha_mu 候选牌超时修复是否生效"""
import sys
import io
# Fix Windows GBK encoding for Unicode suits
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


def test_13_card_scenario():
    print("=" * 70)
    print("Test: 13-card scenario with alpha_mu timeout fix")
    print("=" * 70)
    print(f"endplay available: {ENDPLAY_AVAILABLE}")

    # All four hands have full suits
    hands = {
        '北': {'spades': 'AKQJT9876543', 'hearts': '', 'diamonds': '', 'clubs': ''},
        '东': {'spades': '', 'hearts': 'AKQJT9876543', 'diamonds': '', 'clubs': ''},
        '南': {'spades': '', 'hearts': '', 'diamonds': 'AKQJT9876543', 'clubs': ''},
        '西': {'spades': '', 'hearts': '', 'diamonds': '', 'clubs': 'AKQJT98765432'},
    }

    service = PlayService(llm_client=MockLLMClient())
    player_roles = {pos: PlayerRole.AI.value for pos in POSITION_ORDER}

    state = service.initialize(
        hands=hands, contract_str='7NT', declarer='北',
        player_roles=player_roles, bidding_sequence='', bid_history='',
    )

    cp = state.current_player
    sizes = {p: len(state.hands.get(p, [])) for p in POSITION_ORDER}
    print(f"\nCurrent player: {cp}")
    print(f"Hand sizes: {sizes}")
    print(f"Declarer tricks: {state.declarer_tricks}, Defender tricks: {state.defender_tricks}")

    playable = state.get_playable_cards(cp)
    print(f"Playable cards ({len(playable)}):")
    for c in playable:
        print(f"  {c} suit={c.suit} rank={c.rank}")

    print(f"\nTesting alpha_mu search...")
    print(f"  num_worlds=20, max_depth=1, time_limit=60.0s, dds_budget=20000")

    sampler = DealSampler()

    am = AlphaMuSearch(
        sampler=sampler,
        num_worlds=20,
        max_depth=1,
        time_limit=60.0,
        dds_budget=20000,
    )

    t0 = time.time()
    try:
        result = am.search(state)
        elapsed = time.time() - t0
        card = result.get("card")
        print(f"\nResult card: {card}")
        print(f"Elapsed: {elapsed:.2f}s")
        print(f"Reasoning: {result.get('reasoning', '')[:200]}")

        stats = result.get("full_output", {}).get("mcts_stats", {})
        candidates = stats.get("candidates", [])
        print(f"\nCandidates evaluated: {len(candidates)}")
        for c in candidates:
            print(f"  {c['card']:6s} worst={c['worst']} rate={c['success_rate']:.3f} "
                  f"min_t={c['min_tricks']} avg_t={c['avg_tricks']} "
                  f"front={c['front_size']}")

        # Check for timeout truncation
        if len(candidates) < len(playable):
            print(f"\nWARNING: Only {len(candidates)}/{len(playable)} candidates evaluated!")
            missing = [str(c) for c in playable
                       if str(c) not in [x['card'] for x in candidates]]
            print(f"  Missing: {missing}")
        else:
            print(f"\nOK: All {len(playable)} candidates evaluated")

    except Exception as e:
        traceback.print_exc()

    print("\n" + "=" * 70)
    print("Test complete")


if __name__ == "__main__":
    test_13_card_scenario()
