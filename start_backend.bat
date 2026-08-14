@echo off
cd /d "%~dp0"
echo Starting backend...
echo.
"C:\Users\Fanyi\AppData\Local\Programs\Python\Python313\python.exe" -m uvicorn api.main:app --host 0.0.0.0 --port 8003
echo.
echo Backend stopped.
pause
