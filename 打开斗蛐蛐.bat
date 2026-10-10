@echo off
chcp 65001 >nul
setlocal
set "PYTHONUTF8=1"
cd /d "%~dp0"
py -3 -c "import sys; sys.exit(not (sys.version_info >= (3,10)))" >nul 2>&1
if not errorlevel 1 goto run_py
python -c "import sys; sys.exit(not (sys.version_info >= (3,10)))" >nul 2>&1
if not errorlevel 1 goto run_python
echo 未找到 Python 3.10 或更新版本。请安装 Python，并勾选 Add Python to PATH，然后重新打开。
pause
exit /b 1
:run_py
py -3 launch.py %*
goto finish
:run_python
python launch.py %*
:finish
if errorlevel 1 (
  echo 请查看本目录的使用说明.md，或 server.log 中的错误信息。
  pause
  exit /b 1
)
exit /b 0
