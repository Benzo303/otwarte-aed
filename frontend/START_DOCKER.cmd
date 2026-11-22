@echo off
call "%~dp0..\START_DOCKER.cmd" %*
exit /b %ERRORLEVEL%
