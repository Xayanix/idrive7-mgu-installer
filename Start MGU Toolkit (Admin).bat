@echo off
setlocal
cd /d "%~dp0"
net session >nul 2>&1
if errorlevel 1 (
  powershell -NoProfile -ExecutionPolicy Bypass -Command "Start-Process -FilePath '%~f0' -Verb RunAs"
  exit /b
)
py -3 --version >nul 2>&1
if errorlevel 1 goto fallback
py -3 "%~dp0run.py"
goto end
:fallback
python "%~dp0run.py"
:end
if errorlevel 1 pause
