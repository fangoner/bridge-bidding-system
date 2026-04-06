---
name: bridge-bidding-recorder
description: "Record bridge bidding cases after discussion. Manually activate when user wants to save a bidding scenario, error correction, or strategic lesson. AI should suggest using this skill after meaningful bidding discussions."
description_zh: "桥牌叫牌案例记录器。讨论结束后手动激活，用于保存叫牌案例、错误纠正或策略教训。AI可在有价值的叫牌讨论后主动建议使用。"
description_en: "Bridge bidding case recorder. Manually activate after discussion to save bidding cases, error corrections, or strategic lessons. AI should suggest using this skill after meaningful bidding discussions."
---

# Bridge Bidding Recorder

## Overview

This skill enables systematic recording of bridge bidding discussions. When users analyze specific hands, review bidding sequences, or correct bidding decisions, this skill extracts key information and stores structured bidding cases in the project's `bidding-cases/` directory.

The recorded cases serve as a growing knowledge base of bidding scenarios, lessons learned, and strategic insights that can later be utilized to improve LLM bidding performance.

## When to Use This Skill

**手动激活模式**：此skill不会自动触发，需要用户明确要求或AI建议后由用户确认。

**AI建议时机**：在以下讨论结束后，AI应主动询问是否需要记录案例：

- **Hand analysis**: Discussion of specific card distributions and point counts
- **Bidding review**: Reviewing a bidding sequence and evaluating decisions
- **Error correction**: Identifying and correcting incorrect LLM bidding calls
- **Strategy discussion**: Explaining why a particular bid is correct or incorrect
- **Pattern recognition**: Discussing recurring bidding situations or conventions

**建议话术示例**：
- "这个叫牌案例很有价值，需要记录到案例库吗？"
- "要我把这个叫牌错误记录下来吗？"
- "这个策略讨论值得保存，是否需要记录案例？"

## Core Capabilities

### 1. Extract Bidding Case Information

From bidding discussions, extract:

- **Hand details**: Four-suit distribution and high card points (HCP)
- **Bidding sequence**: Complete auction from dealer to current position
- **Position context**: Dealer, vulnerability, partnership agreements
- **LLM decision**: What the AI bid in this situation
- **Correct decision**: What should have been bid (from discussion)
- **Reasoning**: Why the correction is needed, strategic explanation
- **Tags**: Categories for future retrieval (e.g., "1NT opening", "slam bidding", "competitive auction")

### 2. Store Structured Cases

Save extracted cases as JSON files in `bidding-cases/YYYY-MM-DD/case-NNN.json`:

```json
{
  "id": "case-001",
  "date": "2026-03-25",
  "timestamp": "2026-03-25T14:30:00",
  "hand": {
    "spades": "AKxx",
    "hearts": "Qx",
    "diamonds": "Jxxx",
    "clubs": "xxx",
    "hcp": 12
  },
  "position": {
    "dealer": "North",
    "vulnerability": "None",
    "seat": "South"
  },
  "bidding_sequence": ["1NT", "2♣", "2♦", "3NT"],
  "llm_bid": "2NT",
  "correct_bid": "3NT",
  "discussion_summary": "Responder with 12 HCP should bid 3NT directly after Stayman sequence, not invite with 2NT.",
  "discussion_content": "Detailed analysis: After 1NT-2♣-2♦, 2NT shows weakness (8-9 HCP). With game-going values (10-14 HCP), responder should bid 3NT directly to end the auction. The hand ♠AKxx ♥Qx ♦Jxxx ♣xxx has 12 HCP with balanced shape, well within the game-going range.",
  "tags": ["1NT opening", "Stayman", "game invitation", "no trump"],
  "convention": "JF",
  "source": "user discussion"
}
```

### 3. Maintain Case Index

Keep `bidding-cases/cases-index.json` updated with metadata for all cases:

```json
{
  "version": "1.0",
  "total_cases": 15,
  "last_updated": "2026-03-25T22:00:00",
  "cases": [
    {
      "id": "case-001",
      "date": "2026-03-25",
      "tags": ["1NT opening", "Stayman"],
      "brief": "Game invitation after 1NT-2♣-2♦"
    }
  ],
  "tag_statistics": {
    "1NT opening": 3,
    "Stayman": 2
  }
}
```

