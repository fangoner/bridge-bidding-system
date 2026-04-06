# Bidding Case Tag Taxonomy

Standardized tags for categorizing bidding cases.

## Primary Tags: Error Types (Required for Error Cases)

Every error case must have exactly one primary error type tag:

| Tag | Chinese | Description | Example |
|-----|---------|-------------|---------|
| `overbid` | 叫过头 | Bid too aggressively for the hand strength | 13 points but bid game; jumped without sufficient strength |
| `underbid` | 叫得保守 | Bid too conservatively, missed opportunity | 6-5 shape but passed; missed game/slam |
| `convention-error` | 约定理解错误 | Misunderstood or misapplied a convention | RKCB response logic wrong; Stayman misuse |
| `rule-violation` | 规则违反 | Violated bidding rules | Bid lower than previous bid; illegal pass |
| `calculation-error` | 计算错误 | Arithmetic or counting error | Key cards miscounted; HCP miscounted |
| `sequence-error` | 流程顺序错误 | Wrong order of operations | Cue bid before confirming trump fit |
| `option-missing` | 叫品遗漏 | Failed to consider a valid bid option | Didn't consider double; missed transfer |

## Secondary Tags: Bidding Context (Optional)

### Opening Type

- `1C-opening` - One club opening
- `1D-opening` - One diamond opening
- `1H-opening` - One heart opening
- `1S-opening` - One spade opening
- `1NT-opening` - One no-trump opening
- `2C-opening` - Strong two clubs
- `2D/H/S-opening` - Weak two opening
- `2NT-opening` - Two no-trump opening (20-21)
- `preempt` - Preemptive opening (3+ level)

### Bidding Phase

- `opening` - Opening bid decision
- `response` - Response to opening
- `rebid` - Opener's or responder's rebid
- `competitive` - Competitive auction (both sides bidding)
- `balancing` - Balancing/protective position

### Contract Level

- `partscore` - Partscore contract (1-2 level)
- `game` - Game contract decision (3NT, 4M, 5m)
- `slam` - Slam investigation
- `grand-slam` - Grand slam investigation

### Conventions Used

- `Stayman` - Stayman convention
- `Jacoby-transfer` - Jacoby transfer
- `RKCB` - Roman Key Card Blackwood
- `Blackwood` - Standard Blackwood
- `cue-bid` - Cue bid (control showing)
- `splinter` - Splinter bid
- `negative-double` - Negative double
- `takeout-double` - Takeout double

### Hand Pattern

- `balanced` - Balanced hand (4333, 4432, 5332)
- `single-suiter` - Single long suit (6+ cards)
- `two-suiter` - Two long suits (5-5, 6-5, etc.)
- `three-suiter` - Three suits (4441, 5440)
- `void` - Hand contains a void
- `singleton` - Hand contains a singleton

## Tag Selection Guidelines

### Required Tags for Error Cases

1. **Exactly one** primary error type tag (from Error Types)
2. **At least one** context tag (opening type, phase, or level)

### Recommended Tag Combinations

```
Example 1: Overbid in slam bidding
Tags: ["overbid", "slam", "RKCB", "calculation-error"]

Example 2: Underbid with two-suiter
Tags: ["underbid", "two-suiter", "competitive", "1S-opening"]

Example 3: Convention error in response
Tags: ["convention-error", "response", "Stayman", "1NT-opening"]
```

### Tag Priority

When multiple errors exist, prioritize by impact:
1. `rule-violation` - Always tag if present (most severe)
2. `calculation-error` - If it directly caused the wrong bid
3. `convention-error` - If convention was misunderstood
4. `sequence-error` - If order of operations was wrong
5. `overbid` / `underbid` - The outcome of the error

## Statistics Categories

For tag_statistics in cases-index.json, count:
- Primary error types (overbid, underbid, convention-error, etc.)
- Contract levels (game, slam, partscore)
- Opening types (1H-opening, 1NT-opening, etc.)

## Migration Notes

Old tags mapped to new system:
- `wrong principle` → `convention-error` or `sequence-error`
- `pass too conservative` → `underbid`
- `wrong convention` → `convention-error`
- `point counting error` → `calculation-error`
- `historical`, `error` → Remove, use specific error type instead
