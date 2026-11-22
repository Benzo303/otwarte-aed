@echo off
setlocal EnableExtensions DisableDelayedExpansion
call "%~dp0START_AED.cmd" %* --lan
set "AED_EXIT=%ERRORLEVEL%"
if "%AED_EXIT%"=="0" if /I not "%~1"=="--no-browser" (
  echo.
  echo Wpisz wyswietlony ADRES NA TELEFON w przegladarce telefonu.
  echo To okno mozna zamknac; serwer pozostanie uruchomiony.
  pause
)
exit /b %AED_EXIT%
