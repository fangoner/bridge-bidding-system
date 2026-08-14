# AGENTS.md

This is a compact companion to `CLAUDE.md`. CLAUDE.md is the canonical reference with full architecture, data structures, and workflows. This file only documents things an agent would likely guess wrong or miss entirely.

## Quick start

```bash
pip install -r requirements.txt
cd web && npm install && cd ..
cp .env.example .env   # then edit .env with your API key
python main.py         # CLI
# or web:
# Terminal 1: uvicorn api.main:app --host 0.0.0.0 --port 8003
# Terminal 2: cd web && npm run dev
```

## Critical gotchas

### DeepSeek V4 thinking mode is disabled by default, enabled on demand
In `llm/deepseek_client.py`, `chat()` and `chat_json()` accept a `thinking: bool = False` parameter. When `thinking=False` (default), `extra_body={"thinking": {"type": "disabled"}}` is passed; when `thinking=True`, `{"thinking": {"type": "enabled"}}` is passed. All `chat_bidding`/`chat_bidding_fallback`/`chat_human_bid`/`chat_play` methods forward this parameter.

Default disabled is intentional: DeepSeek V4 with thinking=enabled is 3-5x slower (60-90s instead of 14-19s for bidding), which is undesirable for most calls. The exception is the αμ+LLM engine's "思考模式" (reasoning mode), which explicitly passes `thinking=True` for deeper play analysis. Never change the default to True.

### `endplay` is an optional dependency (v1.50: DD engine no longer depends on it)
`endplay_integration.py` still uses the `endplay` Python library for batch double-dummy analysis (CLI menu option 9). It is NOT in `requirements.txt`. Install separately: `pip install endplay`. Code that uses it should guard with try/except ImportError.

**v1.50 change**: `bridge/mcts/dd_search.py` (DD engine) has removed endplay dependency entirely, switching to `bridge/mcts/direct_dds.py` (ctypes direct DDS C library wrapper). `direct_dds.py` provides `solve_all_boards_raw()` and `solve_all_boards_bits()`, ~6x faster than the endplay path.

### Tests are standalone scripts, not pytest
Each file in `tests/` is run directly: `python tests/test_1c_1d.py`. No test runner, no pytest, no conftest.

### No Python lint/typecheck configured
There is no ruff, mypy, or pyright config. The web frontend has `npm run lint` (eslint). For Python changes, just verify code runs.

### Port conventions are fixed
- Backend: port 8003 (`api/main.py`)
- Frontend: port 5173 (Vite, configured with `strictPort: true` in `vite.config.js`)
- The frontend expects the backend at these exact ports.

### `.env` is mandatory, not optional
The app loads `config.py` which calls `load_dotenv(".env")` at module level. API keys come exclusively from `.env`. Without it, everything that calls AI will fail.

### Backend must NOT use `--reload` mode (v1.48+)
Start backend with `uvicorn api.main:app --host 0.0.0.0 --port 8003` (no `--reload`). The `--reload` mode may crash when multiple files are edited in succession (CHANGELOG.md, DEVELOPMENT.md, project_memory.md, etc.) due to frequent process restarts. This is a known issue with the mode, not a code bug.

### BeliefTracker is deprecated (v1.50)
`bridge/mcts/belief.py` no longer contains the `BeliefTracker` class. It only retains utility functions: `collect_voids()` (void detection) and `collect_signal_evidence()` (for LLM prompt injection). Hand sampling now uses uniform sampling with level-based constraint validation (`DealSampler._sample_uniform()` + L1/L2/L0 fallback chain).

## Configuration

`config.py` is the single source of truth. All MCTS, DD, model, temperature, and path settings are there. Do not create separate config files.

Key non-obvious settings:
- `DEFAULT_PLAY_ENGINE = "dd_alphamu_llm"` — options: `"llm"`, `"mcts"`, `"dd"`, `"perfect"`, `"alphamu"`, `"dd_alphamu_llm"`
- `MCTS_SEARCH_MODE = "mcts"` — options: `"mcts"` (tree+rollout) or `"dd"` (pure Monte Carlo + double-dummy)
- `DEFAULT_DEAL_SYSTEM = "2D/2H/2S：自然阻击"` — affects keyword extraction for opening bids
- `SHOW_FULL_LLM_OUTPUT = True`
- `MAIN_PROMPT_MAX_RETRIES = 2` / `FALLBACK_PROMPT_MAX_RETRIES = 1` — bidding compliance retry counts

## Bidding system gotchas

### Keyword extraction uses "next bidder" perspective
`extract_retrieval_keyword()` perspective is always the **next player to bid** in the sequence, NOT a fixed position (South or otherwise). Example: for `(东)2NT-(南)3S-`, the perspective is 北家 (the next to bid), so the keyword reflects 北家's decision context.

### 2NT opening after intervention returns "JF尚未实现"
After a 2NT opening, if the second seat does anything other than `pass`, the keyword is `JF尚未实现` (fallback to "成局与满贯"). The `2NT均型强牌` keyword ONLY applies when there is no intervention. Same for 1C/1D/1H/1S openings after high-level (3+) overcalls.

