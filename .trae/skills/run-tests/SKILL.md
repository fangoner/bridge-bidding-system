---
name: "run-tests"
description: "Runs all test scripts in the tests directory and reports results. Invoke when user asks to run tests, verify changes, or check functionality."
---

# Run Tests Skill

When invoked, this skill runs all test scripts and reports the results.

## Test Directory

- `tests/` - Contains all test scripts
- Test files follow pattern: `test_*.py`

## Process

1. **Find all test files**:
   - List files in `tests/` directory
   - Identify `test_*.py` files

2. **Run each test**:
   - Execute with Python
   - Capture output and exit code

3. **Report results**:
   - Summary: passed/failed/total
   - Details for any failures

## Example Output

```
测试结果汇总
============

✅ test_1nt_opening.py - 通过
✅ test_keyword_extract.py - 通过
❌ test_deep_finesse.py - 失败
   错误: AssertionError on line 42

总计: 2/3 通过
```

## Usage

User: "运行测试"
User: "测试一下"
User: "验证修改是否正确"
User: "跑一下测试脚本"

## Notes

- Tests run in the project root directory
- Each test runs independently
- Report both success and failure cases
- Highlight any errors for debugging
