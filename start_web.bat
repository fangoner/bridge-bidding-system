@echo off
cd /d "%~dp0"

echo Starting backend with auto-reload...
start /b "" "C:\Users\Fanyi\AppData\Local\Programs\Python\Python313\python.exe" -m uvicorn api.main:app --host 0.0.0.0 --port 8003 --reload >nul 2>&1

timeout /t 3 /nobreak >nul

echo Starting frontend...
cd web
start /b "" npm run dev >nul 2>&1

echo.
echo Services started in background!
echo Frontend: http://localhost:5173
echo API: http://localhost:8003
echo.
echo Note: Backend auto-reloads on code changes.
echo Close this window to stop services.
pause
