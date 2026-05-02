---
name: "analyze-performance"
description: "Analyzes DeepSeek API call performance for bidding and playing. Invoke when user asks to analyze performance, check response times, or review API logs."
---

# Analyze Performance

This skill analyzes the DeepSeek API call performance from the debug log file, producing statistics on response times, success/failure rates, and token usage for both bidding (叫牌) and playing (打牌) operations.

## Log File Location

The log file is at: `d:\Bridge Card\Bidding System\deepseek_debug.log`

## Log Format

Each API call generates two log lines:
1. Request line: `YYYY-MM-DD HH:MM:SS [DeepSeek] chat_json model=<model> thinking=<bool> max_tokens=<int> timeout=<float>s prompt_chars=<int>`
2. Response line: `YYYY-MM-DD HH:MM:SS [DeepSeek] OK in <float>s response_chars=<int> finish_reason=<str> reasoning_tokens=<int> total_tokens=<int>`
3. Retry line: `YYYY-MM-DD HH:MM:SS [DeepSeek] JSON mode retry after <int>s: <error>`
4. Failure line: `YYYY-MM-DD HH:MM:SS [DeepSeek] JSON mode failed after 1 retry: <error>` or `YYYY-MM-DD HH:MM:SS [DeepSeek] 各模式均失败: <error>`

## Classification Rules

CRITICAL: Use `max_tokens` to distinguish bidding from playing, NOT `prompt_chars`:

| max_tokens | thinking | Type | Reason |
|------------|----------|------|--------|
| 1024 | False | **打牌 (play)** | `chat_play` explicitly sets max_tokens=1024 for non-thinking |
| 2048 | False | **叫牌 (bid)** | `chat_bidding` uses default max_tokens=2048 for non-thinking |
| 8192 | True | **打牌 (play)** | `chat_play` explicitly sets max_tokens=8192 for thinking mode |
| 8192 | False | **叫牌 (bid)** | Edge case, same default as bidding |

The code reference in `llm/deepseek_client.py`:
- `chat_bidding()`: calls `chat_json()` without max_tokens → defaults to 8192(thinking)/2048(non-thinking)
- `chat_play()`: calls `chat_json()` with `max_tokens = 8192 if thinking else 1024`

## Analysis Script

Run the following Python script to generate the full analysis. Write it to a temporary file and execute with `python`:

