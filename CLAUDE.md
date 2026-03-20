# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Overview

Bridge bidding practice system with AI integration. Supports two-player/four-player bidding practice using JF bidding conventions. Uses DeepSeek API for AI bidding decisions, Doubao Vision API for screenshot recognition, and Deep Finesse for contract analysis.

## Development Commands

### Running the CLI Application
```bash
python main.py
```
Main menu provides options to deal hands, configure settings, run bidding, analyze contracts, view history, and test bidding sequences.

### Running the Web API Backend
```bash
cd api
uvicorn main:app --host 127.0.0.1 --port 8003
```
Or use the convenience script:
```bash
start-web-service.bat
```
This starts both backend API (FastAPI) and frontend React app.

### Running the Web Frontend
First install dependencies:
```bash
cd web
npm install
```

Then start the development server:
```bash
npm run dev
```
Frontend runs on `http://localhost:5173` (Vite). Requires backend API on port 8003.

### Testing
The primary testing mechanism is the built-in `test_bidding_sequence` function accessible via menu option 7. This interactive test allows you to input bidding sequences and see keyword extraction, JF convention retrieval, and preprocessing results.

To run the test:
1. Start the application: `python main.py`
2. Choose menu option 7: "测试叫牌序列关键词和预处理"

For unit tests, many ad‑hoc test scripts are in the `tests/` directory. Run them individually, e.g.:
```bash
python tests/test_1c_1d.py
```

API tests can be run with `python test_api.py` (requires the backend API to be running).

### Using Claude Code with DeepSeek Configuration
The repository includes a batch script `claude-deepseek.bat` that configures Claude Code to use the DeepSeek API instead of the default Anthropic API. This is useful for development and testing with the same AI model used by the bidding system.

To use Claude Code with DeepSeek:
```bash
claude-deepseek.bat
```

The script sets the following environment variables:
- `ANTHROPIC_BASE_URL`: Points to DeepSeek API endpoint
- `ANTHROPIC_MODEL`: Set to `deepseek-chat`
- `API_TIMEOUT_MS`: Increased to 600000ms (10 minutes)

### Packaging
The project can be packaged with PyInstaller into a standalone Windows executable.
- **Quick build**: Double‑click `build.bat` or run `pyinstaller build.spec --clean`
- **Update release package**: Run `update_release.bat` (copies executable and required files to `release_桥牌叫牌练习/`)
- **Create installer**: Use Inno Setup with `installer.iss`

Detailed packaging notes are in `DEVELOPMENT.md`.

## Getting Started

### Prerequisites
- Python 3.x
- DeepSeek API key (optional, for AI bidding)
- Doubao Vision API key (optional, for screenshot recognition)
- Deep Finesse 2014 v2 executable (optional, for contract analysis)
- JF convention document (`JF实战_标准自然 - Rev 3.2.docx`) must be present in project root

### Installation
```bash
pip install openai python-dotenv python-docx pyautogui pyscreeze pillow mss
```

### Environment Setup
Create a `.env` file in the project root with the following variables:
```env
DEEPSEEK_API_KEY=your_deepseek_api_key
DEEPSEEK_BASE_URL=https://api.deepseek.com
DOUBAO_API_KEY=your_doubao_api_key
DOUBAO_BASE_URL=https://ark.cn-beijing.volces.com/api/v3
DOUBAO_VISION_ENDPOINT=your_vision_endpoint_id
```

## Project Architecture

### Core Modules
- **`bridge/dealer.py`**: Hand generation, HCP calculation, distribution formatting, manual input parsing.
- **`bridge/bidding.py`**: Bidding sequence parsing, partner position logic, retrieval keyword extraction.
- **`bridge/bidding_service.py`**: Bidding service wrapper that manages LLM calls, fallback prompt switching, and bid meanings accumulation.
- **`bridge/deep_finesse.py`**: Integration with Deep Finesse executable for contract analysis.
- **`bridge/output_format.py`**: Programmatic generation of graphical, compact, and Deep Finesse formatted outputs.
- **`knowledge/loader.py`**: JF convention document loading, segmentation, tree‑structured retrieval with preprocessing.
- **`llm/prompts.py`**: System, fallback, and human bid prompt templates.
- **`llm/deepseek_client.py`**: DeepSeek API client with JSON schema validation.
- **`llm/doubao_client.py`**: Doubao Vision API client for screenshot recognition.
- **`utils/history.py`**: JSON‑based storage of bidding history.
- **`utils/screenshot.py`**: MSS‑based screen capture and Edge window detection.

### Web Architecture
- **Frontend**: React 19 + Vite + Material‑UI (`web/`). Communicates with backend via `axios`. Features responsive design for mobile devices.
- **Backend**: FastAPI (`api/main.py`). Provides REST endpoints for game management (create, state, deal, bid, formats), bidding, analysis, and output formatting. Supports CORS for cross‑origin requests.
- **Integration**: The CLI (`main.py`) and web API share the same core modules (`bridge/`, `knowledge/`, `llm/`). The `BiddingService` class centralizes bidding logic for both interfaces.

### Key Data Structures
- `Hand`: HCP, distribution, display string.
- `Position`: Enum for North, East, South, West.
- `DealMode`: Enum for free, manual, screenshot, Deep Finesse input.
- `BiddingGame`: Main state machine holding hands, sequence, dealer, mode, AI clients, etc.
- `BiddingService`: Service wrapper that manages LLM calls, fallback prompt switching, and bid meanings accumulation.

### Flow
1. **Deal**: Random generation or manual input.
2. **Bidding Loop**: For each position, retrieve JF convention content, preprocess subsequent bids, call AI (or human) for decision.
3. **AI Decision**: Main prompt searches JF conventions; fallback prompt provides intelligent choices when no match.
4. **Output**: Generate graphical/compact/Deep Finesse formatted results.
5. **Analysis**: Optionally run Deep Finesse on the final contract.

