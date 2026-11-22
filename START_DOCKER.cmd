@echo off
setlocal EnableExtensions DisableDelayedExpansion
set "AED_DOCKER=docker"
set "AED_EXIT=1"
pushd "%~dp0" >nul 2>&1
if errorlevel 1 exit /b 1

where docker >nul 2>&1
if not errorlevel 1 goto check_engine
if exist "%ProgramFiles%\Docker\Docker\resources\bin\docker.exe" (
  set "AED_DOCKER=%ProgramFiles%\Docker\Docker\resources\bin\docker.exe"
  goto check_engine
)
if exist "%LOCALAPPDATA%\Programs\DockerDesktop\resources\bin\docker.exe" (
  set "AED_DOCKER=%LOCALAPPDATA%\Programs\DockerDesktop\resources\bin\docker.exe"
  goto check_engine
)
echo Brak Docker Desktop. Zainstaluj go i uruchom przed ponownym startem.
echo Instrukcja: https://docs.docker.com/desktop/setup/install/windows-install/
goto failed

:check_engine
"%AED_DOCKER%" info >nul 2>&1
if errorlevel 1 (
  echo Uruchom Docker Desktop i poczekaj na gotowosc silnika Linux.
  goto failed
)
"%AED_DOCKER%" compose version >nul 2>&1
if errorlevel 1 (
  echo Wymagany Docker Compose v2 dostepny w aktualnym Docker Desktop.
  goto failed
)
echo Budowanie i uruchamianie Otwarte AED w Dockerze...
"%AED_DOCKER%" compose --project-directory "%CD%" -f "%CD%\compose.yaml" up -d --build --wait --wait-timeout 240
if errorlevel 1 goto failed
set "AED_EXIT=0"
echo Gotowe: http://localhost:8080/
echo Zatrzymanie: STOP_DOCKER.cmd. Dane cache pozostaja zachowane.
if /I not "%~1"=="--no-browser" start "" "http://localhost:8080/"
goto finish

:failed
if /I not "%~1"=="--no-browser" pause

:finish
popd
exit /b %AED_EXIT%
