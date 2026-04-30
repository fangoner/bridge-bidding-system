@echo off
setlocal enabledelayedexpansion
cd /d "%~dp0"

echo ========================================
echo   Bridge Bidding System - Web Startup
echo ========================================
echo.

echo [1/2] Starting backend (port 8003)...
start "Bridge Backend API" cmd /c "python -m uvicorn api.main:app --host 0.0.0.0 --port 8003 --reload && pause"

echo [2/2] Starting frontend (port 5173)...
cd web
start "Bridge Frontend" cmd /c "npm run dev && pause"
cd ..

echo.
echo Waiting for services to start...
echo.

:: Wait and verify backend
for /L %%i in (1,1,10) do (
    timeout /t 1 /nobreak >nul
    curl -s http://localhost:8003/api/health >nul 2>&1
    if !errorlevel! equ 0 (
        echo Backend:  http://localhost:8003 [OK]
        goto :check_frontend
    )
)
echo Backend:  http://localhost:8003 [FAILED - check window]

:check_frontend
:: Wait and verify frontend
for /L %%i in (1,1,15) do (
    timeout /t 1 /nobreak >nul
    curl -s http://localhost:5173 >nul 2>&1
    if !errorlevel! equ 0 (
        echo Frontend: http://localhost:5173 [OK]
        goto :done
    )
)
echo Frontend: http://localhost:5173 [FAILED - check window]

:done
echo.
echo ========================================
echo Close the service windows to stop.
echo ========================================
pause
