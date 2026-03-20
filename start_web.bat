@echo off
cd /d "%~dp0"

start /b python -m uvicorn api.main:app --host 0.0.0.0 --port 8003 >nul 2>&1

timeout /t 3 /nobreak >nul

cd web
start /b npm run dev >nul 2>&1

echo Services started in background!
echo Frontend: http://localhost:5173
echo API: http://localhost:8003
echo LAN: http://192.168.1.14:5173
echo.
echo Close this window to stop services.
pause
