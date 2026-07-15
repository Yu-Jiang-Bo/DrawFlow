$ErrorActionPreference = "Stop"

$Port = if ($env:CUSTOM_RENDERER_PORT) { [int]$env:CUSTOM_RENDERER_PORT } else { 8765 }
$Listeners = Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue

if (-not $Listeners) {
    Write-Host "No Custom Renderer listener found on port $Port"
    exit 0
}

$Pids = $Listeners | Select-Object -ExpandProperty OwningProcess -Unique
$RendererPids = @()
foreach ($PidValue in $Pids) {
    $ProcessInfo = Get-CimInstance Win32_Process -Filter "ProcessId = $PidValue" -ErrorAction SilentlyContinue
    $CommandLine = if ($ProcessInfo) { [string]$ProcessInfo.CommandLine } else { "" }
    if ($CommandLine -notmatch "src\.service\.http_server") {
        Write-Host "Port $Port is used by PID $PidValue, but it is not Custom Renderer. Skipping."
        continue
    }
    $RendererPids += $PidValue
}

if (-not $RendererPids) {
    throw "No Custom Renderer process found on port $Port; refusing to stop unrelated process."
}

foreach ($PidValue in $RendererPids) {
    Stop-Process -Id $PidValue -Force
    Write-Host "Stopped PID $PidValue on port $Port"
}
