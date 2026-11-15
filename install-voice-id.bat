@echo off
setlocal
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" (
  echo [ERROR] Run install.bat first.
  pause
  exit /b 1
)
REM Optional, slower speaker verification; NOT needed for fast spell casting.
call ".venv\Scripts\python.exe" -m pip install "torch>=2.2,<3" "scipy>=1.11,<2" "librosa>=0.10.2,<0.12" "webrtcvad-wheels>=2.0.14.post1"
if errorlevel 1 goto :fail
call ".venv\Scripts\python.exe" -m pip install --no-deps resemblyzer==0.1.4
if errorlevel 1 goto :fail
echo [OK] Optional speaker ID dependencies installed.
pause
exit /b 0
:fail
echo [ERROR] Optional speaker setup failed.
pause
exit /b 1
