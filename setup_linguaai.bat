@echo off
rem ======================================================================
rem  LinguaAI setup - run once (needs internet for downloads).
rem  Creates a virtual environment in this folder, installs packages,
rem  downloads models (asks first), creates the database, runs diagnostics.
rem  It never deletes your files.
rem ======================================================================
setlocal
cd /d "%~dp0"
title LinguaAI setup
echo.
echo  LinguaAI setup
echo  Project folder: %CD%
echo.

echo %CD% | find /i "OneDrive" >nul
if not errorlevel 1 (
  echo [WARN] This folder is inside OneDrive. OneDrive may sync your private
  echo        practice data to the cloud and can lock files while syncing.
  echo        Recommended: move the LinguaAI folder to C:\LinguaAI and run setup again.
  echo.
  choice /c YN /m "Continue here anyway"
  if errorlevel 2 exit /b 1
)

rem ---- 1. Find a supported Python (3.11 - 3.13, 64-bit) -------------------
set "PY="
for %%v in (3.12 3.11 3.13) do (
  if not defined PY (
    py -%%v -c "import sys; sys.exit(0 if sys.maxsize > 2**32 else 1)" >nul 2>&1 && set "PY=py -%%v"
  )
)
if not defined PY (
  python -c "import sys; sys.exit(0 if (3,11) <= sys.version_info[:2] <= (3,13) and sys.maxsize > 2**32 else 1)" >nul 2>&1 && set "PY=python"
)
if not defined PY (
  echo [FAIL] Python 3.11, 3.12 or 3.13 ^(64-bit^) was not found.
  echo        Install Python 3.12 from https://www.python.org/downloads/windows/
  echo        and tick "Add python.exe to PATH" during installation.
  pause
  exit /b 1
)
echo [ OK ] Using: %PY%
%PY% --version

rem ---- 2. Virtual environment ---------------------------------------------
if exist "venv\Scripts\python.exe" (
  echo [ OK ] Virtual environment already exists - reusing it.
) else (
  echo [....] Creating virtual environment in %CD%\venv
  %PY% -m venv venv
  if errorlevel 1 (
    echo [FAIL] Could not create the virtual environment.
    pause
    exit /b 1
  )
)

rem ---- 3. Packages ----------------------------------------------------------
echo [....] Installing Python packages (about 400 MB, may take several minutes)...
"venv\Scripts\python.exe" -m pip install --upgrade pip
"venv\Scripts\python.exe" -m pip install -r requirements.txt
if errorlevel 1 (
  echo [FAIL] Package installation failed. Check your internet connection and
  echo        see docs\TROUBLESHOOTING.md ^("A dependency fails to install"^).
  pause
  exit /b 1
)
echo [ OK ] Packages installed.

rem ---- 4. Models ------------------------------------------------------------
echo.
echo [....] Checking models. You will be asked before each download.
echo        If Ollama is not installed yet, get it from https://ollama.com/download
echo        then run this setup again.
"venv\Scripts\python.exe" scripts\download_models.py

rem ---- 5. Database and diagnostics -----------------------------------------
"venv\Scripts\python.exe" scripts\init_db.py
echo.
"venv\Scripts\python.exe" scripts\diagnose.py
echo.
echo Setup finished. Start LinguaAI by double-clicking run_linguaai.bat
pause
