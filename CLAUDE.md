# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Overview

Bridge bidding and card play practice system with AI integration. Bidding: two-player/four-player using JF conventions, DeepSeek API for AI decisions, 5-path fallback mechanism with keyword extraction from JF convention document. Card play: full trick-taking state machine with 7 engines — LLM, MCTS (determinization + UCT tree search), DD (Monte Carlo + DirectDDS), Perfect DD (full-info double-dummy), Tiered (multi-engine auto-scheduling), αμ (Pareto search solving PIMC defects), and αμ+LLM (αμ + LLM strategy review). Also uses Doubao Vision API for screenshot recognition, Deep Finesse (external exe) and endplay (Python library) for contract analysis.

## Development Commands

### Installation
```bash
pip install -r requirements.txt
cd web && npm install
```

### Running the CLI Application
```bash
python main.py
```
Main menu: deal hands, settings, run bidding, analyze contracts, view history, test bidding sequences.

### Running the Web API Backend
```bash
cd api
uvicorn main:app --host 127.0.0.1 --port 8003
```
Or use convenience scripts: `start_backend.bat` (backend only), `start_web.bat` (frontend only), or chain both.

### Running the Web Frontend
```bash
cd web && npm run dev
```
Frontend runs on `http://localhost:5173` (Vite). Requires backend API on port 8003.

### Testing
- **Bidding sequence test** (menu option 7): Tests keyword extraction, JF retrieval, and preprocessing interactively.
- **Unit tests**: ~30 individual scripts in `tests/`, covering bidding sequences (openings, responses, 1NT, 2D, third-fourth seat, etc.), keyword extraction, tree navigation, and preprocessing. E.g. `python tests/test_1c_1d.py`.
- **API tests**: `python test_api.py` (requires running backend).
- **endplay test**: `python endplay_integration.py`.

### Packaging
- **Quick build**: `build.bat` or `pyinstaller build.spec --clean`
- **Update release**: `update_release.bat` (copies to `release_桥牌叫牌练习/`)
- **Installer**: Inno Setup with `installer.iss`
- Details in `DEVELOPMENT.md`.

### Using Claude Code with DeepSeek
```bash
claude-deepseek.bat
```
Sets `ANTHROPIC_BASE_URL`, `ANTHROPIC_MODEL` (`deepseek-v4-flash`), `API_TIMEOUT_MS` (600000ms).

## Getting Started
### Prerequisites
- Python 3.x, Node.js 18+
- DeepSeek API key (for AI bidding)
- Doubao Vision API key (optional, for screenshot recognition)
- Deep Finesse 2014 v2 executable (optional, for contract analysis)
- JF convention document (`JF实战_标准自然 - Rev 3.2.docx`) in project root

### Environment Setup (`.env`)
```env
DEEPSEEK_API_KEY=your_deepseek_api_key
DEEPSEEK_BASE_URL=https://api.deepseek.com
DOUBAO_API_KEY=your_doubao_api_key
DOUBAO_BASE_URL=https://ark.cn-beijing.volces.com/api/v3
DOUBAO_VISION_ENDPOINT=your_vision_endpoint_id
DOUBAO_SEED_ENDPOINT=your_seed_endpoint_id
```

## Project Architecture

