# CLAUDE.md

This file is the canonical reference for working in this repository: architecture, data structures, and workflows.

> **文档纪律（重要）**：本文件于 2026-09-20 依代码逐条重写——此前它长期滞后（曾同时描述 7 个打牌引擎、已删除的 `search.py`/`rollout.py`/`endplay_integration.py`，以及多个不存在的配置常量）。
> 改动代码时**必须同步本文件**；凡涉及模块/函数/配置常量名，**以代码为准，不要引用本文件的记忆**。漂移成因与治理记录见 `docs/开发文档整理_发现清单_20260920.md`。

## Overview

Bridge bidding and card play practice system with AI integration.

- **Bidding**: two-player / four-player practice using JF conventions (plus an alternative 新睿/XR 二盖一 system), DeepSeek API for AI decisions, main-prompt / fallback-prompt mechanism with keyword extraction from the JF convention document.
- **Card play**: full trick-taking state machine with **4 engines** — LLM, DD (Monte Carlo + DirectDDS), Perfect DD (full-info double-dummy), αμ (Pareto search solving PIMC defects) — plus a finesse-intervention rule layer that sits on top of the engine result.
- Also uses Doubao Vision API for screenshot recognition, and Deep Finesse (external exe) / DDS for contract analysis.

## Development Commands

### Installation

```bash
pip install -r requirements.txt
cd web && npm install
```

> `requirements.txt` is **incomplete**. `python-dotenv` (imported at module level by `config.py`), `endplay` (used by `direct_dds._load_dll()` to locate `dds.dll`) and `pillow` (screenshot) are needed at runtime but are not listed. Without `endplay`, `is_dds_available()` returns False and every DD / Perfect DD / αμ decision silently degrades to rule-based card selection.

### Running the CLI Application

```bash
python main.py
```

Main menu: deal hands, settings, run bidding, analyze contracts, view history, test bidding sequences. Batch double-dummy analysis is 主菜单 `5 定约分析` → `2` (the label still says "（endplay）" but the implementation is `dd_analysis.py` + DirectDDS).

### Running the Web API Backend

```bash
uvicorn api.main:app --host 0.0.0.0 --port 8003
```

Do **not** use `--reload` (it may crash when several files change in succession). Convenience scripts: `start_backend.bat` (backend only), `start_web.bat` (**starts both** backend and frontend — note it still passes `--reload`, a legacy inconsistency), `start_services.ps1`.

### Running the Web Frontend

```bash
cd web && npm run dev
```

Frontend runs on `http://localhost:5173` (Vite, `strictPort: true`, `/api` proxied to `localhost:8003`).

### Testing

- **Unit tests**: standalone scripts in `tests/`, run directly — e.g. `python tests/test_finesse_pipeline.py`. **No pytest, no conftest, no test runner.**
  Current state: 21 top-level files (13 `test_*`, 8 `debug_*`/`verify_*`). The bidding-sequence corpus (~31 files, e.g. `test_1c_1d.py`) has been **archived to `tests/_stale/`** and is no longer maintained; `tests/README.md` is stale.
- **Finesse pipeline** (main regression for the play rule layer): `tests/test_finesse_pipeline.py` (29 cases), `tests/test_probe_finesse.py` (8 cases).
- **Finesse doc-sync guard**: `python tests/test_finesse_doc_sync.py` — verifies `docs/飞牌介入管线图解.md` still matches the code (29 function/constant symbols + 8 `FINESSE_*` threshold values). **Run it after any finesse-code or `FINESSE_*` change**; it exits 1 and lists each mismatch. It cannot detect branch reordering, new branches, or internal predicate changes — those still need a manual read of the diagram.
- **One-shot runner for all three finesse checks**: `run_finesse_tests.bat` (project root) — runs doc-sync + `test_finesse_pipeline.py` + `test_probe_finesse.py`, prints a per-script PASS/FAIL and a final `RESULT:` line, exits 0/1. Nothing invokes it automatically (no test runner, no git hooks installed).
- **Bidding sequence test** (CLI menu option 7): interactive keyword extraction / JF retrieval / preprocessing check.
- **API tests**: `python test_api.py` — that file **no longer exists**; exercise the running backend instead.

