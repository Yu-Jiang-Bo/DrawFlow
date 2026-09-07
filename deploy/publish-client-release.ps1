param(
    [Parameter(Mandatory = $true)][string]$DataDir,
    [Parameter(Mandatory = $true)][string]$PayloadPath,
    [Parameter(Mandatory = $true)][string]$ClientVersion,
    [string]$MinimumLauncherVersion = "1.0.0",
    [string]$Notes = ""
)

$ErrorActionPreference = "Stop"
$ProjectRoot = Resolve-Path (Join-Path $PSScriptRoot "..")
& (Join-Path $PSScriptRoot "assert-master-release.ps1") -ProjectRoot $ProjectRoot
if (-not (Test-Path $PayloadPath -PathType Leaf)) { throw "PayloadPath does not exist: $PayloadPath" }
if ($ClientVersion -notmatch '^(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)$') { throw "ClientVersion must be stable SemVer." }
if ($MinimumLauncherVersion -notmatch '^(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)$') { throw "MinimumLauncherVersion must be stable SemVer." }
$VenvPython = Join-Path $ProjectRoot ".venv\Scripts\python.exe"
$Python = if (Test-Path $VenvPython) { $VenvPython } else { "python" }
Set-Location $ProjectRoot
& $Python -m src.client_release_main --data-dir $DataDir --payload $PayloadPath --version $ClientVersion --minimum-launcher-version $MinimumLauncherVersion --notes $Notes
if ($LASTEXITCODE -ne 0) { throw "Client release publish failed; latest manifest was not replaced." }
