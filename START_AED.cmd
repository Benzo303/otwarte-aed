@echo off
setlocal EnableExtensions DisableDelayedExpansion
rem Sciezka zawsze pochodzi z polozenia TEGO pliku, nie z katalogu terminala.
set "AED_ROOT=%~dp0"
set "AED_PYTHON=%~dp0.venv\Scripts\python.exe"
set "AED_EXIT=1"

pushd "%AED_ROOT%" >nul 2>&1
if errorlevel 1 (
  echo Nie mozna otworzyc folderu projektu: "%AED_ROOT%"
  exit /b 1
)
if not exist "%AED_ROOT%uruchom_aed.py" goto missing_project
if not exist "%AED_ROOT%backend\main.py" goto missing_project

echo Otwarte AED
echo Folder projektu: "%AED_ROOT%"
if not exist "%AED_PYTHON%" goto prepare_environment
"%AED_PYTHON%" -c "import sys; assert sys.version_info >= (3, 10)" >nul 2>&1
if errorlevel 1 goto prepare_environment
goto check_packages

:prepare_environment
rem Python systemowy sluzy jedynie do utworzenia lokalnego .venv.
py -3 -c "import sys; assert sys.version_info >= (3, 10)" >nul 2>&1
if not errorlevel 1 (
  set "AED_BASE_PYTHON=py -3"
  goto create_environment
)
python -c "import sys; assert sys.version_info >= (3, 10)" >nul 2>&1
if not errorlevel 1 (
  set "AED_BASE_PYTHON=python"
  goto create_environment
)
echo Brak dzialajacego Python 3.10 lub nowszego.
echo Zainstaluj Python, zaznacz opcje dodania do PATH i uruchom starter ponownie.
goto failed

:create_environment
set "AED_BACKUP=.venv_backup_%RANDOM%_%RANDOM%"
if exist "%AED_ROOT%.venv" (
  rem Zmieniamy tylko nazwe katalogu .venv bezposrednio obok tego startera.
  echo Zachowuje niesprawne srodowisko jako "%AED_BACKUP%".
  ren "%AED_ROOT%.venv" "%AED_BACKUP%"
  if errorlevel 1 goto failed
)
echo Tworzenie lokalnego srodowiska .venv...
%AED_BASE_PYTHON% -m venv "%AED_ROOT%.venv"
if errorlevel 1 goto failed

:check_packages
"%AED_PYTHON%" -c "import fastapi, uvicorn, multipart, requests, openpyxl, lxml, opening_hours, tzdata, reportlab, svglib, pptx, fontTools, pypdf, qrcode, bs4, pdfplumber" >nul 2>&1
if not errorlevel 1 goto launch
echo Instalowanie bibliotek projektu. Pierwsze uruchomienie wymaga internetu.
"%AED_PYTHON%" -m pip install -r "%AED_ROOT%requirements.txt"
if errorlevel 1 goto failed

:launch
"%AED_PYTHON%" "%AED_ROOT%uruchom_aed.py" %*
set "AED_EXIT=%ERRORLEVEL%"
if not "%AED_EXIT%"=="0" goto failed
goto finish

:missing_project
echo Nie znaleziono plikow aplikacji. Przenos caly folder projektu razem ze starterem.

:failed
set "AED_EXIT=1"
echo Uruchomienie nie powiodlo sie. Szczegoly powyzej lub w backend\logs\server.log.
if /I not "%~1"=="--no-browser" pause

:finish
popd
exit /b %AED_EXIT%
