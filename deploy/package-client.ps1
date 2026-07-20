param(
    [string]$ReleaseName = "",
    [string]$CentralUrl = "http://162.14.120.240:8765",
    [switch]$NoArchive
)

$ErrorActionPreference = "Stop"

$ProjectRoot = Resolve-Path (Join-Path $PSScriptRoot "..")
if (-not $ReleaseName) {
    $ReleaseName = "drawflow-client-{0}" -f (Get-Date -Format "yyyyMMdd-HHmm")
}

$ReleaseBase = Join-Path $ProjectRoot "release"
$ReleaseRoot = Join-Path $ReleaseBase $ReleaseName
$ArchivePath = Join-Path $ReleaseBase "$ReleaseName.zip"
$BuildRoot = Join-Path $ReleaseBase ".client-build"
$DistRoot = Join-Path $ReleaseBase ".client-dist"
$VenvPython = Join-Path $ProjectRoot ".venv\Scripts\python.exe"
$Python = if (Test-Path $VenvPython) { $VenvPython } else { "python" }
$ParsedCentralUri = $null
if (
    -not [Uri]::TryCreate($CentralUrl.Trim(), [UriKind]::Absolute, [ref]$ParsedCentralUri) -or
    $ParsedCentralUri.Scheme -notin @("http", "https") -or
    -not $ParsedCentralUri.Host
) {
    throw "CentralUrl must be an absolute HTTP(S) URL: $CentralUrl"
}

New-Item -ItemType Directory -Force -Path $ReleaseBase | Out-Null
if (Test-Path $ReleaseRoot) {
    throw "Release folder already exists: $ReleaseRoot"
}
if (Test-Path $BuildRoot) {
    Remove-Item -LiteralPath $BuildRoot -Recurse -Force
}
if (Test-Path $DistRoot) {
    Remove-Item -LiteralPath $DistRoot -Recurse -Force
}

Set-Location $ProjectRoot
& $Python -m PyInstaller --version | Out-Null
if ($LASTEXITCODE -ne 0) {
    throw "PyInstaller is required. Install it in the build environment, then rerun deploy\package-client.ps1."
}

$DataSeparator = ":"
$PyInstallerArgs = @(
    "--noconfirm",
    "--clean",
    "--onedir",
    "--name", "DrawFlowClient",
    "--paths", $ProjectRoot,
    "--distpath", $DistRoot,
    "--workpath", $BuildRoot,
    "--specpath", $BuildRoot,
    "--add-data", ((Join-Path $ProjectRoot "scripts") + $DataSeparator + "scripts"),
    "--add-data", ((Join-Path $ProjectRoot "config") + $DataSeparator + "config"),
    "--collect-submodules", "src",
    "deploy\client\DrawFlowClient.py"
)

& $Python -m PyInstaller @PyInstallerArgs
if ($LASTEXITCODE -ne 0) {
    throw "PyInstaller failed."
}

$BuiltApp = Join-Path $DistRoot "DrawFlowClient"
if (-not (Test-Path (Join-Path $BuiltApp "DrawFlowClient.exe"))) {
    throw "DrawFlowClient.exe was not produced."
}

New-Item -ItemType Directory -Force -Path $ReleaseRoot | Out-Null
Copy-Item -Recurse -Path (Join-Path $BuiltApp "*") -Destination $ReleaseRoot
Copy-Item (Join-Path $ProjectRoot "deploy\client\drawflow-client.example.json") (Join-Path $ReleaseRoot "drawflow-client.example.json")
Copy-Item (Join-Path $ProjectRoot "deploy\client\start-client.bat") (Join-Path $ReleaseRoot "start-client.bat")
Copy-Item (Join-Path $ProjectRoot "deploy\client\README-CLIENT.md") (Join-Path $ReleaseRoot "README-CLIENT.md")
$ClientConfigPath = Join-Path $ReleaseRoot "drawflow-client.json"
$ClientConfigJson = [ordered]@{ central_url = $CentralUrl.TrimEnd("/") } | ConvertTo-Json
[System.IO.File]::WriteAllText($ClientConfigPath, $ClientConfigJson + [Environment]::NewLine, [System.Text.UTF8Encoding]::new($false))

function Assert-CleanClientRelease {
    $PackagedConfig = Get-Content -Raw -Encoding UTF8 $ClientConfigPath | ConvertFrom-Json
    if ($PackagedConfig.central_url -ne $CentralUrl.TrimEnd("/")) {
        throw "Client release central_url mismatch: $($PackagedConfig.central_url)"
    }
    $TextExtensions = @(".bat", ".json", ".md", ".py", ".txt")
    $TextFiles = Get-ChildItem -Path $ReleaseRoot -Recurse -File |
        Where-Object { $TextExtensions -contains $_.Extension.ToLowerInvariant() }

    $RegexPatterns = @(
        ("-----BEGIN " + "(?:RSA |EC |OPENSSH )?PRIVATE KEY-----"),
        ("\b" + "s" + "k-" + "[A-Za-z0-9_-]{16,}\b"),
        '(?im)^\s*(?:password|passwd|pwd|secret|access_token|refresh_token)\s*[:=]\s*["'']?(?!\$|<|YOUR_|REPLACE_)[^\s"'']{12,}'
    )
    foreach ($Pattern in $RegexPatterns) {
        $Matches = $TextFiles | Select-String -Pattern $Pattern -ErrorAction SilentlyContinue
        if ($Matches) {
            $First = $Matches | Select-Object -First 1
            throw "Client release secret scan failed in $($First.Path):$($First.LineNumber)"
        }
    }
}

function Compress-ArchiveWithRetry {
    param(
        [Parameter(Mandatory = $true)][string]$Source,
        [Parameter(Mandatory = $true)][string]$Destination
    )

    $LastError = $null
    for ($Attempt = 1; $Attempt -le 4; $Attempt++) {
        try {
            Compress-Archive -Path $Source -DestinationPath $Destination -CompressionLevel Optimal
            return
        }
        catch {
            $LastError = $_
            Start-Sleep -Seconds (2 * $Attempt)
        }
    }
    throw $LastError
}

Assert-CleanClientRelease

if (-not $NoArchive) {
    if (Test-Path $ArchivePath) {
        Remove-Item -LiteralPath $ArchivePath -Force
    }
    Compress-ArchiveWithRetry -Source (Join-Path $ReleaseRoot "*") -Destination $ArchivePath
}

Write-Host "Client folder: $ReleaseRoot"
if (-not $NoArchive) {
    Write-Host "Client archive: $ArchivePath"
}
