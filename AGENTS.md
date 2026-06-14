# AGENTS.md

This is a compact companion to `CLAUDE.md`. CLAUDE.md is the canonical reference with full architecture, data structures, and workflows. This file only documents things an agent would likely guess wrong or miss entirely.

## Quick start

```bash
pip install -r requirements.txt
cd web && npm install && cd ..
cp .env.example .env   # then edit .env with your API key
python main.py         # CLI
# or web:
# Terminal 1: uvicorn api.main:app --host 0.0.0.0 --port 8003 --reload
# Terminal 2: cd web && npm run dev
```

## Critical gotchas

### DeepSeek V4 thinking mode MUST be disabled
In `llm/deepseek_client.py`, both `chat()` and `chat_json()` pass `extra_body={"thinking": {"type": "disabled"}}`. Without this, DeepSeek V4 defaults to thinking=enabled, making API calls 3-5x slower (60-90s instead of 14-19s for bidding). Never remove this.

### `endplay` is an optional dependency
`endplay_integration.py` and `bridge/mcts/dd_search.py` use the `endplay` Python library for double-dummy analysis. It is NOT in `requirements.txt`. Install separately: `pip install endplay`. Code that uses it should guard with try/except ImportError.

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

## Configuration

`config.py` is the single source of truth. All MCTS, DD, model, temperature, and path settings are there. Do not create separate config files.

Key non-obvious settings:
- `DEFAULT_PLAY_ENGINE = "llm"` — options: `"llm"`, `"mcts"`, `"dd"`, `"hybrid"`
- `MCTS_SEARCH_MODE = "mcts"` — options: `"mcts"` (tree+rollout) or `"dd"` (pure Monte Carlo + endplay solve_board)
- `DEFAULT_DEAL_SYSTEM = "2D/2H/2S：自然阻击"` — affects keyword extraction for opening bids
- `SHOW_FULL_LLM_OUTPUT = True`

## Code conventions

- Chinese for user-facing strings and comments; English for technical identifiers, class names, functions
- Python type hints and dataclasses throughout
- Module-level constants in UPPERCASE
- Follow patterns in `bridge/dealer.py` and `bridge/bidding.py` for new code
- Bidding sequence format: `(S)1H-(W)pass-(N)2C-` (position prefix in parens + bid, hyphen-separated)
- Bid priority at same level: S > H > D > C > NT

## File locations that matter

- `JF实战_标准自然 - Rev 3.2.docx` — must exist in project root; the JF convention document
- `bidding_history.json` — gitignored; generated at runtime
- `Deep Finesse 2014 v2/` — gitignored; optional external tool directory
- `bidding-cases/` — tracked in git; test/example bidding case records
