@echo off
setlocal enabledelayedexpansion
cd /d "%~dp0"

REM ============================================================
REM  Bridge Bidding System - Web Startup (backend 8003 + frontend 5173)
REM
REM  IMPORTANT: this file is pure ASCII on purpose.
REM  cmd.exe reads .bat files using the OEM codepage (GBK on this
REM  machine), NOT UTF-8. Any non-ASCII byte in a comment is decoded
REM  as garbage and can shift bytes mid-line, splitting later lines
REM  into bogus commands and breaking the whole script.
REM  Keep it ASCII. Do not add Chinese text here.
REM
REM  Also: no --reload on uvicorn (project policy, AGENTS.md).
REM ============================================================

echo ========================================
echo   Bridge Bidding System - Web Startup
echo ========================================
echo.

REM ---- [0/2] port pre-check: a busy port makes uvicorn/vite fail
REM ---- inside their own window, which is easy to miss.
set "PORTBUSY="
for %%P in (8003 5173) do (
    netstat -ano | findstr /r /c:":%%P .*LISTENING" >nul 2>&1
    if !errorlevel! equ 0 set "PORTBUSY=!PORTBUSY! %%P"
)
if defined PORTBUSY (
    echo [ERROR] Port^(s^) already in use:!PORTBUSY!
    echo.
    echo   Another instance is probably still running. Close it, or release
    echo   the ports, then run this script again:
    echo.
    echo       powershell -ExecutionPolicy Bypass -File kill_port.ps1
    echo.
    pause
    exit /b 1
)
echo [0/2] Ports 8003 / 5173 free.
echo.

echo [1/2] Starting backend (port 8003)...
start "Bridge Backend API" cmd /c "python -m uvicorn api.main:app --host 0.0.0.0 --port 8003"

echo [2/2] Starting frontend (port 5173)...
cd web
start "Bridge Frontend" cmd /c "npm run dev"
cd ..

echo.
echo Waiting for services...
echo.

set "BACKEND_OK="
for /L %%i in (1,1,20) do (
    timeout /t 1 /nobreak >nul
    curl -s http://localhost:8003/api/health >nul 2>&1
    if !errorlevel! equ 0 (
        echo Backend:  http://localhost:8003 [OK]
        set "BACKEND_OK=1"
        goto :check_frontend
    )
)
echo Backend:  http://localhost:8003 [FAILED - check the backend window]

:check_frontend
for /L %%i in (1,1,20) do (
    timeout /t 1 /nobreak >nul
    curl -s http://localhost:5173 >nul 2>&1
    if !errorlevel! equ 0 (
        echo Frontend: http://localhost:5173 [OK]
        goto :done
    )
)
echo Frontend: http://localhost:5173 [FAILED - check the frontend window]

:done
echo.
echo ========================================
if defined BACKEND_OK (
    echo   Ready:  open http://localhost:5173
) else (
    echo   Backend did not come up - the page at :5173 cannot work.
)
echo   Close the service windows to stop.
echo ========================================
echo.
pause