### Directory Structure
```
├── main.py                 # CLI application entry point
├── api/main.py             # FastAPI web backend (1320 lines, 25+ endpoints)
├── config.py               # Centralized configuration
├── bridge/                 # Core bridge logic
│   ├── dealer.py           # Hand generation, HCP, distribution
│   ├── bidding.py          # Bidding sequence parsing, keyword extraction
│   ├── bidding_service.py  # AI bidding service wrapper
│   ├── play_types.py       # Card, Trick, Contract, PlayState dataclasses
│   ├── play_engine.py      # Card play state machine (rules, undo)
│   ├── play_service.py     # AI play service (declarer/defender prompts)
│   ├── deep_finesse.py     # Deep Finesse external exe integration
│   ├── output_format.py    # Graphical/compact/DF output generation
│   └── mcts/               # MCTS/DD/αμ play engines (determinization + search)
│       ├── __init__.py      # Exports MctsSearch, DealSampler, HeuristicRollout, RandomizedRollout, DDSearch
│       ├── search.py        # MCTS determinization + UCT tree search
│       ├── dd_search.py     # Monte Carlo + DirectDDS evaluation, endgame enumeration
│       ├── alpha_mu.py      # αμ Pareto search engine (2019 Cazenave & Ventos)
│       ├── direct_dds.py    # ctypes direct DDS C library wrapper (v1.50)
│       ├── sampler.py       # DealSampler: uniform sampling with level-based constraint validation
│       ├── rollout.py       # HeuristicRollout + RandomizedRollout: fast playout
│       ├── constraints.py   # BidConstraint: constraint validation (L1/L2/L0 levels)
│       ├── bid_constraint_library.py  # Bidding constraint definitions
│       ├── bit_hands.py     # Bit-level hand representation for DDS
│       ├── belief.py        # Utility functions: void detection, signal evidence collection
│       ├── signals.py       # Defense signal models (attitude/count/suit preference)
│       ├── llm_validator.py # LLM play validation layer (rule-based checks)
│       └── state_utils.py   # Shared utilities: hand cloning, card application, PBN/endplay conversion
├── knowledge/
│   └── loader.py           # JF document parsing, tree retrieval
├── llm/
│   ├── prompts.py          # System/fallback/human/play prompts (~590 lines)
│   ├── deepseek_client.py  # DeepSeek API via OpenAI SDK
│   └── doubao_client.py    # Doubao Vision API client
├── utils/
│   ├── history.py          # JSON-based bidding history storage
│   └── screenshot.py       # Screen capture via MSS
├── endplay_integration.py  # Batch double dummy analysis via endplay library
└── web/                    # React frontend (React 19 + Vite + MUI)
    ├── src/App.jsx         # Main app with all game state (~2375 lines)
    ├── src/components/     # 14+ React components + layout/ subdir
    ├── src/context/        # 3 context providers (BiddingContext, PlayContext, GameContext)
    ├── src/hooks/          # 7 custom hooks
    ├── src/services/       # API service layer (api.js)
    ├── src/theme/          # Theme system (colorSchemes.js, dark mode)
    ├── src/constants/      # Shared constants (suits.js)
    ├── src/utils/          # Frontend utilities (biddingUtils.js)
    └── src/styles/         # Separated style modules
```

### Core Modules
- **`bridge/dealer.py`**: `BridgeDealer` class, `Hand` dataclass (HCP, distribution), `DealMode` enum, manual input parsing, `Position` enum.
- **`bridge/bidding.py`**: `extract_retrieval_keyword()` - maps sequence to JF keyword; structural convention judgment (opening/two-bid/third-fourth seat vs fallback); partner position logic; consecutive pass detection.
- **`bridge/bidding_service.py`**: `BiddingService` class - orchestrates keyword extraction, JF retrieval, main/fallback prompt switching, bid meanings accumulation.
- **`knowledge/loader.py`**: `JFLoader` loads docx, segments by headings; `JFRetriever` matches keywords, builds tree from indentation (`│----`), `navigate_tree_by_bids()` for multi-bid decomposition and preprocessing.
- **`bridge/play_engine.py`**: `PlayEngine` - state machine for card play with lead/dummy_reveal/playing/complete phases; card following rules; undo support (per-card and per-trick).
- **`bridge/play_service.py`**: `PlayService` - AI card play logic. Supports 7 engines: LLM, MCTS, DD, Perfect DD, Tiered, αμ, αμ+LLM. Engine selected via `play_engine` param. v1.50: BeliefTracker removed, uniform sampling with level-based constraint validation.
- **`bridge/mcts/search.py`**: `MctsSearch` - Single-dummy MCTS with determinization. Each iteration samples unknown hands, then runs Selection→Expansion→Simulation→Backpropagation using UCT. Adaptive iteration scaling based on remaining unknown cards.
- **`bridge/mcts/dd_search.py`**: `DDSearch` - Pure Monte Carlo + DirectDDS (v1.50). Uniform samples, batch DDS via `solve_all_boards_raw()`, 3-layer tie-breaking. Supports `search()` (MC), `search_perfect()` (full-info DD), endgame enumeration. v1.50 removed endplay dependency entirely.
- **`bridge/mcts/sampler.py`**: `DealSampler` - Uniform random sampling (v1.50) with level-based constraint validation fallback chain. `_sample_uniform()` shuffles unknown pool and distributes per remaining counts. Attempt chain (number = order): L0 (MH repair) → L1 (master-soft) → L2 (relaxed, 50 retries) → L3 (voids only, 20) → final least-violating. Removed BeliefTracker and old 3-step biased generation.
- **`bridge/mcts/rollout.py`**: `HeuristicRollout` (deterministic) and `RandomizedRollout` (stochastic weighted) for MCTS simulation to hand completion.
- **`bridge/mcts/constraints.py`**: `BidConstraint` dataclass; source-based classification (`is_hard_source`, `is_ignored_source`); verification fns `validate_hard()` / `validate_relaxed()` / `validate_voids_only()`; `compute_sample_violation_score()` retained for diagnostics only.
- **`bridge/mcts/direct_dds.py`**: ctypes direct DDS library wrapper (v1.50). `solve_all_boards_raw()` (Card-based) and `solve_all_boards_bits()` (bitmap-based) bypass endplay PBN/Deal conversion. ~6x faster than endplay path.
- **`bridge/mcts/alpha_mu.py`**: `AlphaMuSearch` - Pareto search engine (2019 Cazenave & Ventos). Implements all 5 optimizations from 2021 paper (v1.50): Cut on Win, Maintaining Useful Worlds, World Cuts, Deep Alpha Cut, Empty Entry, Leaf Parallelization. Uses OutcomeVector/ParetoFront data structures, iterative deepening M=1..M, transposition table, DirectDDS bitmap leaf evaluation.
- **`bridge/mcts/belief.py`**: Utility functions only (v1.50). `collect_voids()` for void detection, `collect_signal_evidence()` for LLM prompt injection. BeliefTracker class removed.
- **`bridge/mcts/bid_constraint_library.py`**: Bid constraint definitions — maps bidding sequences to HCP/suit length/control constraints for sample validation.
- **`bridge/mcts/bit_hands.py`**: Bit-level hand representation for efficient DDS board construction.
- **`bridge/mcts/signals.py`**: Defense signal models — attitude (high=welcome/low=not), count, suit preference. `collect_all_signals()` gathers evidence from tricks; `format_partner_signals_for_prompt()` injects into LLM defense prompts.
- **`bridge/mcts/llm_validator.py`**: Rule-based LLM play validation. Checks: (1) card legality, (2) 4th seat "can win but plays small", (3) 2nd seat "small covers big". Falls back to `_select_best_card` on validation failure.
- **`bridge/deep_finesse.py`**: Integration with Deep Finesse 2014 v2 executable for contract analysis.
- **`bridge/output_format.py`**: Three display formats (graphic, compact, Deep Finesse) generated programmatically without LLM calls.
- **`llm/prompts.py`**: All prompt templates (bidding main/fallback/human, play declarer/defender/common rules).
- **`endplay_integration.py`**: Batch double dummy analysis using `endplay` library; analyzes all 20 declarer-trump combinations; formats into compact table.

