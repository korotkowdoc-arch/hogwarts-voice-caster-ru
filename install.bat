@echo off
setlocal
cd /d "%~dp0"
where py >nul 2>nul
if %errorlevel%==0 (
  py -3 -m venv .venv
) else (
  python -m venv .venv
)
if errorlevel 1 goto :fail
call ".venv\Scripts\python.exe" -m pip install --upgrade pip
if errorlevel 1 goto :fail
call ".venv\Scripts\python.exe" -m pip install -r requirements.txt
if errorlevel 1 goto :fail
REM Resemblyzer's legacy requirements include a Windows source-only VAD and typing backport.
call ".venv\Scripts\python.exe" -m pip install --no-deps resemblyzer==0.1.4
if errorlevel 1 goto :fail
call ".venv\Scripts\python.exe" download_model.py
if errorlevel 1 goto :fail
echo.
echo [OK] Installed. Run run.bat
pause
exit /b 0
:fail
echo [ERROR] Install failed. Install Python 3.11 or 3.12 (64-bit), check internet.
pause
exit /b 1