### 4. Generate Human-Readable Summaries

Optionally create Markdown summaries in `bidding-cases/summaries/` for easy review:

```markdown
# Bidding Cases - 2026-03-25

## Case 001: Game Invitation After Stayman

**Hand**: ♠AKxx ♥Qx ♦Jxxx ♣xxx (12 HCP)
**Auction**: 1NT - 2♣ - 2♦ - ?
**LLM Bid**: 2NT
**Correct Bid**: 3NT

**Lesson**: With 10+ HCP and balanced shape after Stayman sequence, 
bid game directly rather than inviting.
```

## Workflow

### Step 1: Identify Bidding Discussion

Recognize when conversation contains:
- Specific hand descriptions (suit distributions, HCP counts)
- Bidding sequences with card symbols (♠♥♦♣)
- Evaluations of bidding decisions ("should have bid...", "correct bid is...")
- Strategic explanations of bidding choices

### Step 2: Extract Case Information

Parse the discussion to identify:
1. The hand being discussed (if shown)
2. The bidding sequence
3. What was bid vs. what should have been bid
4. The reasoning behind the correction

If information is incomplete, ask the user for clarification:
- "What's the complete hand distribution?"
- "What was the vulnerability?"
- "What was the final contract?"

### Step 3: Create Case File

1. Generate unique case ID (incremental: case-001, case-002...)
2. Create directory `bidding-cases/YYYY-MM-DD/` if not exists
3. Write JSON case file
4. Update `cases-index.json`

### Step 4: Confirm Recording

Inform the user:
- "Recorded as case-001 in bidding-cases/2026-03-25/"
- Brief summary of what was captured
- Ask if any corrections needed

## Case Storage Location

All cases stored in project root:
```
D:\Bridge Card\Bidding System\
├── bidding-cases/
│   ├── 2026-03-25/
│   │   ├── case-001.json
│   │   └── case-002.json
│   ├── cases-index.json
│   └── summaries/
│       └── 2026-03-25.md
```

## Tagging Guidelines

Use consistent tags for future retrieval. See `references/tag_taxonomy.md` for complete taxonomy.

### Primary Error Type Tags (Required for Error Cases)

Every error case must have **exactly one** primary error type:

| Tag | Chinese | Description |
|-----|---------|-------------|
| `overbid` | 叫过头 | Bid too aggressively |
| `underbid` | 叫得保守 | Bid too conservatively |
| `convention-error` | 约定理解错误 | Misunderstood convention |
| `rule-violation` | 规则违反 | Violated bidding rules |
| `calculation-error` | 计算错误 | Counting/arithmetic error |
| `sequence-error` | 流程顺序错误 | Wrong order of operations |
| `option-missing` | 叫品遗漏 | Failed to consider valid option |

### Context Tags (Optional)

**Opening Type**: `1C-opening`, `1D-opening`, `1H-opening`, `1S-opening`, `1NT-opening`

**Contract Level**: `partscore`, `game`, `slam`, `grand-slam`

**Bidding Phase**: `opening`, `response`, `rebid`, `competitive`, `balancing`

**Conventions**: `Stayman`, `Jacoby-transfer`, `RKCB`, `Blackwood`, `cue-bid`, `splinter`

**Hand Pattern**: `balanced`, `single-suiter`, `two-suiter`, `void`, `singleton`

## Future Integration Notes

Currently this skill focuses on **recording only**. Future enhancements may include:

- Similar case retrieval based on hand patterns
- Automatic injection of relevant cases into LLM prompts
- Pattern analysis across multiple cases
- Rule extraction from accumulated cases

These features will be added when sufficient cases have been accumulated and their quality assessed.

## Resources

### scripts/

Contains utility scripts for case management:

- `record_case.py` - Create new bidding case from extracted data
- `update_index.py` - Maintain cases-index.json
- `search_cases.py` - Search cases by tags or patterns (future use)

### references/

- `case_schema.json` - JSON schema for case validation
- `tag_taxonomy.md` - Complete list of recommended tags
