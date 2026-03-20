$path = "$env:LOCALAPPDATA\Packages\Microsoft.WindowsTerminal_8wekyb3d8bbwe\LocalState\settings.json"
$content = Get-Content $path -Raw
$content = $content -replace '"useAcrylic": true', '"useAcrylic": false'
Set-Content $path -Value $content -NoNewline
Write-Output "Done"
