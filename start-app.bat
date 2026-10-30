@echo off
setlocal
cd /d "%~dp0"

echo ========================================
echo   Couple App - Full Stack Launcher
echo ========================================
echo.

where conda >nul 2>nul
if errorlevel 1 (
    echo [ERROR] Conda was not found in PATH.
    pause
    exit /b 1
)

where node >nul 2>nul
if errorlevel 1 (
    echo [ERROR] Node.js was not found in PATH.
    pause
    exit /b 1
)

call conda run -n couple-app python -c "import fastapi, uvicorn" >nul 2>nul
if errorlevel 1 (
    echo [ERROR] Backend dependencies are missing from the couple-app environment.
    echo         Run: conda run -n couple-app python -m pip install -r backend\requirements.txt
    pause
    exit /b 1
)

if not exist "frontend\node_modules" (
    echo [*] Installing frontend dependencies...
    pushd frontend
    call npm ci
    if errorlevel 1 (
        popd
        echo [ERROR] Frontend dependency installation failed.
        pause
        exit /b 1
    )
    popd
)

netstat -ano | findstr /R /C:":8000 .*LISTENING" >nul
if errorlevel 1 (
    echo [*] Starting backend at http://localhost:8000
    start "Couple App Backend" cmd /k "cd /d "%~dp0backend" && set SERVER_RELOAD=false && conda run -n couple-app --no-capture-output python run.py"
) else (
    echo [OK] Backend is already running at http://localhost:8000
)

echo [*] Starting independent memory worker
start "Couple App Memory Worker" cmd /k "cd /d "%~dp0backend" && conda run -n couple-app --no-capture-output python -m app.memory_worker"

netstat -ano | findstr /R /C:":5173 .*LISTENING" >nul
if errorlevel 1 (
    echo [*] Starting frontend at http://localhost:5173
    start "Couple App Frontend" cmd /k "cd /d "%~dp0frontend" && npm run dev"
) else (
    echo [OK] Frontend is already running at http://localhost:5173
)

echo.
echo [OK] Servers are starting. Open http://localhost:5173
endlocal