### Packaging

Build/packaging scripts (`build.bat`, `build.spec`, `update_release.bat`, `installer.iss`) are **not in the working tree** — they survive only under `backups/backup_*/` history snapshots. `DEVELOPMENT.md` no longer documents packaging.

## Project Architecture

### Directory Structure

```
├── main.py                 # CLI application entry point
├── api/main.py             # FastAPI web backend (~3380 lines, 61 routes)
├── config.py               # Centralized configuration
├── dd_analysis.py          # Batch double-dummy analysis (DirectDDS calc_dd_table, 20 combos)
├── bridge/                 # Core bridge logic
│   ├── dealer.py           # Hand generation, HCP, distribution, DealMode
│   ├── bidding.py          # Bidding sequence parsing, keyword extraction
│   ├── bidding_service.py  # AI bidding service (main/fallback switching, retries)
│   ├── play_types.py       # Card, Trick, Contract, PlayState dataclasses
│   ├── play_engine.py      # Card play state machine (rules, undo)
│   ├── play_service.py     # AI play service (engine dispatch + finesse layer) (~3150 lines)
│   ├── play_strategies.py  # Lead/signal scheme registry — NOT wired into the system
│   ├── deep_finesse.py     # Deep Finesse external exe integration
│   ├── output_format.py    # Graphical / compact / DF output generation
│   └── mcts/               # Search engines and sampling
│       ├── __init__.py      # Exports only `DDSearch`
│       ├── dd_search.py     # Monte Carlo + DirectDDS, endgame enumeration
│       ├── alpha_mu.py      # αμ Pareto search engine
│       ├── direct_dds.py    # ctypes direct DDS C library wrapper
│       ├── sampler.py       # DealSampler: uniform sampling + level-based validation
│       ├── constraints.py   # BidConstraint validation (L0-L3 levels)
│       ├── bid_constraint_library.py  # DEPRECATED (v1.79) — research asset, not imported
│       ├── bit_hands.py     # Bit-level hand representation for DDS
│       ├── belief.py        # Utilities: collect_voids(), collect_signal_evidence()
│       ├── signals.py       # Defense signal models (attitude / count / suit preference)
│       ├── llm_validator.py # LLM play validation layer (9 rule checks)
│       └── state_utils.py   # Shared utilities
├── knowledge/
│   ├── loader.py           # JF document parsing (split on >=2 blank paragraphs) + tree retrieval
│   └── xr_retriever.py     # 新睿 (XR) retriever over scripts/xr_data/md_tables.json
├── llm/
│   ├── prompts.py          # Shared-template system / fallback / human / play prompts (~790 lines)
│   ├── xr_prompts.py       # XR prompts, built from the same shared templates
│   ├── deepseek_client.py  # DeepSeek API via OpenAI SDK
│   └── doubao_client.py    # Doubao Vision / Seed client
├── utils/
│   ├── history.py          # JSON-based bidding history storage
│   └── screenshot.py       # Screen capture (subprocess + PIL)
└── web/                    # React frontend (React 19 + Vite + MUI)
    └── src/
        ├── App.jsx         # Main app (~3770 lines)
        ├── components/     # 14 components + features/ layout/ mobile/ play/ ui/ subdirs
        ├── context/        # 4 providers (Game, Play, Bidding, AIProgress)
        ├── hooks/          # 7 custom hooks
        ├── services/       # API service layer (api.js)
        ├── theme/          # Theme system (index.js only)
        ├── layouts/  store/  styles/  constants/  utils/
```

> **`bridge/play_strategies.py`** defines `LeadScheme` / `SignalScheme` plus `lead_scheme()`, `signal_scheme()` and `register_*()`. **Nothing outside the file references it** — its only coupling is the unused `config.LEAD_SIGNAL_SCHEME` constant. Treat it as an un-wired reserved module (a v1.66 deliverable), not a live mechanism, and do not document it as active.

