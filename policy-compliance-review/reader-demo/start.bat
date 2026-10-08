@echo off
chcp 65001 >nul
cd /d "%~dp0"

rem ---- 找 Python ----
set "PYCMD="
where py >nul 2>nul && set "PYCMD=py"
if not defined PYCMD (
  where python >nul 2>nul && set "PYCMD=python"
)
if not defined PYCMD (
  echo [错误] 未找到 Python，请先安装 Python 3.10+ 并加入 PATH：https://www.python.org/downloads/
  pause
  exit /b 1
)

rem ---- 安装依赖（首次运行）----
echo 正在检查/安装依赖 lxml、pywin32 ...
"%PYCMD%" -m pip install -r requirements.txt
if errorlevel 1 (
  echo [错误] 依赖安装失败，请检查网络或 pip。
  pause
  exit /b 1
)

rem ---- 启动服务 ----
set "PORT=5173"
if not "%1"=="" set "PORT=%1"
echo.
echo 启动中... 浏览器打开：http://127.0.0.1:%PORT%/
echo （局域网其他电脑可用本机 IP 访问，需放行防火墙该端口）
echo 按 Ctrl+C 停止。
echo.
"%PYCMD%" server.py %PORT%
pause
