@echo off
chcp 65001 >nul
set ANTHROPIC_BASE_URL=https://api.deepseek.com/anthropic
set ANTHROPIC_AUTH_TOKEN=sk-703047b8bd6544fca562ae93b54207f8
set API_TIMEOUT_MS=600000
set ANTHROPIC_MODEL=deepseek-v4-flash
set ANTHROPIC_SMALL_FAST_MODEL=deepseek-v4-flash
set CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC=1

echo Starting Claude Code with DeepSeek...
echo.
echo Environment configured:
echo   ANTHROPIC_BASE_URL=%ANTHROPIC_BASE_URL%
echo   ANTHROPIC_MODEL=%ANTHROPIC_MODEL%
echo.

node D:\Claude-Code\node_modules\@anthropic-ai\claude-code\cli.js %*