### Core Modules

- **`bridge/dealer.py`**: `BridgeDealer`, `Hand` (HCP, distribution), `DealMode` enum (**自由发牌 / 南北进局 / 南北满贯** — deal *strength* modes, not input sources), manual input parsing, `Position` enum.
- **`bridge/bidding.py`**: `extract_retrieval_keyword()` — maps a sequence to a JF keyword; structural-convention judgement; partner-position logic; consecutive-pass detection.
- **`bridge/bidding_service.py`**: `BiddingService` — keyword extraction, JF/XR retrieval, main/fallback switching, bid-meaning accumulation, compliance retries. `MAIN_PROMPT_MAX_RETRIES = 2` / `FALLBACK_PROMPT_MAX_RETRIES = 1` are defined **here**, not in `config.py`.
- **`knowledge/loader.py`**: `JFLoader` loads the docx and splits it on **≥2 consecutive empty paragraphs** (not on headings); `JFRetriever` matches keywords, builds trees from `│----` indentation, and `navigate_tree_by_bids()` handles preprocessing.
- **`bridge/play_engine.py`**: `PlayEngine` — phases `lead` / `dummy_reveal` / `playing` / `complete`; follow-suit rules; per-card and recursive per-trick undo.
- **`bridge/play_service.py`**: `PlayService` — AI play logic. Dispatch in `get_ai_play(use_reasoning, use_dd, use_perfect, use_alphamu, dd_samples, dd_scoring_mode, amu_worlds, amu_m)`: `use_perfect` → `use_dd` → `use_alphamu` → LLM (fall-through, **no flag**). Default engine is `dd`. Also hosts the finesse-intervention layer and bid-constraint parsing/merging.
- **`bridge/mcts/dd_search.py`**: `DDSearch` — Monte Carlo + DirectDDS. `search()` (MC; supports `perspective` / `actual_turn` / `preset_worlds`), `search_perfect()`, endgame enumeration. Candidate comparison is a **plain single-pass decision-value comparison** (declarer takes the higher, defenders the lower) — **no small-card preference and no significance threshold**; only `make_rate` mode blends `scoring_val*10000 + avg_tricks` as a tiebreak. Equivalence = exact per-world `scores` equality; when the make-rate leader and the trick leader disagree, `DD_MAJORITY_VOTES` (default 1 = off) triggers majority voting.
- **`bridge/mcts/alpha_mu.py`**: `AlphaMuSearch` — Pareto search (Cazenave & Ventos). `OutcomeVector` / `ParetoFront`, iterative deepening `range(1, M+1)`, transposition table (key excludes M), bound reuse, root cut, plus the 2021-paper optimizations — **6 of them**: Cut on Win, Maintaining Useful Worlds, World Cuts, Deep Alpha Cut, Empty Entry, Leaf Parallelization. `_time_up()` must stay enabled.
- **`bridge/mcts/sampler.py`**: `DealSampler` — uniform sampling with level-based constraint validation. `_sample_uniform()` is a **module-level function**; `DealSampler._sample_one` runs the chain L0 (MH repair) → L1 (master-soft) → L2 (relaxed, 50 retries) → L3 (voids only, 20) → L4 (least-violating).
- **`bridge/mcts/constraints.py`**: `BidConstraint` dataclass; `inference_source` is a **diagnostic label only** — source grading (`is_hard_source` / `is_ignored_source` / `filter_hard_constraints`) and `compute_sample_violation_score()` were **deleted in v1.79**, and all constraints are validated uniformly through `validate_hard()` / `validate_relaxed()` / `validate_voids_only()`. `suit_controls` / `min_keycards` are extracted and merged but **skipped** in `_check_constraint` (deferred until defense play is studied).
- **`bridge/mcts/direct_dds.py`**: ctypes DDS wrapper — `solve_all_boards_raw()` / `solve_all_boards_bits()` / `calc_dd_table()`, batching ≤200 boards, all solves serialized behind a lock. `_load_dll()` locates `dds.dll` via `import endplay._dds`, so **endplay is a runtime dependency of the play engines**, despite the module docstring's "bypasses endplay" phrasing (it bypasses endplay's PBN/Deal conversion, not the DLL lookup).
- **`bridge/mcts/llm_validator.py`**: rule-based validation with **9 checks** (legality, discard protection, don't ruff partner's winner, 2nd / 3rd / 4th hand, lead, cheapest winner, cheapest sufficient trump). Only `critical` / `error` severities are corrected, falling back to `validation.suggested_card` → `suggest_rule_based_play()`; `warning` keeps the LLM's choice. (`_select_best_card` is a separate LLM-unavailable path.)
- **`bridge/mcts/signals.py`**: `collect_all_signals()`, `format_partner_signals_for_prompt()` — attitude / count / suit-preference evidence for LLM defense prompts.
- **`dd_analysis.py`**: `analyze_all_contracts()` — 4 declarers × 5 strains = 20 combos via `calc_dd_table`, formatted as the "小房子" table.
- **`llm/prompts.py`**: all prompt templates. The main / fallback / human prompts are generated from shared `_SHARED_*` templates through `_make_prompt(template, system_tag, deal_system_block, no_valid_bid)`, parameterized for JF vs 新睿 (XR).
- **`llm/deepseek_client.py`**: schemas — `BIDDING_SCHEMA` **6** fields, `BIDDING_FALLBACK_SCHEMA` **13** fields, `HUMAN_BID_SCHEMA` **5** fields, `PLAY_SCHEMA` 4 fields.

