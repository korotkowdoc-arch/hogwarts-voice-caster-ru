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
if not exist "download_gigaam.py" goto :missingfiles
REM Some Windows Python launchers return exit code 0 even if a runtime is missing.
REM Check an exact stdout marker produced by a REAL Python interpreter.
set "PYTHON_CMD="
call :probe_python py -3.11
if defined PYTHON_CMD goto :foundpython
call :probe_python py -3.12
if defined PYTHON_CMD goto :foundpython
call :probe_python python
if defined PYTHON_CMD goto :foundpython
call :probe_python python3
if defined PYTHON_CMD goto :foundpython
call :probe_python py -3
if not defined PYTHON_CMD goto :missingpython
:foundpython
echo Using Python: %PYTHON_CMD%
if /I "%~1"=="--check-python" goto :pythoncheckok
echo [1/4] Preparing Python virtual environment...
echo Interpreter: %PYTHON_CMD% >> "%LOG%"
call %PYTHON_CMD% -m venv ".venv" >> "%LOG%" 2>&1
if errorlevel 1 goto :venvfail
if not exist ".venv\Scripts\python.exe" goto :venvfail
echo [2/4] Updating pip...
".venv\Scripts\python.exe" -m pip install --upgrade pip --disable-pip-version-check >> "%LOG%" 2>&1
if errorlevel 1 goto :pipfail
echo [3/4] Installing offline neural speech packages...
".venv\Scripts\python.exe" -m pip install --disable-pip-version-check -r "requirements.txt" >> "%LOG%" 2>&1
if errorlevel 1 goto :depsfail
echo [4/4] Downloading and checking the Russian neural model (~236 MB)...
".venv\Scripts\python.exe" -u "download_gigaam.py" >> "%LOG%" 2>&1
if errorlevel 1 goto :modelfail
echo [OK] Installation complete. Open run.bat.
goto :success
:missingfiles
echo [ERROR] Files are missing. Extract the entire ZIP before running.
goto :fail
:missingpython
echo [ERROR] Python 3.11 or 3.12 x64 not found.
echo Try: py install 3.11
echo Or install Python 3.11 x64 from https://www.python.org/downloads/
echo The previous Python selection issue is fixed in this installer.
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
:pythoncheckok
echo [OK] Found supported Python interpreter: %PYTHON_CMD%
exit /b 0
:selftest
if not exist "%~dp0requirements.txt" exit /b 2
if not exist "%~dp0download_model.py" exit /b 3
echo [OK] Installer launched correctly.
exit /b 0
:probe_python
REM A Python Manager stub can report "No runtime installed" with status 0.
REM Thus check a magic output line, not only ERRORLEVEL.
set "PROBE_OUTPUT=%TEMP%\hvc_python_probe_%RANDOM%_%RANDOM%.txt"
%* -c "import sys;print('HVC_VALID_PY' if sys.version_info[:2] in ((3,11),(3,12)) and sys.maxsize > 2**32 else 'HVC_INVALID_PY')" > "%PROBE_OUTPUT%" 2>nul
findstr /x /c:"HVC_VALID_PY" "%PROBE_OUTPUT%" >nul 2>nul
if not errorlevel 1 set "PYTHON_CMD=%*"
if exist "%PROBE_OUTPUT%" del /q "%PROBE_OUTPUT%" >nul 2>nul
exit /b 0
