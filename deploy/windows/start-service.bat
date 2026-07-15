@echo off
setlocal

set "SCRIPT_DIR=%~dp0"
for %%I in ("%SCRIPT_DIR%..\..") do set "PROJECT_ROOT=%%~fI"
if "%CUSTOM_RENDERER_HOST%"=="" set "CUSTOM_RENDERER_HOST=0.0.0.0"
if "%CUSTOM_RENDERER_PORT%"=="" set "CUSTOM_RENDERER_PORT=8765"

cd /d "%PROJECT_ROOT%"

set "NEED_INSTALL="
if not exist "%PROJECT_ROOT%\.venv\Scripts\python.exe" set "NEED_INSTALL=1"
if not exist "%PROJECT_ROOT%\.venv\.custom-renderer-installed" set "NEED_INSTALL=1"

if defined NEED_INSTALL (
  powershell -ExecutionPolicy Bypass -File "%PROJECT_ROOT%\deploy\windows\install.ps1"
  if errorlevel 1 exit /b %errorlevel%
)

echo Starting Custom Renderer on http://%CUSTOM_RENDERER_HOST%:%CUSTOM_RENDERER_PORT%
"%PROJECT_ROOT%\.venv\Scripts\python.exe" -u -m src.service.http_server --host "%CUSTOM_RENDERER_HOST%" --port "%CUSTOM_RENDERER_PORT%"
