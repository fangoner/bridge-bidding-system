@echo off
chcp 65001 >nul
setlocal enabledelayedexpansion

echo.
echo ╔════════════════════════════════════════════════════════════╗
echo ║          桥牌叫牌练习系统 - 完整打包流程                    ║
echo ╚════════════════════════════════════════════════════════════╝
echo.

:: 检查必要文件
echo [步骤 1/4] 检查必要文件...
set "missing_files="

if not exist "JF约定.docx" (
    set "missing_files=!missing_files! JF约定.docx"
)

if not exist ".env.example" (
    set "missing_files=!missing_files! .env.example"
)

if not exist "run.py" (
    set "missing_files=!missing_files! run.py"
)

if not exist "main.py" (
    set "missing_files=!missing_files! main.py"
)

if not "!missing_files!"=="" (
    echo.
    echo [错误] 缺少必要文件：!missing_files!
    echo 请确保这些文件存在后再运行打包脚本。
    pause
    exit /b 1
)

echo [√] 所有必要文件已就绪

:: 安装依赖
echo.
echo [步骤 2/4] 检查并安装依赖...
pip show pyinstaller >nul 2>&1
if errorlevel 1 (
    echo 正在安装 PyInstaller...
    pip install pyinstaller
)

pip show openai >nul 2>&1
if errorlevel 1 (
    echo 正在安装 openai...
    pip install openai
)

pip show python-docx >nul 2>&1
if errorlevel 1 (
    echo 正在安装 python-docx...
    pip install python-docx
)

echo [√] 依赖安装完成

:: PyInstaller 打包
echo.
echo [步骤 3/4] 开始 PyInstaller 打包...
if exist "dist" rmdir /s /q "dist"
if exist "build" rmdir /s /q "build"

pyinstaller build.spec --clean

if not exist "dist\桥牌叫牌练习.exe" (
    echo.
    echo [错误] PyInstaller 打包失败
    pause
    exit /b 1
)

echo [√] PyInstaller 打包完成

:: 创建发布目录
echo.
echo [步骤 4/4] 创建发布包...
set "release_dir=release_桥牌叫牌练习"
if exist "!release_dir!" rmdir /s /q "!release_dir!"
mkdir "!release_dir!"

:: 复制文件
copy "dist\桥牌叫牌练习.exe" "!release_dir!\" >nul
copy "JF约定.docx" "!release_dir!\" >nul
copy ".env.example" "!release_dir!\" >nul
copy "README.txt" "!release_dir!\" >nul

:: 复制 Deep Finesse（如果存在）
if exist "Deep Finesse 2014 v2" (
    echo 正在复制 Deep Finesse...
    xcopy "Deep Finesse 2014 v2" "!release_dir!\Deep Finesse 2014 v2\" /E /I /Q >nul
)

echo [√] 发布包创建完成

:: 显示结果
echo.
echo ╔════════════════════════════════════════════════════════════╗
echo ║                    打包完成！                              ║
echo ╚════════════════════════════════════════════════════════════╝
echo.
echo 发布包位置：!release_dir!\
echo.
echo 包含文件：
dir /b "!release_dir!"
echo.
echo ════════════════════════════════════════════════════════════
echo 下一步：
echo   1. 测试运行 !release_dir!\桥牌叫牌练习.exe
echo   2. 如需创建安装程序，运行 Inno Setup 编译 installer.iss
echo   3. 将 !release_dir! 目录打包为 ZIP 发布
echo ════════════════════════════════════════════════════════════
echo.

pause
