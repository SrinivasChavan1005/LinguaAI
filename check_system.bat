@echo off
rem ======================================================================
rem  Read-only diagnostics: checks Python, packages, Ollama, models, disk,
rem  RAM and ports. Does not modify or delete anything.
rem ======================================================================
setlocal
cd /d "%~dp0"
title LinguaAI system check
echo User profile : %USERPROFILE%
echo This folder  : %CD%
for /f "tokens=2,*" %%a in ('reg query "HKCU\Software\Microsoft\Windows\CurrentVersion\Explorer\User Shell Folders" /v Desktop 2^>nul ^| find "Desktop"') do echo Desktop path : %%b
echo.
if exist "venv\Scripts\python.exe" (
  "venv\Scripts\python.exe" scripts\diagnose.py
) else (
  echo [INFO] Virtual environment not created yet - using system Python.
  py -3 scripts\diagnose.py 2>nul || python scripts\diagnose.py 2>nul || echo [FAIL] Python not found. Install Python 3.12 from https://www.python.org/downloads/windows/
)
echo.
where ffmpeg >nul 2>&1 && echo [INFO] FFmpeg found (optional) || echo [INFO] FFmpeg not found (optional, not needed)
where git >nul 2>&1 && echo [INFO] Git found || echo [INFO] Git not found (optional)
where nvidia-smi >nul 2>&1 && nvidia-smi --query-gpu=name,memory.total --format=csv,noheader
pause
