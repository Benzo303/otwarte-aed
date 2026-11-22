@echo off
rem Uruchamia projekt z katalogu nadrzednego niezaleznie od katalogu terminala.
call "%~dp0..\START_AED.cmd" %*
exit /b %ERRORLEVEL%