### Configuration
`config.py` centralizes paths, API endpoints, output modes, and model choices. Modify constants there for project‑wide changes.

## AI Integration Details

### Retrieval Keyword Extraction
- Bidding sequences are stored as strings like `(S)1H-(W)pass-(N)2C-`.
- `extract_retrieval_keyword()` in `bridge/bidding.py` extracts keywords based on sequence length, position, and deal system.
- Keywords are matched against JF convention headings (first three lines of each segment).
- Structural conventions (opening bids, two‑bid keywords, third‑fourth seat openings) trigger the main prompt; otherwise the fallback prompt is used.
- **Specialized keyword extraction**:
  - **1NT opening after opponent intervention**: Distinguishes between natural preempts and multi‑Landy based on `deal_system` configuration. Maps to precise JF convention section 12.3.x.
  - **1C/1D opening after opponent interference**: Differentiates between opponent double, one‑level overall, two‑level overall, and higher‑level interference.
  - **1‑major opening after opponent interference**: Handles opponent double, two‑suited overall (2NT), known‑one‑suited overall, simple raise after opponent participation.
- **Structural convention judgment simplified**: Only three types are considered structural:
  1. Opening keywords (e.g., `1H开叫`, `1NT`, `2C`)
  2. Two‑bid keywords (e.g., `1D‑1H`, `1C‑1D`)
  3. Third‑fourth seat opening of 1‑major (e.g., `第三四家开叫1H`)
  All other keywords (including section numbers like `12.3.x`) are non‑structural and use the fallback prompt.

### Tree‑Structured Retrieval and Preprocessing
- `knowledge/loader.py` includes `parse_content_to_tree()` to convert convention segments into tree structures based on indentation patterns (`│----`).
- **Tree navigation**: `navigate_tree_by_bids()` navigates through the tree based on the bidding sequence, automatically handling root nodes (skipping opening bids).
- **Multi‑bid decomposition**: Lines containing "/" are automatically decomposed into multiple parallel bids (e.g., "2S/3C/D/H" → "2S", "3C", "3D", "3H").
- **Single‑letter bids**: Single letters (C, D, H, S) are automatically inferred as 3‑level bids.
- **Two‑bid keywords**: Root node is the first bid, child node is the second bid (e.g., `1D‑1H`).
- **Third‑fourth seat opening**: Root node is the opening bid (1H or 1S).
- `preprocess_jf_content()` extracts subsequent bids by navigating the tree to find the partner's last bid and collecting child nodes.
- Preprocessing results are injected into prompts via the `{subsequent_bids}` placeholder.
- **Empty preprocessing results**: When preprocessing returns empty, the system automatically tries the "成局与满贯" (game and slam) keyword as fallback.

### Prompt System
- **Main Prompt (`BIDDING_SYSTEM_PROMPT`)**: Used when JF conventions contain relevant content. Returns 12 output fields.
  - **AI permission restriction**: When both preprocessing results and partner suggestions are empty, must output "JF无合格叫品". Cannot choose a bid independently.
  - **Switch to fallback**: Two cases trigger fallback: 1) preprocessing returns empty, 2) main prompt outputs "JF无合格叫品".
- **Fallback Prompt (`BIDDING_FALLBACK_PROMPT`)**: Used when main prompt returns "JF无合格叫品". Provides intelligent bidding decisions with 19 output fields (adds fit suits, shape points, game judgment, etc.).
  - **Always returns valid bid**: Guarantees a bidding decision even when JF conventions provide no coverage.
- **Human Prompt (`HUMAN_BID_PROMPT`)**: Provides context for human players. Uses preprocessing results for structural conventions, full JF convention segments for descriptive conventions.
- **All prompts enforce rules against exposing actual hand information** (HCP, distribution, specific cards). Must only reference conventional ranges, never actual holdings.

### AI Client
- `DeepSeekClient` in `llm/deepseek_client.py` uses OpenAI SDK with JSON schema validation.
- Models: `deepseek-chat` (default) and `deepseek-reasoner` (optional).
- Temperature: 0.2 for main prompt, 0.5 for fallback prompt.

## Important Conventions
- Bidding sequences are stored as strings like `(S)1H-(W)pass-(N)2C-`.
- Retrieval keywords are extracted from the sequence and matched against JF convention headings.
- Structural conventions (opening bids, two‑bid keywords, third‑fourth seat openings) trigger the main prompt; otherwise the fallback prompt is used.
- The `output_format` module can generate three display formats without LLM calls.
- **Bid priority**: At the same level, higher‑ranking suits (S > H > D > C) take precedence over NT.
- **Partner consecutive pass logic**: In four‑player bidding, when partners have both passed consecutively after the first substantive bid, they automatically pass in subsequent rounds (no AI calls).
- **Contract verification**: The web interface includes a "检验定约" (verify contract) button that launches Deep Finesse and brings its window to the foreground for analysis.
- **Terminology correction**: "庄家" (dealer) is used for the first bidder; "庄家" (declarer) is reserved for the final contract display (the first player in the contract side to name the suit).
- **Bidding end conditions**: Three consecutive passes end the auction (including non‑participating sides in pair bidding).

## Code Style
- Uses Python type hints and dataclasses where appropriate.
- Module‑level constants are uppercase with underscores.
- Chinese is used in user‑facing strings, comments, and some variable names; English for technical identifiers.
- Follow the existing patterns in `bridge/dealer.py` and `bridge/bidding.py` for new code.

## References
- Detailed development notes: `DEVELOPMENT.md`
- Environment template: `.env.example`
- Version history: `CHANGELOG.md`