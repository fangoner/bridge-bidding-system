---
name: "project-onboarding"
description: "Provides comprehensive project overview for new model sessions. Invoke when switching models, starting fresh session, or user asks to introduce/explain the project."
---

# Project Onboarding Skill

When invoked, this skill provides a complete overview of the project for new model sessions.

## Project Summary

**桥牌叫牌练习系统** - A bridge bidding practice tool converted from Dify workflow to standalone application.

### Core Features
- Dual/Four-player bidding practice
- JF bidding convention system
- DeepSeek API for AI bidding decisions
- Deep Finesse integration for contract analysis

## Key Files to Read

### 1. Documentation (READ FIRST)
```
DEVELOPMENT.md  - Complete technical documentation
CHANGELOG.md    - Development history and changes
```

### 2. Core Modules
```
main.py              - Main entry point, menu system
config.py            - Configuration management
bridge/
  ├── dealer.py      - Card dealing and hand management
  ├── bidding.py     - Bidding sequence parsing, keyword extraction
  ├── deep_finesse.py - Deep Finesse integration
  └── output_format.py - Output formatting
knowledge/
  └── loader.py      - JF convention loading and retrieval
llm/
  ├── prompts.py     - System prompts for AI
  ├── deepseek_client.py - DeepSeek API client
  └── doubao_client.py   - Doubao vision API client
utils/
  ├── history.py     - History record management
  └── screenshot.py  - Screenshot functionality
```

### 3. Configuration
```
.env                 - API keys (not in repo)
.env.example         - API key template
```

## Architecture Overview

### Bidding Flow
```
1. Deal cards → bridge/dealer.py
2. Extract keyword from sequence → bridge/bidding.py:extract_retrieval_keyword()
3. Retrieve JF convention → knowledge/loader.py:retrieve_with_preprocess()
4. AI decides bid → main.py:ai_bid()
   ├── Structural convention → Main prompt with subsequent_bids
   └── Non-structural convention → Fallback prompt with full content
5. Format output → bridge/output_format.py
```

### Key Concepts

| Concept | Description |
|---------|-------------|
| `is_structural_convention` | True for: opening keywords, double-bid keywords (1D-1H), 第三四家开叫1H |
| `subsequent_bids` | Preprocessed bid options extracted from convention |
| `deal_system` | 2阶开叫方案: "自然阻击" or "多功能/麦德伯格" |
| Main prompt | Uses preprocessed subsequent_bids, strict JF matching |
| Fallback prompt | Uses full JF content, natural bidding logic |

### Convention Keyword Types

| Type | Example | is_structural |
|------|---------|---------------|
| Opening | 1H开叫, 1NT, 2C | True |
| Double-bid | 1D-1H, 1C-1D | True |
| 第三四家 | 第三四家开叫1H | True |
| Chapter | 12.3.4 Rubensohl | False |
| Other | 第二家争叫 | False |

## Current Version

Check DEVELOPMENT.md for latest version number and changes.

## Usage

User: "介绍一下项目"
User: "我切换了模型，帮我熟悉一下"
User: "项目概览"
User: "onboarding"

## Quick Start for New Model

1. Read DEVELOPMENT.md for full documentation
2. Read CHANGELOG.md for recent changes
3. Check main.py for entry point and flow
4. Review bridge/bidding.py for keyword extraction logic
5. Review knowledge/loader.py for convention retrieval

## Notes

- Primary language: Chinese (for user interaction and documentation)
- Code comments: Chinese
- Follow existing code style and patterns
- Always check existing implementations before adding new features
