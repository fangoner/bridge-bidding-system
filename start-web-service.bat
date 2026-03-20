@echo off

echo Starting Bridge Bidding Practice Web Service...
echo =============================================

rem Start backend API server
start "Backend API Server" cmd /k "python -c "import uvicorn; from api.main import app; uvicorn.run(app, host='127.0.0.1', port=8003)""

rem Give backend time to start
timeout /t 2 /nobreak >nul

rem Start frontend React application
cd web
start "Frontend React App" powershell -Command "Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass -Force; npm run dev"
cd ..

echo =============================================
echo Web Service Started!
echo Backend API: http://127.0.0.1:8003
echo Frontend: http://localhost:5173
echo =============================================
echo 

pause