@echo off
rem ======================================================================
rem  Start LinguaAI. Keep this window open while you use the app;
rem  close it (or press Ctrl+C) to stop LinguaAI.
rem ======================================================================
setlocal
cd /d "%~dp0"
title LinguaAI

if not exist "venv\Scripts\python.exe" (
  echo [FAIL] LinguaAI is not installed yet. Double-click setup_linguaai.bat first.
  pause
  exit /b 1
)

"venv\Scripts\python.exe" scripts\launcher_check.py
set "CODE=%errorlevel%"
if "%CODE%"=="1" (
  echo.
  echo Startup check failed - see the message above. For details run check_system.bat
  pause
  exit /b 1
)
set /p PORT=<logs\launch_port.txt
if "%CODE%"=="2" (
  echo Opening the running LinguaAI instead of starting a second copy...
  start "" "http://localhost:%PORT%"
  timeout /t 5 >nul
  exit /b 0
)

echo.
echo  Starting LinguaAI on http://localhost:%PORT%  (only reachable from this computer)
echo  Your browser will open automatically. Keep this window open.
echo.
start "" /b "venv\Scripts\python.exe" scripts\open_browser.py %PORT%
"venv\Scripts\python.exe" -m streamlit run app.py --server.port %PORT% --server.address 127.0.0.1
if errorlevel 1 (
  echo.
  echo [FAIL] LinguaAI stopped with an error. See the messages above and logs\linguaai.log
  echo        Run check_system.bat for a full diagnosis.
)
pause
