$ErrorActionPreference = "Stop"

$ProjectRoot = Resolve-Path (Join-Path $PSScriptRoot "..\..")
$Python = Join-Path $ProjectRoot ".venv\Scripts\python.exe"
$InstallMarker = Join-Path $ProjectRoot ".venv\.drawflow-installed"
$LegacyInstallMarker = Join-Path $ProjectRoot ".venv\.custom-renderer-installed"
$HostName = if ($env:DRAWFLOW_HOST) { $env:DRAWFLOW_HOST } elseif ($env:CUSTOM_RENDERER_HOST) { $env:CUSTOM_RENDERER_HOST } else { "0.0.0.0" }
$Port = if ($env:DRAWFLOW_PORT) { [int]$env:DRAWFLOW_PORT } elseif ($env:CUSTOM_RENDERER_PORT) { [int]$env:CUSTOM_RENDERER_PORT } else { 8765 }
$LogDir = Join-Path $ProjectRoot "output\logs"
$StdoutLog = Join-Path $LogDir "drawflow.log"
$StderrLog = Join-Path $LogDir "drawflow.error.log"

Set-Location $ProjectRoot
New-Item -ItemType Directory -Force -Path $LogDir | Out-Null

if ((-not (Test-Path $Python)) -or ((-not (Test-Path $InstallMarker)) -and (-not (Test-Path $LegacyInstallMarker)))) {
    & powershell -ExecutionPolicy Bypass -File (Join-Path $ProjectRoot "deploy\windows\install.ps1")
    if ($LASTEXITCODE -ne 0) {
        throw "Install failed; DrawFlow was not started."
    }
}

$Listeners = Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue
if ($Listeners) {
    $Pids = ($Listeners | Select-Object -ExpandProperty OwningProcess -Unique) -join ", "
    throw "Port $Port is already in use by PID(s): $Pids"
}

$Process = Start-Process `
    -FilePath $Python `
    -ArgumentList @("-u", "-m", "src.service.http_server", "--role", "central", "--host", $HostName, "--port", $Port) `
    -WorkingDirectory $ProjectRoot `
    -RedirectStandardOutput $StdoutLog `
    -RedirectStandardError $StderrLog `
    -WindowStyle Hidden `
    -PassThru

Write-Host "Started DrawFlow central PID=$($Process.Id)"
Write-Host "URL: http://$HostName`:$Port"
Write-Host "Logs: $StdoutLog and $StderrLog"
Write-Host "For startup logs, run deploy\windows\start-service.bat in foreground."
