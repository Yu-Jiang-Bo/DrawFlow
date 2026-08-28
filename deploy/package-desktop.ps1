param(
    [Parameter(Mandatory = $true)][string]$ClientVersion,
    [Parameter(Mandatory = $true)][string]$CentralUrl
)

$ErrorActionPreference = "Stop"
if ($ClientVersion -notmatch '^(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)$') {
    throw "ClientVersion must be a stable SemVer value such as 1.2.3."
}
$centralUri = $null
if (
    -not [Uri]::TryCreate($CentralUrl, [UriKind]::Absolute, [ref]$centralUri) -or
    $centralUri.Scheme -notin @("http", "https") -or
    $centralUri.UserInfo -or
    $centralUri.Query -or
    $centralUri.Fragment
) {
    throw "CentralUrl must be an absolute HTTP(S) URL without embedded credentials, query, or fragment."
}

$ProjectRoot = Resolve-Path (Join-Path $PSScriptRoot "..")
$ReleaseBase = Join-Path $ProjectRoot "release"
$DesktopRoot = Join-Path $ProjectRoot "desktop"
$ClientReleaseName = ".desktop-client-$ClientVersion"
$ClientReleaseRoot = Join-Path $ReleaseBase $ClientReleaseName
$ClientStageRoot = Join-Path $DesktopRoot "build\client"
$OutputRoot = Join-Path $ReleaseBase "desktop-$ClientVersion"

if (-not (Get-Command npm.cmd -ErrorAction SilentlyContinue)) {
    throw "Node.js and npm are required to package DrawFlow Desktop."
}
if (-not (Test-Path (Join-Path $DesktopRoot "node_modules\electron-builder"))) {
    throw "Desktop dependencies are missing. Run npm ci from the desktop directory first."
}
if (Test-Path $OutputRoot) {
    throw "Desktop release folder already exists: $OutputRoot"
}

& (Join-Path $ProjectRoot "deploy\package-client.ps1") -ReleaseName $ClientReleaseName -CentralUrl $CentralUrl
if ($LASTEXITCODE -ne 0) {
    throw "PyInstaller local gateway build failed."
}
if (-not (Test-Path (Join-Path $ClientReleaseRoot "DrawFlowClient.exe"))) {
    throw "PyInstaller did not produce DrawFlowClient.exe."
}

if (Test-Path $ClientStageRoot) {
    Remove-Item -LiteralPath $ClientStageRoot -Recurse -Force
}
New-Item -ItemType Directory -Force -Path $ClientStageRoot | Out-Null
Copy-Item -LiteralPath (Join-Path $ClientReleaseRoot "DrawFlowClient.exe") -Destination $ClientStageRoot
Copy-Item -LiteralPath (Join-Path $ClientReleaseRoot "_internal") -Destination (Join-Path $ClientStageRoot "_internal") -Recurse
Copy-Item -LiteralPath (Join-Path $ClientReleaseRoot "drawflow-client.json") -Destination $ClientStageRoot

Push-Location $DesktopRoot
try {
    & npm.cmd run check
    if ($LASTEXITCODE -ne 0) { throw "Electron syntax check failed." }
    & npm.cmd run build:win -- "--config.extraMetadata.version=$ClientVersion" "--config.directories.output=$OutputRoot"
    if ($LASTEXITCODE -ne 0) { throw "electron-builder failed to generate the Windows installer." }
}
finally {
    Pop-Location
}

$InstallerPath = Join-Path $OutputRoot "DrawFlow-Setup-$ClientVersion.exe"
if (-not (Test-Path $InstallerPath)) {
    throw "DrawFlow desktop installer was not produced: $InstallerPath"
}
Write-Host "Desktop installer: $InstallerPath"
