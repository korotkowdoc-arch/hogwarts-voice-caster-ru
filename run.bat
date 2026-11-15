@echo off
setlocal EnableExtensions
cd /d "%~dp0"
if /I "%~1"=="--self-test" goto :selftest
set "PYTHONPATH=%~dp0src"
if not exist ".venv\Scripts\python.exe" goto :notinstalled
".venv\Scripts\python.exe" -m hogwarts_voice %*
set "STATUS=%errorlevel%"
echo.
if not "%STATUS%"=="0" echo [ERROR] App exited with code %STATUS%.
echo Press any key to close.
pause
exit /b %STATUS%
:notinstalled
echo [ERROR] Run install.bat first (after extracting ZIP).
pause
exit /b 1
:selftest
echo [OK] Launcher works.
exit /b 0
