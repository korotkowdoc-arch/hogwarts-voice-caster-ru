@echo off
setlocal
cd /d "%~dp0"
if not defined HLW_REPLY_LANGUAGE set HLW_REPLY_LANGUAGE=ru
if not defined HLW_WATCH_EVENTS set HLW_WATCH_EVENTS=1
if exist "HogwartsLivingWorld.exe" (
  "HogwartsLivingWorld.exe"
) else (
  py -3 -m hlw
)
pause
