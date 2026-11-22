@echo off
setlocal EnableExtensions DisableDelayedExpansion
set "AED_DOCKER=docker"
pushd "%~dp0" >nul 2>&1
if errorlevel 1 exit /b 1
where docker >nul 2>&1
if not errorlevel 1 goto stop_container
if exist "%ProgramFiles%\Docker\Docker\resources\bin\docker.exe" (
  set "AED_DOCKER=%ProgramFiles%\Docker\Docker\resources\bin\docker.exe"
  goto stop_container
)
if exist "%LOCALAPPDATA%\Programs\DockerDesktop\resources\bin\docker.exe" (
  set "AED_DOCKER=%LOCALAPPDATA%\Programs\DockerDesktop\resources\bin\docker.exe"
  goto stop_container
)
echo Brak Docker Desktop.
popd
exit /b 1

:stop_container
"%AED_DOCKER%" compose --project-directory "%CD%" -f "%CD%\compose.yaml" down
set "AED_EXIT=%ERRORLEVEL%"
if not "%AED_EXIT%"=="0" if /I not "%~1"=="--no-browser" pause
popd
exit /b %AED_EXIT%
