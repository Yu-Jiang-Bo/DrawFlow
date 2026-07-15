$ErrorActionPreference = "Stop"

$HostName = if ($env:CUSTOM_RENDERER_HEALTH_HOST) { $env:CUSTOM_RENDERER_HEALTH_HOST } else { "127.0.0.1" }
$Port = if ($env:CUSTOM_RENDERER_PORT) { [int]$env:CUSTOM_RENDERER_PORT } else { 8765 }
$Url = "http://$HostName`:$Port/api/health"

$Response = Invoke-RestMethod -Uri $Url -Method Get -TimeoutSec 10
if (-not $Response.ok) {
    throw "Health check failed: $($Response | ConvertTo-Json -Compress)"
}

Write-Host "Health OK: $Url"
