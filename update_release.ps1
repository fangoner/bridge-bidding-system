$ErrorActionPreference = "Stop"

Write-Host ""
Write-Host "========================================" -ForegroundColor Cyan
Write-Host "  桥牌叫牌练习 - 更新打包" -ForegroundColor Cyan
Write-Host "========================================" -ForegroundColor Cyan
Write-Host ""

Write-Host "[1/2] 重新打包 EXE..." -ForegroundColor Yellow
python -m PyInstaller build.spec --clean

if ($LASTEXITCODE -ne 0) {
    Write-Host "[错误] 打包失败！" -ForegroundColor Red
    Read-Host "按回车键退出"
    exit 1
}

Write-Host ""
Write-Host "[2/2] 更新发布目录..." -ForegroundColor Yellow

if (Test-Path "release_桥牌叫牌练习") {
    Copy-Item "dist\桥牌叫牌练习.exe" "release_桥牌叫牌练习\" -Force
    Write-Host "[完成] 发布目录已更新！" -ForegroundColor Green
} else {
    Write-Host "[提示] 发布目录不存在，正在创建..." -ForegroundColor Yellow
    New-Item -ItemType Directory -Path "release_桥牌叫牌练习" -Force | Out-Null
    Copy-Item "dist\桥牌叫牌练习.exe" "release_桥牌叫牌练习\"
    Copy-Item "JF实战_标准自然 - Rev 3.2.docx" "release_桥牌叫牌练习\"
    Copy-Item ".env.example" "release_桥牌叫牌练习\"
    Copy-Item "README.txt" "release_桥牌叫牌练习\"
    Copy-Item "LICENSE.txt" "release_桥牌叫牌练习\"
    if (Test-Path "Deep Finesse 2014 v2") {
        Copy-Item -Recurse "Deep Finesse 2014 v2" "release_桥牌叫牌练习\"
    }
    Write-Host "[完成] 发布目录已创建！" -ForegroundColor Green
}

Write-Host ""
Write-Host "========================================" -ForegroundColor Cyan
Write-Host "  更新完成！" -ForegroundColor Green
Write-Host "  发布目录: release_桥牌叫牌练习\" -ForegroundColor Cyan
Write-Host "========================================" -ForegroundColor Cyan
Write-Host ""

Read-Host "按回车键退出"
