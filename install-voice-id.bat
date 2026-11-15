@echo off
setlocal EnableExtensions
cd /d "%~dp0"
if /I "%~1"=="--self-test" goto :selftest
if not exist ".venv\Scripts\python.exe" goto :missing
echo Speaker identification is optional and slows voice commands.
".venv\Scripts\python.exe" -m pip install "torch>=2.2,<3" "scipy>=1.11,<2" "librosa>=0.10.2,<0.12" "webrtcvad-wheels>=2.0.14.post1"
if errorlevel 1 goto :fail
".venv\Scripts\python.exe" -m pip install --no-deps resemblyzer==0.1.4
if errorlevel 1 goto :fail
echo [OK] Optional voice identification installed.
goto :ok
:missing
echo [ERROR] Run install.bat first.
goto :fail
:fail
echo [ERROR] Optional voice ID setup failed.
pause
exit /b 1
:ok
pause
exit /b 0
:selftest
echo [OK] Optional launcher works.
exit /b 0
