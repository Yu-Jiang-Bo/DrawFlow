$ErrorActionPreference = "Stop"

$ProjectRoot = Resolve-Path (Join-Path $PSScriptRoot "..\..")
$VenvDir = Join-Path $ProjectRoot ".venv"
$Python = Join-Path $VenvDir "Scripts\python.exe"
$InstallMarker = Join-Path $VenvDir ".custom-renderer-installed"

Set-Location $ProjectRoot

if (-not (Get-Command python -ErrorAction SilentlyContinue)) {
    throw "Python 3 is required. Install Python 3 and make sure 'python' is available in PATH."
}

if (-not (Test-Path $Python)) {
    python -m venv $VenvDir
    if ($LASTEXITCODE -ne 0) {
        throw "Failed to create Python virtual environment."
    }
}

& $Python -m pip install --upgrade pip
if ($LASTEXITCODE -ne 0) {
    throw "Failed to upgrade pip."
}

& $Python -m pip install -r (Join-Path $ProjectRoot "requirements.txt")
if ($LASTEXITCODE -ne 0) {
    throw "Failed to install Python dependencies."
}

Set-Content -Path $InstallMarker -Value (Get-Date -Format "yyyy-MM-dd HH:mm:ss") -Encoding ASCII

New-Item -ItemType Directory -Force -Path (Join-Path $ProjectRoot "output\service-jobs") | Out-Null
New-Item -ItemType Directory -Force -Path (Join-Path $ProjectRoot "output\service-uploads") | Out-Null
New-Item -ItemType Directory -Force -Path (Join-Path $ProjectRoot "output\logs") | Out-Null

Write-Host "Install complete: $ProjectRoot"
