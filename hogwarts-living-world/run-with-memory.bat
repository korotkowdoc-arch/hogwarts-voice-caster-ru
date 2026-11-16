@echo off
setlocal
cd /d "%~dp0"
echo Hogwarts Living World -- FREE CLOUD MEMORY MODE
echo Use only a Gemini API key from a free-tier project with NO billing enabled.
echo Local limit: 240 new embedding requests per day. Cached text is free.
echo This does not turn on Sonorus Memory by itself; enable it in Sonorus settings.
set "HLW_ENABLE_EMBEDDINGS=1"
call "%~dp0run.bat"