### Deprecated keywords
- `我方开叫1低花` — replaced by `JF尚未实现` for 1C/1D high-level overcall fallback
- `我方开叫1高花` — replaced by `JF尚未实现` for 1H/1S high-level overcall fallback

### Fallback does NOT persist across bidding rounds (P0-2 fix)
Each bidding round independently attempts the main prompt path before falling back. The code does NOT set `self.use_fallback = True` when the main prompt fails; this was a bug that caused subsequent rounds to skip the main prompt entirely.

### Main prompt leaves `jf_content` empty
In the main prompt path, `jf_content` is always set to empty string. The LLM relies solely on `subsequent_bids` (preprocessed bid tree). Injecting the original `jf_content` is redundant and may interfere with judgment.

## Card play system gotchas

### αμ engine: `success_rate` must follow the paper's three-state definition
`OutcomeVector` distinguishes three states: `useful` (1/0), `impossible` (treated as 1), `useless` (treated as 0). The `success_rate` is `sum(effective_value) / n` where n = all possible worlds (NOT just useful worlds). The `dominates` comparison must include all worlds with impossible treated as 1. The old implementation that skipped impossible worlds and used `useful_count` as denominator was wrong and caused alpha cut to trigger too easily.

### αμ engine: `_time_up()` must be enabled
The time limit check `(time.time() - self._start_time) > self.time_limit` must be active. Without it, the search can run indefinitely because the correct three-state logic makes alpha cut harder to trigger.

### αμ engine: Min node must update trick count before `solve_board`
When the Min player plays the 4th card completing a trick, `decl_tricks`/`def_tricks` must be updated BEFORE calling `solve_board`. Since `solve_board` evaluates remaining tricks (excluding the just-completed trick), `remaining_tricks = 13 - (decl_tricks + def_tricks)` would otherwise overcount by 1, causing αμ to systematically prefer losing tricks.

### DD engine: `deal.first` must use `actual_turn` (not `perspective`)
When the dummy leads a trick, `perspective` (rewritten declarer) differs from the actual player. `solve_board` needs the real leader position. The `actual_turn` parameter (= `state.current_player`) must be passed to downstream functions. Using `perspective` causes wrong hand evaluation (e.g., returns 7 instead of ~11 tricks).

### DD card selection: significance threshold uses paired difference
The threshold is `Z × std_diff / √N` where `std_diff` is the sample standard deviation of **paired differences** (same world, different candidate cards), NOT independent samples. The old formula assumed independent samples (`σ_diff = √2 × σ`), which inflated the threshold 2-4x and incorrectly classified real differences as ties.

### αμ 世界数滑块全局有效（v1.60）
`_alpha_mu_play` 优先读取 `self.alpha_mu_search.num_worlds`（设置面板配置值，仅在纯 αμ 引擎下修改，但对 DD-αμ-LLM 残局阶段同样全局生效），世界数上限随 base 成比例缩放（默认 20 时与原绝对上限 100/60/30/20 一致）。修改该函数时不要退回硬编码 `ALPHA_MU_NUM_WORLDS` 常量。

### DD 提示异步追加竞态防护（v1.60）
`api/main.py` 的 `_record_dd_hint_async` 在 `target_trick.dd_hints.append(hints)` 前检查 `len(dd_hints) >= len(cards)`，撤销后迟到 hint 会被丢弃，保持 hints 与牌张 1:1（前端按序号取 `dd_hints[cardIdx]`）。修改异步提示管线时保留该不变量。

### /api/bid 错误语义（v1.60）
LLM 超时/网络/配置错误返回 **502 + detail**（前端提示并停止自动叫牌），不再伪装成 200+pass；合规性重试耗尽的"暂停叫牌"标记保持 200（前端有专门处理路径）。不要改回静默 pass。

## Code conventions

- Chinese for user-facing strings and comments; English for technical identifiers, class names, functions
- Python type hints and dataclasses throughout
- Module-level constants in UPPERCASE
- Follow patterns in `bridge/dealer.py` and `bridge/bidding.py` for new code
- Bidding sequence format: `(S)1H-(W)pass-(N)2C-` (position prefix in parens + bid, hyphen-separated)
- Bid priority at same level: S > H > D > C, and NT outranks S at the same level (1NT > 1S)
- Suit rank order: NT > S > H > D > C (not S > H > D > C)

## File locations that matter

- `JF实战_标准自然 - Rev 3.2.docx` — must exist in project root; the JF convention document
- `bidding_history.json` — gitignored; generated at runtime
- `Deep Finesse 2014 v2/` — gitignored; optional external tool directory
- `bidding-cases/` — tracked in git; test/example bidding case records
- `DEVELOPMENT.md` — current development documentation
- `DEVELOPMENT_HISTORY.md` — archived historical development documentation
- `docs/` — **开发研究/分析/方案讨论类 Markdown 报告的固定存放目录**（如 `打牌窜牌诊断报告.md`、`改进打牌引擎讨论.md`、`流程流畅性审查报告.md`）。所有开发研究类、审查分析类、方案讨论类的报告一律放这里，不要放项目根目录；写作新报告前先检索 docs/ 现有内容，避免重复讨论已知问题
