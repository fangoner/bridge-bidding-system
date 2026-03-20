---
name: "start-web-service"
description: "Starts the bridge bidding practice web service, including both frontend and backend servers. Invoke when user wants to start the web application."
---

# Start Web Service

This skill starts the bridge bidding practice web service, including both the backend API server and the frontend React application.

## When to Invoke

- When you want to start the web version of the bridge bidding practice system
- When the web service is not running and you need to access the application
- When you've made changes to the code and need to restart the services

## Startup Procedure

Follow these steps in order:

### Step 1: Kill any existing processes on ports 8003 and 5173

```powershell
# Kill process on port 8003 (backend)
$process8003 = netstat -ano | findstr :8003 | findstr LISTENING
if ($process8003) {
    $pid8003 = ($process8003 -split '\s+')[-1]
    taskkill /PID $pid8003 /F 2>$null
}

# Kill process on port 5173 (frontend)
$process5173 = netstat -ano | findstr :5173 | findstr LISTENING
if ($process5173) {
    $pid5173 = ($process5173 -split '\s+')[-1]
    taskkill /PID $pid5173 /F 2>$null
}
```

### Step 2: Start Backend API Server

Use the RunCommand tool with:
- `command`: `python -m uvicorn api.main:app --host 0.0.0.0 --port 8003`
- `cwd`: `d:\Bridge Card\Bidding System`
- `blocking`: false
- `command_type`: web_server
- `requires_approval`: false
- `wait_ms_before_async`: 3000

### Step 3: Start Frontend React Application

Use the RunCommand tool with:
- `command`: `npx vite`
- `cwd`: `d:\Bridge Card\Bidding System\web`
- `blocking`: false
- `command_type`: web_server
- `requires_approval`: false
- `wait_ms_before_async`: 3000

Note: Use `npx vite` instead of `npm run dev` to avoid PowerShell execution policy issues.

### Step 4: Verify Services

After starting both services, check their status. The backend should show:
```
INFO: Uvicorn running on http://0.0.0.0:8003
```

The frontend should show:
```
VITE vX.X.X  ready in X ms
➜  Local:   http://localhost:5173/
```

## Access the Application

After starting both services, open your browser and navigate to:
`http://localhost:5173/`

## Services Started

- **Backend API**: FastAPI server running on http://127.0.0.1:8003
- **Frontend**: React application running on http://localhost:5173

## Configuration

Ensure `web/src/services/api.js` has the correct API port:
```javascript
const API_BASE_URL = `http://${window.location.hostname}:8003`;
```

## Troubleshooting

- If the backend service fails to start with "port already in use", kill the existing process first
- If the frontend service fails to start with "port already in use", kill the existing process first
- Use `npx vite` instead of `npm run dev` to avoid PowerShell execution policy issues
- If API shows "未启动", check that the API_BASE_URL port matches the backend port (8003)
