@echo off
chcp 65001 >nul
call "%~dp0打开斗蛐蛐.bat" --stop
exit /b %errorlevel%
