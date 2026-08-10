param(
    [switch]$KillOnly
)

function Stop-ProcessOnPort($port) {
    try {
        $connections = Get-NetTCPConnection -LocalPort $port -ErrorAction SilentlyContinue
        foreach ($conn in $connections) {
            $foundPid = $conn.OwningProcess
            if ($foundPid -and $foundPid -gt 0) {
                Stop-Process -Id $foundPid -Force -ErrorAction SilentlyContinue
                Write-Host "Killed PID $foundPid on port $port" -ForegroundColor Yellow
            }
        }
    } catch {
        # fallback: netstat parsing
        $output = netstat -ano | Select-String ":$port\s"
        foreach ($line in $output) {
            $parts = $line -split '\s+'
            $foundPid = $parts[-1]
            if ($foundPid -match '^\d+$') {
                Stop-Process -Id $foundPid -Force -ErrorAction SilentlyContinue
                Write-Host "Killed PID $foundPid on port $port (fallback)" -ForegroundColor Yellow
            }
        }
    }
}

Write-Host "=== Stopping existing processes ===" -ForegroundColor Cyan
Stop-ProcessOnPort 5173
Stop-ProcessOnPort 8003
Start-Sleep -Seconds 2

if ($KillOnly) {
    Write-Host "Done. Processes on ports 5173 and 8003 have been stopped." -ForegroundColor Green
    exit
}

Write-Host "=== Starting backend ===" -ForegroundColor Cyan
$be = Start-Process -WindowStyle Hidden -FilePath "uvicorn" -ArgumentList "api.main:app --host 0.0.0.0 --port 8003" -WorkingDirectory "D:\Bridge Card\Bidding System" -PassThru
Write-Host "Backend started (PID: $($be.Id))" -ForegroundColor Green

Start-Sleep -Seconds 3

Write-Host "=== Starting frontend ===" -ForegroundColor Cyan
$fe = Start-Process -WindowStyle Hidden -FilePath "npm.cmd" -ArgumentList "run dev" -WorkingDirectory "D:\Bridge Card\Bidding System\web" -PassThru
Write-Host "Frontend started (PID: $($fe.Id))" -ForegroundColor Green

Write-Host ""
Write-Host "=============================" -ForegroundColor Cyan
Write-Host "Frontend: http://localhost:5173/" -ForegroundColor Green
Write-Host "Backend:  http://localhost:8003/" -ForegroundColor Green
Write-Host "=============================" -ForegroundColor Cyan