### Web Architecture
- **Backend** (FastAPI, `api/main.py`, 1320 lines): 25+ REST endpoints organized by function:
  - Game: `POST /api/deal`, `/api/custom-deal`, `/api/image-deal`, `/api/screenshot-deal`, `/api/read-clipboard`
  - Bidding: `POST /api/bid`, `/api/human-bid`, `/api/analyze`, `/api/reload-jf`
  - Output: `POST /api/output-formats`, `/api/analyze-contract`
  - Play: `POST /api/play/init`, `/api/play/card`, `/api/play/ai-play`, `/api/play/undo`, `/api/play/update-roles`, `GET /api/play/state`
  - Analysis: `POST /api/double-dummy`
  - Config: `GET/POST /api/fallback-model`, `/api/ai-provider`, `GET /api/health`
- **Frontend** (React 19 + Vite + MUI, `web/`): 14+ components in `src/components/` (plus `layout/` and `mobile/` subdirs), 6 custom hooks in `src/hooks/`. State managed via `useBiddingState` and `useBridgeRecords` hooks. Dark mode via `theme/colorSchemes.js` with local storage persistence. API calls centralized in `services/api.js`. Error boundary via `ErrorBoundary.jsx`.
- **Shared logic**: CLI and web API both use `BiddingService` for bidding, `PlayService` for card play.

### Key Data Structures
- `Hand`: HCP, distribution string, display string.
- `Position`: Enum (North, East, South, West).
- `DealMode`: Enum (free, manual, screenshot, Deep Finesse input).
- `BiddingGame`: Main state machine holding hands, sequence, dealer, mode, AI clients.
- `BiddingService`: Service wrapper for LLM calls, fallback switching, bid meanings.
- `Card`: suit + rank, with comparison (rank_value, suit_order).
- `Contract`: level, suit, declarer, doubled/redoubled, tricks_needed.
- `Trick`: cards list, leader, trump, winner detection, AI metadata.
- `PlayState`: complete game state - hands, contract, tricks, current_player, phase, declarer/defender trick counts.
- `PlayPhase`: Enum (lead, dummy_reveal, playing, complete).