```python
import re
from collections import defaultdict
from datetime import datetime

log_file = r"d:\Bridge Card\Bidding System\deepseek_debug.log"

with open(log_file, "r", encoding="utf-8") as f:
    lines = f.readlines()

entries = []
current = None

for line in lines:
    m = re.search(r'(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}).*chat_json model=(\S+) thinking=(\S+) max_tokens=(\d+) timeout=([\d.]+)s prompt_chars=(\d+)', line)
    if m:
        current = {
            "timestamp": m.group(1),
            "model": m.group(2),
            "thinking": m.group(3) == "True",
            "max_tokens": int(m.group(4)),
            "timeout": float(m.group(5)),
            "prompt_chars": int(m.group(6)),
            "duration": None,
            "response_chars": None,
            "finish_reason": None,
            "total_tokens": None,
            "reasoning_tokens": None,
            "success": False,
            "retry": False,
            "failed": False,
        }
        continue

    if current and "retry after" in line:
        current["retry"] = True
        continue

    if current and ("failed after" in line or "各模式均失败" in line):
        current["failed"] = True
        entries.append(current)
        current = None
        continue

    m2 = re.search(r'(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}).*OK in ([\d.]+)s response_chars=(\d+) finish_reason=(\S+) reasoning_tokens=(\d+) total_tokens=(\d+)', line)
    if m2 and current:
        current["duration"] = float(m2.group(2))
        current["response_chars"] = int(m2.group(3))
        current["finish_reason"] = m2.group(4)
        current["reasoning_tokens"] = int(m2.group(5))
        current["total_tokens"] = int(m2.group(6))
        current["success"] = True
        entries.append(current)
        current = None
        continue

for e in entries:
    if e["max_tokens"] == 1024:
        e["type"] = "play"
    elif e["max_tokens"] == 2048:
        e["type"] = "bid"
    elif e["max_tokens"] == 8192:
        if e["thinking"]:
            e["type"] = "play"
        else:
            e["type"] = "bid"
    else:
        e["type"] = "unknown"

def model_label(e):
    t = "思考" if e["thinking"] else "非思考"
    return f"{e['model'].replace('deepseek-v4-', '').upper()}({t})"

print("=" * 70)
print("总体统计")
print("=" * 70)
print(f"总请求数: {len(entries)}")
success = [e for e in entries if e["success"]]
failed = [e for e in entries if not e["success"]]
print(f"成功: {len(success)}, 失败/超时: {len(failed)}")
bid_success = [e for e in success if e["type"] == "bid"]
play_success = [e for e in success if e["type"] == "play"]
print(f"叫牌成功: {len(bid_success)}, 打牌成功: {len(play_success)}")

print()
print("=" * 70)
print("按模型+思考模式统计")
print("=" * 70)
by_group = defaultdict(list)
for e in entries:
    key = model_label(e)
    by_group[key].append(e)

for key in sorted(by_group.keys()):
    group = by_group[key]
    g_success = [e for e in group if e["success"]]
    g_failed = [e for e in group if not e["success"]]
    print(f"\n{key}")
    print(f"  成功: {len(g_success)}, 失败: {len(g_failed)}")
    if g_success:
        durations = sorted([e["duration"] for e in g_success])
        avg = sum(durations) / len(durations)
        med = durations[len(durations) // 2]
        print(f"  平均: {avg:.1f}s, 中位: {med:.1f}s, 最小: {min(durations):.1f}s, 最大: {max(durations):.1f}s")

print()
print("=" * 70)
print("按模型+思考模式+类型(叫牌/打牌)统计 [核心数据]")
print("=" * 70)
for key in sorted(by_group.keys()):
    group = by_group[key]
    print(f"\n{key}")
    for t in ["bid", "play"]:
        type_entries = [e for e in group if e["type"] == t and e["success"]]
        type_label = "叫牌" if t == "bid" else "打牌"
        if type_entries:
            durations = sorted([e["duration"] for e in type_entries])
            avg = sum(durations) / len(durations)
            med = durations[len(durations) // 2]
            avg_tokens = sum(e["total_tokens"] for e in type_entries) / len(type_entries)
            avg_reasoning = sum(e["reasoning_tokens"] for e in type_entries) / len(type_entries)
            print(f"  {type_label}: {len(type_entries)}次, 平均{avg:.1f}s, 中位{med:.1f}s, 最小{min(durations):.1f}s, 最大{max(durations):.1f}s")
            print(f"    avg_total_tokens={avg_tokens:.0f}, avg_reasoning_tokens={avg_reasoning:.0f}")

print()
print("=" * 70)
print("超时/失败记录")
print("=" * 70)
for e in failed:
    t = "思考" if e["thinking"] else "非思考"
    tp = "叫牌" if e["type"] == "bid" else "打牌"
    print(f"  {e['timestamp']} {e['model'].replace('deepseek-v4-','').upper()}({t}) [{tp}] prompt={e['prompt_chars']} max_tokens={e['max_tokens']} retry={e['retry']} failed={e['failed']}")

print()
print("=" * 70)
print("finish_reason=length 的记录 (输出被截断)")
print("=" * 70)
length_entries = [e for e in success if e["finish_reason"] == "length"]
for e in length_entries:
    tp = "叫牌" if e["type"] == "bid" else "打牌"
    print(f"  {e['timestamp']} {e['model'].replace('deepseek-v4-','').upper()} [{tp}] prompt={e['prompt_chars']} duration={e['duration']}s max_tokens={e['max_tokens']} response={e['response_chars']}")

print()
print("=" * 70)
print("最近打牌会话详情")
print("=" * 70)
play_entries = [e for e in entries if e["type"] == "play"]
if play_entries:
    sessions = []
    current_session = [play_entries[0]]
    for i in range(1, len(play_entries)):
        prev_time = datetime.strptime(play_entries[i-1]["timestamp"], "%Y-%m-%d %H:%M:%S")
        curr_time = datetime.strptime(play_entries[i]["timestamp"], "%Y-%m-%d %H:%M:%S")
        if (curr_time - prev_time).total_seconds() > 300:
            sessions.append(current_session)
            current_session = [play_entries[i]]
        else:
            current_session.append(play_entries[i])
    sessions.append(current_session)

    for sidx, session in enumerate(sessions):
        print(f"\n--- 打牌会话 {sidx+1} ---")
        total_time = 0
        for e in session:
            t = "思考" if e["thinking"] else "非思考"
            status = f"OK {e['duration']}s" if e["success"] else ("RETRY" if e["retry"] else "FAILED")
            print(f"  {e['timestamp']} {e['model'].replace('deepseek-v4-','').upper()}({t}) prompt={e['prompt_chars']} max_tok={e['max_tokens']} {status}")
            if e["success"]:
                total_time += e["duration"]
        success_count = sum(1 for e in session if e["success"])
        print(f"  小计: {success_count}/{len(session)}成功, 总耗时{total_time:.1f}s, 平均{total_time/max(success_count,1):.1f}s/步")

print()
print("=" * 70)
print("最近叫牌会话详情")
print("=" * 70)
bid_entries = [e for e in entries if e["type"] == "bid"]
if bid_entries:
    sessions = []
    current_session = [bid_entries[0]]
    for i in range(1, len(bid_entries)):
        prev_time = datetime.strptime(bid_entries[i-1]["timestamp"], "%Y-%m-%d %H:%M:%S")
        curr_time = datetime.strptime(bid_entries[i]["timestamp"], "%Y-%m-%d %H:%M:%S")
        if (curr_time - prev_time).total_seconds() > 300:
            sessions.append(current_session)
            current_session = [bid_entries[i]]
        else:
            current_session.append(bid_entries[i])
    sessions.append(current_session)

    for sidx, session in enumerate(sessions):
        print(f"\n--- 叫牌会话 {sidx+1} ---")
        total_time = 0
        for e in session:
            t = "思考" if e["thinking"] else "非思考"
            status = f"OK {e['duration']}s" if e["success"] else ("RETRY" if e["retry"] else "FAILED")
            print(f"  {e['timestamp']} {e['model'].replace('deepseek-v4-','').upper()}({t}) prompt={e['prompt_chars']} {status}")
            if e["success"]:
                total_time += e["duration"]
        success_count = sum(1 for e in session if e["success"])
        print(f"  小计: {success_count}/{len(session)}成功, 总耗时{total_time:.1f}s, 平均{total_time/max(success_count,1):.1f}s/步")

print()
print("=" * 70)
print("综合对比表")
print("=" * 70)
print(f"{'模式':<25} {'类型':<6} {'次数':>4} {'平均':>7} {'中位':>7} {'最小':>7} {'最大':>7} {'失败':>4}")
print("-" * 70)
for key in sorted(by_group.keys()):
    group = by_group[key]
    for t in ["bid", "play"]:
        type_entries = [e for e in group if e["type"] == t]
        type_success = [e for e in type_entries if e["success"]]
        type_failed = [e for e in type_entries if not e["success"]]
        type_label = "叫牌" if t == "bid" else "打牌"
        if type_entries:
            if type_success:
                durations = [e["duration"] for e in type_success]
                avg = sum(durations) / len(durations)
                med = sorted(durations)[len(durations) // 2]
                print(f"{key:<25} {type_label:<6} {len(type_success):>4} {avg:>6.1f}s {med:>6.1f}s {min(durations):>6.1f}s {max(durations):>6.1f}s {len(type_failed):>4}")
            else:
                print(f"{key:<25} {type_label:<6} {0:>4} {'N/A':>7} {'N/A':>7} {'N/A':>7} {'N/A':>7} {len(type_failed):>4}")
```

## Execution Steps

1. Write the script above to a temporary file (e.g., `analyze_log.py` in the project root)
2. Run `python analyze_log.py`
3. Read the output and present the results to the user in a clear format
4. Delete the temporary script file after analysis

## Output Interpretation

When presenting results to the user, always include:

1. **综合对比表** - The summary comparison table is the most important output
2. **Key findings** - Highlight notable patterns:
   - Which model/mode is fastest for bidding vs playing
   - Failure/timeout rates
   - Output truncation issues (finish_reason=length)
   - Stability (min vs max duration gap)
3. **Recommendations** - Based on the data, suggest optimal model/mode configurations

## Important Notes

- Always classify using `max_tokens`, NOT `prompt_chars`. Bidding prompts can be very large (10000+ chars) due to JF convention content.
- The `reasoning_tokens` field indicates thinking mode usage: non-thinking mode should have 0, thinking mode will have thousands.
- Sessions are grouped by 5-minute gaps between consecutive requests of the same type.
- All 3 timeout failures in historical data came from PRO model with prompt > 14000 chars.
