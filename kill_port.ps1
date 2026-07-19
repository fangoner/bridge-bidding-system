param([int]$Port = 8003)
$conns = Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue
if ($conns) {
    foreach ($c in $conns) {
        Write-Host ("Killing PID {0} on port {1}" -f $c.OwningProcess, $Port)
        Stop-Process -Id $c.OwningProcess -Force -ErrorAction SilentlyContinue
    }
} else {
    Write-Host ("No process listening on port {0}" -f $Port)
}
