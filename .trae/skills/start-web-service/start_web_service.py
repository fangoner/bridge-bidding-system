import subprocess
import os
import time


def start_backend():
    """Start the backend API server"""
    backend_cmd = [
        'python', '-c',
        'import uvicorn; from api.main import app; uvicorn.run(app, host="127.0.0.1", port=8003)'
    ]
    print("Starting backend API server...")
    backend_process = subprocess.Popen(
        backend_cmd,
        creationflags=subprocess.CREATE_NEW_CONSOLE
    )
    return backend_process


def start_frontend():
    """Start the frontend React application"""
    frontend_dir = os.path.join(os.path.dirname(__file__), '../../../web')
    frontend_cmd = [
        'powershell.exe', '-Command',
        'Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass -Force; npm run dev'
    ]
    print("Starting frontend React application...")
    frontend_process = subprocess.Popen(
        frontend_cmd,
        cwd=frontend_dir,
        creationflags=subprocess.CREATE_NEW_CONSOLE
    )
    return frontend_process


def main():
    """Start both backend and frontend services"""
    print("=== Starting Bridge Bidding Practice Web Service ===")
    
    # Start backend first
    backend_process = start_backend()
    time.sleep(2)  # Give backend time to start
    
    # Start frontend
    frontend_process = start_frontend()
    
    print("\n=== Web Service Started ===")
    print("Backend API: http://127.0.0.1:8003")
    print("Frontend: http://localhost:5173")
    print("\nPress Ctrl+C to stop the services")
    
    try:
        # Keep the script running
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        print("\n=== Stopping Web Service ===")
        backend_process.terminate()
        frontend_process.terminate()
        print("Services stopped.")


if __name__ == "__main__":
    main()