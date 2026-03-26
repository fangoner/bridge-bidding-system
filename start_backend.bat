@echo off
cd /d "%~dp0"
echo Starting backend with auto-reload...
echo.
"C:\Users\Fanyi\AppData\Local\Programs\Python\Python313\python.exe" -m uvicorn api.main:app --host 0.0.0.0 --port 8003 --reload
echo.
echo Backend stopped.
pause
