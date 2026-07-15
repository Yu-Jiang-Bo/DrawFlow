$ErrorActionPreference = "Stop"

$ProjectRoot = Resolve-Path (Join-Path $PSScriptRoot "..\..")
$Python = Join-Path $ProjectRoot ".venv\Scripts\python.exe"
$InstallMarker = Join-Path $ProjectRoot ".venv\.custom-renderer-installed"
$HostName = if ($env:CUSTOM_RENDERER_HOST) { $env:CUSTOM_RENDERER_HOST } else { "0.0.0.0" }
$Port = if ($env:CUSTOM_RENDERER_PORT) { [int]$env:CUSTOM_RENDERER_PORT } else { 8765 }
$LogDir = Join-Path $ProjectRoot "output\logs"

Set-Location $ProjectRoot
New-Item -ItemType Directory -Force -Path $LogDir | Out-Null

if ((-not (Test-Path $Python)) -or (-not (Test-Path $InstallMarker))) {
    & powershell -ExecutionPolicy Bypass -File (Join-Path $ProjectRoot "deploy\windows\install.ps1")
    if ($LASTEXITCODE -ne 0) {
        throw "Install failed; Custom Renderer was not started."
    }
}

$Listeners = Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue
if ($Listeners) {
    $Pids = ($Listeners | Select-Object -ExpandProperty OwningProcess -Unique) -join ", "
    throw "Port $Port is already in use by PID(s): $Pids"
}

$StartInfo = New-Object System.Diagnostics.ProcessStartInfo
$StartInfo.FileName = $Python
$StartInfo.Arguments = "-u -m src.service.http_server --host $HostName --port $Port"
$StartInfo.WorkingDirectory = $ProjectRoot
$StartInfo.UseShellExecute = $false
$StartInfo.CreateNoWindow = $true
$Process = [System.Diagnostics.Process]::Start($StartInfo)

Write-Host "Started Custom Renderer PID=$($Process.Id)"
Write-Host "URL: http://$HostName`:$Port"
Write-Host "For startup logs, run deploy\windows\start-service.bat in foreground."
