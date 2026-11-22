@echo off
setlocal EnableExtensions DisableDelayedExpansion
if not exist "%~dp0.venv\Scripts\python.exe" (
  echo Brak lokalnego interpretera. Uruchom najpierw START_AED.cmd.
  pause
  exit /b 1
)
"%~dp0.venv\Scripts\python.exe" "%~dp0uruchom_aed.py" --stop
set "AED_EXIT=%ERRORLEVEL%"
if not "%AED_EXIT%"=="0" pause
exit /b %AED_EXIT%