### Web Architecture

- **Backend** (FastAPI, `api/main.py`, ~3380 lines, **61 routes**): game setup (`/api/deal`, `/api/custom-deal`, `/api/bm-deal`, `/api/image-deal`, `/api/trigger-screenshot`, `/api/single-hand-image`, `/api/read-clipboard`, `/api/read-hand-clipboard`, `/api/bidding-image`, `/api/read-bidding-clipboard`, `/api/diag-clipboard`), bidding (`/api/bid`, `/api/bid-async`, `/api/tasks/{id}`, `/api/tasks/{id}/cancel`, `/api/human-bid`, `/api/analyze`, `/api/constraints`, `/api/constraints/parse`, `/api/reload-jf`), output / analysis (`/api/output-formats`, `/api/analyze-contract`, `/api/double-dummy`), play (`/api/play/init`, `/api/play/card`, `/api/play/ai-play`, `/api/play/ai-play-async`, `/api/play/undo`, `/api/play/set-hand`, `/api/play/update-roles`, `/api/play/state`, `/api/play/dd-hints`, `/api/play/dd-hints-review`), play tuning (`/api/play/particle-settings`, `/api/play/dd-world-filter`, `/api/play/dd-finesse`, `/api/play/dd-finesse-delta`, `/api/play/dd-constraints`), records (`/api/records/index`, `/api/records/full/{id}`, `/api/records/backup`, `/api/records/upsert`, `/api/records/export`, `/api/records/delete`, `/api/records/note`), config (`/api/fallback-model`, `/api/ai-provider`, `/api/vision-provider`, `/api/time-budgets`, `/api/health`).
  This list is a guide, not exhaustive — **`api/main.py` is the source of truth** for routes.
  There is **no** `/api/screenshot-deal` (it is `/api/trigger-screenshot`) and **no** `/api/play/config`.
- **Frontend** (React 19 + Vite + MUI, `web/`): 14 components in `src/components/` plus `features/`, `layout/`, `mobile/`, `play/`, `ui/` subdirs; 7 hooks in `src/hooks/`; 4 context providers (`GameContext`, `PlayContext`, `BiddingContext`, `AIProgressContext`); theme in `src/theme/index.js` (there is **no** `theme/colorSchemes.js`); API calls centralized in `src/services/api.js`; `ErrorBoundary.jsx`; eslint via `npm run lint`.

