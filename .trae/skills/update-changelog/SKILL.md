---
name: "update-changelog"
description: "Updates CHANGELOG.md and DEVELOPMENT.md after code changes. Invoke when user asks to record logs, update docs, or after completing code modifications."
---

# Update Changelog Skill

When invoked, this skill helps update the project documentation after code changes.

## Files to Update

1. **CHANGELOG.md** - Development log with date-based entries
2. **DEVELOPMENT.md** - Technical documentation with module details and version history

## Process

1. **Analyze the changes made**:
   - What files were modified
   - What functionality was added/changed/fixed
   - What was the problem and solution

2. **Update CHANGELOG.md**:
   - Add new entry under current date (or create new date section)
   - Include: Background, Changes, Modified files, Test results
   - Use concise bullet points

3. **Update DEVELOPMENT.md**:
   - Update relevant module sections if functionality changed
   - Update version history section
   - Add new version entry with changes summary

## Format Guidelines

### CHANGELOG.md Entry
```markdown
### <Feature Name>

**背景**: <Why this change was needed>

**改进**:
- <Change 1>
- <Change 2>

**修改文件**: <file1>, <file2>

**测试验证**: <Test result>
```

### DEVELOPMENT.md Version Entry
```markdown
### v1.XX (当前版本)
- **<Feature Name>**
  - <Detail 1>
  - <Detail 2>
```

## Example Usage

User: "记录日志"
User: "更新文档"
User: "修改完成了，更新日志"

## Notes

- Always read existing files first to maintain consistency
- Keep entries concise but informative
- Use Chinese for content (matching project style)
- Include version number increment if significant change
