@echo off
setlocal EnableExtensions
cd /d "%~dp0"
if /I "%~1"=="--self-test" goto :selftest
if not exist ".venv\Scripts\python.exe" goto :missing
REM Double click = background GUI without a persistent console window.
if "%~1"=="" goto :gui
set "PYTHONPATH=%~dp0src"
".venv\Scripts\python.exe" -m hogwarts_voice %*
set "STATUS=%errorlevel%"
echo.
if not "%STATUS%"=="0" echo [ERROR] Command exited with code %STATUS%.
pause
exit /b %STATUS%
:gui
if not exist ".venv\Scripts\pythonw.exe" goto :missing
start "" "%~dp0.venv\Scripts\pythonw.exe" "%~dp0launch_gui.pyw"
exit /b 0
:missing
echo [ERROR] Environment is missing. Run install.bat after extracting the ZIP.
pause
exit /b 1
:selftest
if not exist "%~dp0launch_gui.pyw" exit /b 3
echo [OK] Hidden GUI launch script exists.
exit /b 0