### Key Data Structures

- `Hand`: HCP, distribution string, display string.
- `Position`: Enum (North / East / South / West → 北 / 东 / 南 / 西).
- `DealMode`: Enum (`自由发牌`, `南北进局`, `南北满贯`).
- `BiddingGame`: main CLI state machine (hands, sequence, dealer, mode, AI clients).
- `BiddingService`: LLM calls, fallback switching, bid meanings.
- `Card`: suit + rank, with `rank_value` / `suit_order`.
- `Contract`: level, suit, declarer, doubled / redoubled, `tricks_needed`.
- `Trick`: cards, leader, trump, `winner()`, AI metadata, **`dd_hints`**.
- `PlayState`: hands, contract, tricks, `current_player`, phase, declarer / defender trick counts, **`finesse_flow`**, **`finesse_flow_ends`**. Finesse also uses dynamically attached attributes (`finesse_flow_extra`, `finesse_windows`) which are **not** declared fields.
- `PlayPhase`: Enum (lead / dummy_reveal / playing / complete).

### Bidding Flow

1. **Deal**: random / manual / screenshot / image / BM2000 import / Deep Finesse input.
2. **Bidding loop**: for each position — extract keyword → retrieve JF/XR content → preprocess subsequent bids → call AI or human.
3. **AI decision**: main prompt (structural conventions) or fallback prompt. Fallback triggers when preprocessing returns empty or the main prompt outputs "JF无合格叫品".
4. **End**: three consecutive passes.
5. **Output**: graphical / compact / Deep Finesse formats.

### Card Play Flow

1. **Init**: `PlayService.initialize()` builds `PlayState` from the contract and hands.
2. **Lead**: opening lead from declarer's left-hand opponent.
3. **Dummy reveal**: after the opening lead.
4. **Playing**: follow-suit enforced. AI decisions come from `get_ai_play()` (4 engines).
5. **Finesse intervention**: after the engine returns candidates, a rule layer (`_intervene`, three gates: 段1 稳成 top1 make ≥ 1.0 → 段2 无损清将 `_clear_trump_lead`（仅有将定约，成约率口径）→ 段3 `_finesse_lead` 飞牌探针; the 9砸 `_garrison_*` branch was removed 2026-09-22) may rewrite the chosen card. Structure recognition is a deterministic predicate (`_probe_finesse_ok`: there exists a card G with `obj > G > every defender card except obj`); the DD probe's Δ — a **made-contract-rate difference** with threshold `FINESSE_PROBE_DELTA = 0.10` — is an entry ticket and sort key, not the sole gate. The cross-trick continuation state machine (removed v1.77) and the "顶张方" (top-honor-holder) concept are **gone**; `finesse_flow` registration now lives within a single trick. The acceptance-side rule (v2.16): step 1 `b_押注 ≥ FINESSE_COMMIT_ALIVE_PCT = 0.50` **and** ≥ the non-bet bucket → defer to the engine; otherwise step 2 ratio `flyer/top_alt ≥ FINESSE_RATIO = 0.75` keeps the finesse. Since v2.17, after the general launch gate (action/engine-top ratio ≥ `FINESSE_NEC_RATIO = 0.85`) passes, `_safe_cash_action` may cash a safe top honor in a **non-finesse suit** (engine top-1 is an A, or a K with partner holding the suit's A — the suit's A is unique, so the enemy has no A and the K wins in NT) and **postpone the finesse one trick** without registering `finesse_flow`; the next trick re-verifies the finesse structure naturally (only the engine top-1 counts — a non-top A/K never triggers the cash).
   → **Branch-by-branch flowchart: `docs/飞牌介入管线图解.md`** (current-state diagram; run `python tests/test_finesse_doc_sync.py` after changing finesse code). Historical rationale: `docs/飞牌系统演化全程_20260830-20260920.md`. Current rule text: `docs/飞牌现行口径_接应判据与Δ门票_20260920.md`. Code is always the source of truth.
