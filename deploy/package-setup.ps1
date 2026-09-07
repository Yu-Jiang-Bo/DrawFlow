param(
    [Parameter(Mandatory = $true)][string]$ClientVersion,
    [Parameter(Mandatory = $true)][string]$CentralUrl,
    [Parameter(Mandatory = $true)][string]$UpdateBaseUrl,
    [string]$ReleaseName = ""
)

$ErrorActionPreference = "Stop"
if ($ClientVersion -notmatch '^(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)$') { throw "ClientVersion must be stable SemVer." }
$centralUri = $null
if (
    -not [Uri]::TryCreate($CentralUrl, [UriKind]::Absolute, [ref]$centralUri) -or
    $centralUri.Scheme -notin @("http", "https") -or
    $centralUri.UserInfo -or
    $centralUri.Query -or
    $centralUri.Fragment
) { throw "CentralUrl must be an absolute HTTP(S) URL without embedded credentials, query, or fragment." }
$updateUri = $null
if (
    -not [Uri]::TryCreate($UpdateBaseUrl, [UriKind]::Absolute, [ref]$updateUri) -or
    $updateUri.Scheme -ne "https" -or
    $updateUri.UserInfo -or
    $updateUri.Query -or
    $updateUri.Fragment
) { throw "UpdateBaseUrl must be absolute HTTPS without embedded credentials, query, or fragment." }

. (Join-Path $PSScriptRoot "master-release-snapshot.ps1")
$ReleaseContext = Enter-MasterReleaseSnapshot -InvocationRoot (Join-Path $PSScriptRoot "..")
$ProjectRoot = $ReleaseContext.SourceRoot
$ReleaseBase = $ReleaseContext.ReleaseBase
. (Join-Path $PSScriptRoot "release-path-guards.ps1")
try {
if (-not $ReleaseName) { $ReleaseName = "DrawFlow-Setup-$ClientVersion" }
$InstallerPath = Resolve-SafeReleaseChildPath -BaseDirectory $ReleaseBase -Name "$ReleaseName.exe" -Label "ReleaseName"
$StageRoot = Join-Path $ReleaseBase ".setup-stage-$ClientVersion"
$InstallerScript = Join-Path $ProjectRoot "deploy\installer\DrawFlow.iss"
$Iscc = (Get-Command iscc.exe -ErrorAction SilentlyContinue).Source
if (-not $Iscc) {
    $candidates = @("$env:ProgramFiles(x86)\Inno Setup 6\ISCC.exe", "$env:ProgramFiles\Inno Setup 6\ISCC.exe")
    $Iscc = $candidates | Where-Object { Test-Path $_ } | Select-Object -First 1
}
if (-not $Iscc) { throw "Inno Setup 6 (ISCC.exe) is required to generate DrawFlow-Setup.exe. Install it on the build machine and rerun this command." }

& (Join-Path $ProjectRoot "deploy\package-client.ps1") -ClientVersion $ClientVersion
if ($LASTEXITCODE -ne 0) { throw "Client payload build failed." }
& (Join-Path $ProjectRoot "deploy\package-launcher.ps1") -ReleaseName "drawflow-launcher-$ClientVersion"
if ($LASTEXITCODE -ne 0) { throw "Launcher build failed." }

$ClientRoot = Join-Path $ReleaseBase ".client-payload-$ClientVersion"
$LauncherRoot = Join-Path $ReleaseBase "drawflow-launcher-$ClientVersion"
if (-not (Test-Path (Join-Path $ClientRoot "DrawFlowClient.exe"))) { throw "Client payload is missing DrawFlowClient.exe." }
if (-not (Test-Path (Join-Path $LauncherRoot "DrawFlow.exe"))) { throw "Launcher build is missing DrawFlow.exe." }
if (Test-Path $StageRoot) { Remove-Item -LiteralPath $StageRoot -Recurse -Force }
New-Item -ItemType Directory -Force -Path (Join-Path $StageRoot "versions\$ClientVersion") | Out-Null
Copy-Item -LiteralPath (Join-Path $LauncherRoot "DrawFlow.exe") -Destination (Join-Path $StageRoot "DrawFlow.exe")
Copy-Item -LiteralPath (Join-Path $ClientRoot "DrawFlowClient.exe") -Destination (Join-Path $StageRoot "versions\$ClientVersion\DrawFlowClient.exe")
Copy-Item -LiteralPath (Join-Path $ClientRoot "_internal") -Destination (Join-Path $StageRoot "versions\$ClientVersion\_internal") -Recurse
$launcherConfig = [ordered]@{ central_url = $CentralUrl.TrimEnd("/"); update_base_url = $UpdateBaseUrl.TrimEnd("/"); allow_insecure_loopback_update = $false } | ConvertTo-Json
$activeState = [ordered]@{ schema = "drawflow/launcher-state/v1"; active_version = $ClientVersion; previous_version = "" } | ConvertTo-Json
[System.IO.File]::WriteAllText((Join-Path $StageRoot "drawflow-launcher.json"), $launcherConfig + [Environment]::NewLine, [System.Text.UTF8Encoding]::new($false))
[System.IO.File]::WriteAllText((Join-Path $StageRoot "active.json"), $activeState + [Environment]::NewLine, [System.Text.UTF8Encoding]::new($false))

& $Iscc "/DClientVersion=$ClientVersion" "/DStageDir=$StageRoot" "/DOutputDir=$ReleaseBase" "/DOutputName=$ReleaseName" $InstallerScript
if ($LASTEXITCODE -ne 0) { throw "Inno Setup failed to generate the initial installer." }
if (-not (Test-Path $InstallerPath)) { throw "DrawFlow initial installer was not produced." }
Write-Host "Initial installer: $InstallerPath"
} finally {
    Exit-MasterReleaseSnapshot -Context $ReleaseContext
}