### Bidding Flow
1. **Deal**: Random generation or manual/screenshot/DF input.
2. **Bidding Loop**: For each position, extract keyword → retrieve JF content → preprocess subsequent bids → call AI (or human).
3. **AI Decision**: Main prompt (structural conventions) or fallback prompt (no JF match). Fallback triggered when preprocessing returns empty or main prompt outputs "JF无合格叫品".
4. **End**: Three consecutive passes end the auction.
5. **Output**: Generate graphical/compact/Deep Finesse formatted results.

### Card Play Flow
1. **Init**: After bidding, `PlayService.initialize()` creates `PlayState` with contract, hands, player roles.
2. **Lead phase**: Opening lead from left of declarer.
3. **Dummy reveal**: After opening lead, dummy's hand is revealed (visible to all).
4. **Playing**: 4-player trick-taking with follow-suit rules. AI decisions via one of seven engines:
   - **LLM** ("llm"): Uses declarer/defender prompts with played cards tracking, defense signals, and trump-cleared detection.
   - **MCTS** ("mcts"): Determinization + UCT tree search. Samples unknown hands, builds search tree over legal plays, runs heuristic rollouts to evaluate leaf nodes.
   - **DD** ("dd"): Pure Monte Carlo + DirectDDS. Uniform samples, batch DDS via `solve_all_boards_raw()`, 3-layer tie-breaking (avg significance → small card preference → avg fallback).
   - **Perfect DD** ("perfect"): Full-info double-dummy. Single `solve_board` gives exact tricks for all legal cards. Only in deal-practice mode.
   - **Tiered** ("tiered"): Multi-engine auto-scheduling. Opening lead → DD+LLM fusion, midgame → DD+tiered LLM upgrade, endgame (≤6 cards) → αμ or DD enumeration.
   - **αμ** ("alphamu"): Pareto search (Cazenave & Ventos 2019). OutcomeVector + ParetoFront, solves PIMC strategy fusion/non-locality defects. Adaptive depth by remaining cards.
   - **αμ+LLM** ("alphamu_llm"): αμ search + LLM strategy review. Groups candidate cards by suit+rank tier, triggers LLM when groups are close in success rate.
   - Engine selection via `play_engine` API param or `DEFAULT_PLAY_ENGINE` config.
5. **Undo**: Supports per-card undo (restores hand, phase, current_player). Recursive undo across completed tricks.
6. **Complete**: After 13 tricks, result calculated (made/undertricks).

## AI Integration Details

### Retrieval Keyword Extraction
- Bidding sequences stored as `(S)1H-(W)pass-(N)2C-`.
- `extract_retrieval_keyword()` in `bridge/bidding.py` extracts keywords based on sequence length, position, and deal system.
- **Structural conventions** (use main prompt): Opening bids, two-bid keywords (`1D-1H`), third-fourth seat opening of 1-major.
- **Non-structural** (use fallback prompt): Everything else including section numbers like `12.3.x`.
- **Specialized extraction**: 1NT/1C/1D/1-major opening after opponent intervention (handles double, overalls, multi-Landy based on `deal_system`).

### Tree-Structured Retrieval and Preprocessing
- `parse_content_to_tree()` converts convention segments to trees based on `│----` indentation.
- `navigate_tree_by_bids()` navigates tree by bidding sequence, auto-skipping opening bid root nodes.
- Multi-bid lines with "/" decomposed into parallel bids (e.g., "2S/3C/D/H").
- Single letters (C, D, H, S) auto-inferred as 3-level bids.
- Empty preprocessing auto-falls back to "成局与满贯" (game and slam) keyword.

### Prompt System
- **Main Prompt** (`BIDDING_SYSTEM_PROMPT`): 12 output fields. Must output "JF无合格叫品" when no valid bid. Cannot choose bid independently when preprocessing and partner suggestions are both empty.
- **Fallback Prompt** (`BIDDING_FALLBACK_PROMPT`): 19 output fields (adds fit suits, shape points, game judgment). Always returns valid bid.
- **Human Prompt** (`HUMAN_BID_PROMPT`): Context for human players with preprocessing results.
- **Play Prompts** (`PLAY_DECLARER_PROMPT`, `PLAY_DEFENDER_PROMPT`, `PLAY_COMMON_RULES`, `PLAY_COMMON_SITUATION`): Declarer gets global plan + per-trick planning; defender gets per-position plans; both get trump-cleared detection.
- **All prompts** forbid exposing actual hand info (HCP, distribution, specific cards).

