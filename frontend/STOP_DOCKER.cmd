@echo off
call "%~dp0..\STOP_DOCKER.cmd" %*
exit /b %ERRORLEVEL%
