@echo off
setlocal

set "SCRIPT_DIR=%~dp0"
for %%I in ("%SCRIPT_DIR%..\..") do set "PROJECT_ROOT=%%~fI"
if "%DRAWFLOW_HOST%"=="" set "DRAWFLOW_HOST=%CUSTOM_RENDERER_HOST%"
if "%DRAWFLOW_HOST%"=="" set "DRAWFLOW_HOST=0.0.0.0"
if "%DRAWFLOW_PORT%"=="" set "DRAWFLOW_PORT=%CUSTOM_RENDERER_PORT%"
if "%DRAWFLOW_PORT%"=="" set "DRAWFLOW_PORT=8765"

cd /d "%PROJECT_ROOT%"

set "NEED_INSTALL="
if not exist "%PROJECT_ROOT%\.venv\Scripts\python.exe" set "NEED_INSTALL=1"
if not exist "%PROJECT_ROOT%\.venv\.drawflow-installed" if not exist "%PROJECT_ROOT%\.venv\.custom-renderer-installed" set "NEED_INSTALL=1"

if defined NEED_INSTALL (
  powershell -ExecutionPolicy Bypass -File "%PROJECT_ROOT%\deploy\windows\install.ps1"
  if errorlevel 1 exit /b %errorlevel%
)

echo Starting DrawFlow central service on http://%DRAWFLOW_HOST%:%DRAWFLOW_PORT%
"%PROJECT_ROOT%\.venv\Scripts\python.exe" -u -m src.service.http_server --role central --host "%DRAWFLOW_HOST%" --port "%DRAWFLOW_PORT%"
