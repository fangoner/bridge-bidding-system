@echo off
cd /d "d:\Bridge Card\Bidding System"
"C:\Users\Fanyi\AppData\Local\Programs\Python\Python313\python.exe" -m uvicorn api.main:app --host 0.0.0.0 --port 8003
pause
