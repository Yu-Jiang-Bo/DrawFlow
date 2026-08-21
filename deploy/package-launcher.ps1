param(
    [string]$ReleaseName = ""
)

$ErrorActionPreference = "Stop"
$ProjectRoot = Resolve-Path (Join-Path $PSScriptRoot "..")
$ReleaseBase = Join-Path $ProjectRoot "release"
$BuildRoot = Join-Path $ReleaseBase ".launcher-build"
$DistRoot = Join-Path $ReleaseBase ".launcher-dist"
$VenvPython = Join-Path $ProjectRoot ".venv\Scripts\python.exe"
$Python = if (Test-Path $VenvPython) { $VenvPython } else { "python" }
if (-not $ReleaseName) { $ReleaseName = "drawflow-launcher" }
$ReleaseRoot = Join-Path $ReleaseBase $ReleaseName

if (Test-Path $ReleaseRoot) { Remove-Item -LiteralPath $ReleaseRoot -Recurse -Force }
if (Test-Path $BuildRoot) { Remove-Item -LiteralPath $BuildRoot -Recurse -Force }
if (Test-Path $DistRoot) { Remove-Item -LiteralPath $DistRoot -Recurse -Force }

Set-Location $ProjectRoot
& $Python -m PyInstaller --version | Out-Null
if ($LASTEXITCODE -ne 0) { throw "PyInstaller is required to build DrawFlow.exe." }
& $Python -m PyInstaller --noconfirm --clean --onefile --name DrawFlow --paths $ProjectRoot --distpath $DistRoot --workpath $BuildRoot --specpath $BuildRoot --collect-submodules src.launcher deploy\launcher\DrawFlow.py
if ($LASTEXITCODE -ne 0) { throw "PyInstaller failed to build DrawFlow.exe." }
$Launcher = Join-Path $DistRoot "DrawFlow.exe"
if (-not (Test-Path $Launcher)) { throw "DrawFlow.exe was not produced." }
New-Item -ItemType Directory -Force -Path $ReleaseRoot | Out-Null
Copy-Item -LiteralPath $Launcher -Destination (Join-Path $ReleaseRoot "DrawFlow.exe")
Write-Host "Launcher folder: $ReleaseRoot"