### AI Client
- `DeepSeekClient` in `llm/deepseek_client.py`: OpenAI SDK with JSON schema validation.
- Dual provider support: DeepSeek (`deepseek-v4-flash`/`deepseek-v4-pro`) or Doubao Seed API.
- Separate model selection for main prompt (default `deepseek-v4-flash`) and fallback prompt (default `deepseek-v4-flash`), each configurable to chat or reasoner model.
- Temperature: 0.2 for main prompt, 0.5 for fallback prompt.
- Config keys in `config.py`: `DEFAULT_MAIN_PROMPT_MODEL`, `DEFAULT_FALLBACK_MODEL`, `DEFAULT_AI_PROVIDER`, `SHOW_FULL_LLM_OUTPUT`.

### Play Engine Configuration
- `DEFAULT_PLAY_ENGINE`: "llm" (default), "mcts", "dd", "perfect", "tiered", "alphamu", "alphamu_llm".
- `MCTS_ITERATIONS`: Max iterations per play decision (default 5000).
- `MCTS_TIME_LIMIT`: Hard time cap per decision in seconds (default 10.0).
- `MCTS_EXPLORATION_CONSTANT`: UCT exploration weight (default 1.414).
- `ROLLOUT_GREEDY_PROB`: Heuristic play probability (default 0.80).
- `DD_NUM_SAMPLES`: Max samples per DD decision (default 200). Adaptively scaled.
- `DD_MIN_SAMPLES`: Floor for adaptive sample scaling (default 15).
- `DD_TIME_LIMIT`: Time cap for DD decisions (default 30.0).
- `DD_MAXIMIN_ENABLE`: Maximin card selection (default True). Mixes avg and min to prefer stable cards.
- `DD_ENDGAME_CARD_THRESHOLD`: Cards/hand ≤ this triggers enumeration (default 4).
- `ALPHA_MU_ENABLE`: Enable αμ engine (default True).
- `ALPHA_MU_NUM_WORLDS`: Worlds per αμ search (default 20).
- `ALPHA_MU_M`: Max recursion depth (default 2; forced to 1 when >8 cards remain).
- `ALPHA_MU_TIME_LIMIT`: Time cap per αμ decision (default 60.0).
- `ALPHA_MU_ENDGAME_CARDS`: Cards/hand ≤ this triggers αμ in Tiered engine (default 8).
- `DD_PARTICLES_MIN/MAX`: DD sample count bounds for API config (100/2000).
- `MCTS_PARTICLES_MIN/MAX`: MCTS iteration bounds for API config (300/1000).
- `ALPHA_MU_WORLDS_MIN/MAX`: αμ world count bounds for API config (30/500).
- `SIGNAL_MIN_RANK`: Minimum rank for high-card defense signal (default 8).
- `TIERED_ENDGAME_CARDS`, `TIERED_*`: Tiered engine thresholds (see config.py).

### Double Dummy Analysis
- **endplay integration** (`endplay_integration.py`): Batch analysis of all 20 declarer-trump combos via `calc_dd_table()`.
- Results formatted as compact table (rows: S/H/D/C/NT, columns: N/E/S/W).
- Also supports single contract analysis via `solve_board()`.
- Web API: `POST /api/double-dummy`.
- CLI: Menu option 9 (requires `pip install endplay`).
- **Deep Finesse** (`bridge/deep_finesse.py`): External executable integration for contract analysis. Web "检验定约" button auto-focuses DF window.

## Important Conventions
- **Bidding sequence format**: `(S)1H-(W)pass-(N)2C-` (position prefix + bid, hyphen separated).
- **Bid priority**: At same level, higher-ranking suits (S > H > D > C) over NT.
- **Partner consecutive pass**: In four-player bidding, when both partners have passed consecutively after first substantive bid, they auto-pass (no AI calls).
- **Terminology**: "发牌人" (dealer) for first bidder; "庄家" (declarer) for final contract display.
- **Config**: Centralized in `config.py` - includes AI provider, main/fallback models, temperatures, DF paths, deal system default, output modes.
- **Output formats**: Three display formats (graphic, compact, Deep Finesse) generated without LLM calls.

## Code Style
- Python type hints and dataclasses where appropriate.
- Module-level constants in UPPERCASE.
- Chinese in user-facing strings and comments; English for technical identifiers.
- Follow patterns in `bridge/dealer.py` and `bridge/bidding.py` for new code.

## References
- `AGENTS.md` — companion file with critical gotchas, alpha cut rules, DeepSeek thinking mode, and non-obvious behaviors
- `DEVELOPMENT.md` — detailed development notes, version history, and architecture deep-dives
- `.env.example` — environment template
- `CHANGELOG.md` — version history
