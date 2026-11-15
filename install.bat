@echo off
setlocal EnableExtensions
cd /d "%~dp0"
if /I "%~1"=="--self-test" goto :selftest
set "LOG=%CD%\install.log"
> "%LOG%" echo Hogwarts Voice Caster RU installation
echo ===== Hogwarts Voice Caster RU - Installer =====
echo.
echo Fast mode: no speaker ID or heavy torch dependency.
echo Logging details to install.log in this folder.
if not exist "requirements.txt" goto :missingfiles
if not exist "download_model.py" goto :missingfiles
set "PYTHON_CMD="
where py >nul 2>nul
if errorlevel 1 goto :try_python
py -3.11 -c "import sys;sys.exit(0 if sys.maxsize>2**32 else 1)" >nul 2>nul
if not errorlevel 1 set "PYTHON_CMD=py -3.11"
if defined PYTHON_CMD goto :foundpython
py -3.12 -c "import sys;sys.exit(0 if sys.maxsize>2**32 else 1)" >nul 2>nul
if not errorlevel 1 set "PYTHON_CMD=py -3.12"
if defined PYTHON_CMD goto :foundpython
:try_python
where python >nul 2>nul
if errorlevel 1 goto :missingpython
python -c "import sys;sys.exit(0 if sys.version_info[:2] in ((3,11),(3,12)) and sys.maxsize>2**32 else 1)" >nul 2>nul
if errorlevel 1 goto :missingpython
set "PYTHON_CMD=python"
:foundpython
echo [1/4] Preparing Python virtual environment...
echo Interpreter: %PYTHON_CMD% >> "%LOG%"
call %PYTHON_CMD% -m venv ".venv" >> "%LOG%" 2>&1
if errorlevel 1 goto :venvfail
if not exist ".venv\Scripts\python.exe" goto :venvfail
echo [2/4] Updating pip...
".venv\Scripts\python.exe" -m pip install --upgrade pip --disable-pip-version-check >> "%LOG%" 2>&1
if errorlevel 1 goto :pipfail
echo [3/4] Installing basic offline speech packages...
".venv\Scripts\python.exe" -m pip install --disable-pip-version-check -r "requirements.txt" >> "%LOG%" 2>&1
if errorlevel 1 goto :depsfail
echo [4/4] Downloading Russian speech model...
".venv\Scripts\python.exe" "download_model.py" >> "%LOG%" 2>&1
if errorlevel 1 goto :modelfail
echo [OK] Installation complete. Open run.bat.
goto :success
:missingfiles
echo [ERROR] Files are missing. Extract the entire ZIP before running.
goto :fail
:missingpython
echo [ERROR] Python 3.11 or 3.12 x64 not found.
echo Install Python 3.11 x64 from https://www.python.org/downloads/
goto :fail
:venvfail
echo [ERROR] Virtual environment creation failed.
goto :details
:pipfail
echo [ERROR] pip upgrade failed.
goto :details
:depsfail
echo [ERROR] Offline speech package installation failed.
goto :details
:modelfail
echo [ERROR] Model download failed.
goto :details
:details
echo See install.log for the detailed error.
goto :fail
:fail
echo.
echo [FAILED] Installation was NOT completed.
echo The window will stay open until you press a key.
pause
exit /b 1
:success
echo.
echo The window will stay open until you press a key.
pause
exit /b 0
:selftest
if not exist "%~dp0requirements.txt" exit /b 2
if not exist "%~dp0download_model.py" exit /b 3
echo [OK] Installer launched correctly.
exit /b 0