6. **Undo**: per-card, recursively across completed tricks.
7. **Complete**: after 13 tricks the result is computed.

## AI Integration Details

### Retrieval Keyword Extraction

- Sequences are stored as `(S)1H-(W)pass-(N)2C-`.
- `extract_retrieval_keyword()` in `bridge/bidding.py` keys off sequence length, position and deal system.
- **Structural conventions** (main prompt): opening bids, two-bid keywords (`1D-1H`), third/fourth-seat 1-major openings.
- **Non-structural** (fallback): everything else, including section numbers such as `12.3.x`.
- Specialized extraction handles 1NT / 1C / 1D / 1-major openings after intervention (double, overcalls, multi-Landy) based on `deal_system`.

### Tree-Structured Retrieval and Preprocessing

- `parse_content_to_tree()` builds trees from `│----` indentation.
- `navigate_tree_by_bids()` navigates by bidding sequence, auto-skipping opening root nodes.
- Multi-bid lines with `/` are decomposed (e.g. `2S/3C/D/H`); single letters (C/D/H/S) are inferred as 3-level bids.
- Empty preprocessing falls back to the "成局与满贯" keyword.

### Prompt System

- **Main Prompt** (`BIDDING_SYSTEM_PROMPT`): structural conventions, **6 output fields**; must output "JF无合格叫品" when nothing qualifies.
- **Fallback Prompt** (`BIDDING_FALLBACK_PROMPT`): **13 output fields** (adds fit-suit count, shape points, game/slam judgement, stoppers, cue-bid controls, key cards). Always returns a bid.
- **Human Prompt** (`HUMAN_BID_PROMPT`): context for human players, **5 fields**.
- **Play Prompts**: `PLAY_DECLARER_PROMPT`, `PLAY_DEFENDER_PROMPT`, `PLAY_COMMON_RULES`, `PLAY_COMMON_SITUATION`.
- All prompts forbid exposing actual hand information (HCP, distribution, specific cards).

### AI Client

- `DeepSeekClient` in `llm/deepseek_client.py`: OpenAI SDK with JSON schema validation.
- Dual provider: DeepSeek (`deepseek-flash`) or Doubao Seed.
- Separate models for main and fallback prompts, each switchable to a reasoning variant (`::reasoning` suffix).
- Temperature 0.2 (main) / 0.5 (fallback).
- Play-side `thinking=True` comes from the **LLM engine** plus a `::reasoning` model selection — the old αμ+LLM "思考模式" engine is retired.

### Play Engine Configuration

