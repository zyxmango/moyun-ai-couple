@echo off
cd /d "%~dp0"
echo ========================================
echo   Couple App - Backend Server
echo ========================================
echo.
where conda >nul 2>nul
if errorlevel 1 (
    echo [ERROR] Conda was not found in PATH.
    pause
    exit /b 1
)

echo [*] Starting with Conda environment: couple-app
set SERVER_RELOAD=false
call conda run -n couple-app --no-capture-output python run.py
pause
