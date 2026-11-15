@echo off
setlocal
cd /d "%~dp0"
if exist "HogwartsLivingWorld.exe" (
  "HogwartsLivingWorld.exe"
) else (
  py -3 -m hlw
)
pause
