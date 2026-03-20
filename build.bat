@echo off
chcp 65001 >nul
echo ========================================
echo 桥牌叫牌练习系统 - 打包脚本
echo ========================================
echo.

echo [1/3] 检查依赖...
pip show pyinstaller >nul 2>&1
if errorlevel 1 (
    echo 正在安装 PyInstaller...
    pip install pyinstaller
)

echo.
echo [2/3] 开始打包...
pyinstaller build.spec --clean

echo.
echo [3/3] 打包完成！
echo.
echo 输出位置: dist\桥牌叫牌练习.exe
echo.
pause