- `DEFAULT_PLAY_ENGINE = "dd"` — options `"llm" | "dd" | "perfect" | "alphamu"`. **No** `mcts` / `tiered` / `dd_alphamu_llm`.
- DD: `DD_NUM_SAMPLES` 1000 (2026-09-23 由 200 提升：探针 Δ 门槛稳定化), `DD_MIN_SAMPLES` 15, `DD_TIME_LIMIT` 30.0, `DD_SCORING_MODE = "make_rate"` (default since 2026-09-20; `"imp"` / `"avg_tricks"` still selectable), `DD_KEEP_SURE_WIN/CRITICAL/SURE_LOSE`, `DD_MAJORITY_VOTES = 1`, `DD_USE_CONSTRAINTS = True`, `DD_ENDGAME_CARD_THRESHOLD` 4.
- αμ: `ALPHA_MU_ENABLE` True, `ALPHA_MU_ENDGAME_CARDS` 8, `ALPHA_MU_NUM_WORLDS` 20, `ALPHA_MU_M` 2 (panel-adjustable 1–3, **not** reduced by card count), `ALPHA_MU_TIME_LIMIT` 60.0.
- API validation bounds: `DD_PARTICLES_MIN/MAX` 100/2000, `ALPHA_MU_WORLDS_MIN/MAX` **10/100**.
- Finesse: `FINESSE_DEFER_ENABLE`, `DD_INTERVENE_ENABLE` (DD 介入总开关：稳成→无损清将→飞牌探针→多数投票), `FINESSE_RATIO` 0.75, `FINESSE_PROBE_DELTA` 0.10, `FINESSE_COMMIT_ALIVE_PCT` 0.50 (2026-09-25: 接应退让判据改两步——第一步"≥0.50 且 ≥非押注桶"→退让；不满足→第二步 flyer/top_alt 0.75 比值，≥0.75 强制。删 `FINESSE_COMMIT_DIE_PCT` 0.05 强制分支).
- Launch gate / 稳成线: `FINESSE_NEC_MAKE` 0.50, `FINESSE_NEC_MIN_RATIO` 0.50, `FINESSE_NEC_RATIO` 0.85 (v2.13: 门控分子改**动作牌全样本做成率**，阈值由 0.70 同步收紧——"要不要飞"看全局期望，押桶成只用于启动后的路线排序/接应), and **`FINESSE_NEC_MAKE_HIGH` 1.00** — the 稳成线 is evaluated by `_top1_make()`, i.e. the **engine top-1 candidate's** make rate (changed 2026-09-20 from "max over all candidates" at 0.95; 2026-09-22 0.85→1.00, only a guaranteed make shuts the intervention down). At/above it the whole intervention layer (无损清将/飞牌) defers to the engine.
- `LEAD_SIGNAL_SCHEME = "standard"` — consumed only by the un-wired `play_strategies.py`.
- **Removed constants** (do not reference): `MCTS_ITERATIONS`, `MCTS_TIME_LIMIT`, `MCTS_EXPLORATION_CONSTANT`, `MCTS_SEARCH_MODE`, `MCTS_PARTICLES_MIN/MAX`, `ROLLOUT_GREEDY_PROB`, `DD_MAXIMIN_ENABLE`, `TIERED_*`, `FINESSE_COMMIT_DIE_PCT` (2026-09-25 删).

### Double Dummy Analysis

- **Batch** (`dd_analysis.py`): all 20 declarer-strain combos via `direct_dds.calc_dd_table`. Web: `POST /api/double-dummy`. CLI: 主菜单 5 → 2.
- **Deep Finesse** (`bridge/deep_finesse.py`): external exe integration; the web "检验定约" button focuses the DF window.
- The former `endplay_integration.py` **no longer exists** — do not reference it.

## Important Conventions

- **Bidding sequence format**: `(S)1H-(W)pass-(N)2C-`.
- **Bid priority**: at the same level, S > H > D > C; NT outranks S at the same level.
- **Partner consecutive pass**: once both partners have passed consecutively after the first substantive bid, they auto-pass (no AI calls).
- **Terminology**: "发牌人" (dealer) for the first bidder; "庄家" (declarer) for the final contract display.
- **Config**: centralized in `config.py` — except the two bidding retry constants, which live in `bridge/bidding_service.py`.
- **Output formats**: generated programmatically, without LLM calls.

## Code Style

- Chinese for user-facing strings and comments; English for technical identifiers, class names and functions.
- Python type hints and dataclasses where appropriate; module-level constants in UPPERCASE.
- Follow the patterns in `bridge/dealer.py` and `bridge/bidding.py` for new code.

## References

- `AGENTS.md` — companion file: critical gotchas and non-obvious behaviours.
- `DEVELOPMENT.md` — current architecture / mechanism documentation plus per-version **summaries**.
- `DEVELOPMENT_HISTORY.md` — archived historical development documentation.
- `CHANGELOG.md` — the authoritative per-version narrative (background, lessons, tests). **Process detail lives here, not in `DEVELOPMENT.md`.**
- `docs/开发文档整理_发现清单_20260920.md` — documentation-drift audit: what was stale, why, and the cleanup record.
- `.env.example` — environment template.
