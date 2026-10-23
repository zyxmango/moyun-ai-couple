@echo off
cd /d "%~dp0"

REM Auto fix Node.js PATH (conda may override it)
if exist "C:\Program Files\nodejs\node.exe" (
    set "PATH=C:\Program Files\nodejs;%PATH%"
) else if exist "C:\Program Files (x86)\nodejs\node.exe" (
    set "PATH=C:\Program Files (x86)\nodejs;%PATH%"
)

where node >nul 2>nul
if errorlevel 1 (
    echo [ERROR] Node.js not found! Please install from https://nodejs.org/
    pause
    exit /b 1
)

echo [OK] Node:
node --version
echo [OK] npm:
npm --version
echo.

REM Install dependencies if missing
if not exist "node_modules" (
    echo [*] Installing dependencies...
    call npm install
    if errorlevel 1 (
        echo [ERROR] Install failed. Try mirror:
        echo     npm config set registry https://registry.npmmirror.com
        pause
        exit /b 1
    )
    echo [OK] Dependencies installed!
    echo.
)

echo [*] Starting dev server...
echo     URL: http://localhost:5173
echo     Press Ctrl+C to stop
echo.
call npm run dev
pause
