@echo off
setlocal EnableExtensions DisableDelayedExpansion
rem Dziala z dowolnego folderu: sciezka pochodzi z polozenia tego pliku.
set "AED_ROOT=%~dp0"
set "AED_PYTHON=%~dp0.venv\Scripts\python.exe"
set "AED_RESULT=1"
pushd "%AED_ROOT%" >nul 2>&1
if errorlevel 1 goto missing_folder
if not exist "%AED_PYTHON%" goto missing_environment
echo Otwarte AED - generowanie prezentacji
echo Folder: "%AED_ROOT%"
"%AED_PYTHON%" "%AED_ROOT%docs\generuj_prezentacje_otwarte_aed.py"
if errorlevel 1 goto failed
"%AED_PYTHON%" "%AED_ROOT%docs\spakuj_materialy.py"
if errorlevel 1 goto failed
echo.
echo Gotowe: docs\prezentacja_otwarte_aed.pptx
echo Gotowe: docs\prezentacja_otwarte_aed.pdf
set "AED_RESULT=0"
goto finish
:missing_environment
echo Brak lokalnego srodowiska .venv. Uruchom najpierw START_AED.cmd.
goto finish
:failed
echo.
echo Generowanie nie powiodlo sie. Sprawdz komunikat powyzej.
goto finish
:missing_folder
echo Nie mozna otworzyc folderu projektu.
if /I not "%~1"=="--bez-pauzy" pause
exit /b 1
:finish
popd
if /I not "%~1"=="--bez-pauzy" pause
exit /b %AED_RESULT%
