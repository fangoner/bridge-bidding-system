@echo off
setlocal enabledelayedexpansion
cd /d "%~dp0"

REM ============================================================
REM  Finesse test suite (fly-card intervention rule layer)
REM  Runs the three finesse scripts under tests/ in sequence.
REM
REM  Output is deliberately ASCII-only: this machine's console
REM  codepage is GBK, so Chinese text in .bat output would be
REM  garbled. The Python scripts themselves print proper UTF-8.
REM
REM  Usage:  run_finesse_tests.bat
REM  Exit code: 0 = all passed, 1 = at least one failed.
REM ============================================================

echo ========================================
echo   Finesse Tests
echo ========================================
echo.

REM ---- locate python ----
set "PY=python"
where python >nul 2>&1
if errorlevel 1 (
    if exist "%LOCALAPPDATA%\Programs\Python\Python313\python.exe" (
        set "PY=%LOCALAPPDATA%\Programs\Python\Python313\python.exe"
        echo [note] 'python' not on PATH, using: !PY!
        echo.
    ) else (
        echo [FAILED] python not found on PATH and no fallback install detected.
        echo          Install Python or add it to PATH, then re-run.
        goto :done
    )
)

REM ---- UTF-8 so the Python scripts' Chinese output does not crash ----
set PYTHONIOENCODING=utf-8
set PYTHONUTF8=1

set "FAILED=0"
set "TOTAL=0"
set "SUMMARY="

REM ---- [1/3] doc sync guard (fast; no DDS, no network) ----
echo [1/3] test_finesse_doc_sync.py  (docs vs code)
%PY% tests\test_finesse_doc_sync.py
if errorlevel 1 (
    echo   ^>^> FAILED
    set "FAILED=1"
    set "SUMMARY=!SUMMARY! [1]doc-sync"
) else (
    echo   ^>^> PASS
)
set /a TOTAL+=1
echo.

REM ---- [2/3] rule layer regression ----
echo [2/3] test_finesse_pipeline.py  (rule layer, 29 cases)
%PY% tests\test_finesse_pipeline.py
if errorlevel 1 (
    echo   ^>^> FAILED
    set "FAILED=1"
    set "SUMMARY=!SUMMARY! [2]pipeline"
) else (
    echo   ^>^> PASS
)
set /a TOTAL+=1
echo.

REM ---- [3/3] probe structure predicate ----
echo [3/3] test_probe_finesse.py  (probe predicate, 8 cases)
%PY% tests\test_probe_finesse.py
if errorlevel 1 (
    echo   ^>^> FAILED
    set "FAILED=1"
    set "SUMMARY=!SUMMARY! [3]probe"
) else (
    echo   ^>^> PASS
)
set /a TOTAL+=1
echo.

:done
echo ========================================
if "%FAILED%"=="1" (
    echo   RESULT: FAILED  -  !TOTAL! script^(s^) run, failed:!SUMMARY!
    echo.
    echo   If [1] doc-sync failed, sync docs\fly-card pipeline diagram
    echo   to the code ^(code is the source of truth^), then re-run.
) else (
    echo   RESULT: ALL PASSED  -  %TOTAL% script^(s^) run
)
echo ========================================
echo.
REM custom wait: cmd built-in pause text is localized and garbles under mixed encodings
set /p "_="  Press any key to continue... 
goto :finish

REM ---- single exit point: guarantees the exit code reaches the caller ----
:finish
if "%FAILED%"=="1" exit /b 1
exit /b 0
