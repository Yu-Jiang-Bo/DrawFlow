param(
    [string]$ReleaseName = "",
    [switch]$NoArchive
)

$ErrorActionPreference = "Stop"
$ProjectRoot = Resolve-Path (Join-Path $PSScriptRoot "..")
if (-not $ReleaseName) {
    $ReleaseName = "drawflow-central-linux-{0}" -f (Get-Date -Format "yyyyMMdd-HHmm")
}

$ReleaseBase = Join-Path $ProjectRoot "release"
$ReleaseRoot = Join-Path $ReleaseBase $ReleaseName
$ArchivePath = Join-Path $ReleaseBase "$ReleaseName.zip"
New-Item -ItemType Directory -Force -Path $ReleaseBase | Out-Null
if (Test-Path $ReleaseRoot) { throw "Release folder already exists: $ReleaseRoot" }
New-Item -ItemType Directory -Force -Path $ReleaseRoot | Out-Null

function Copy-Tree {
    param(
        [Parameter(Mandatory = $true)][string]$RelativePath,
        [string[]]$ExcludeFiles = @()
    )
    $Source = Join-Path $ProjectRoot $RelativePath
    $Target = Join-Path $ReleaseRoot $RelativePath
    if (-not (Test-Path $Source)) { throw "Missing source path: $Source" }
    New-Item -ItemType Directory -Force -Path $Target | Out-Null
    $RoboCopyArgs = @($Source, $Target, "/E", "/NFL", "/NDL", "/NJH", "/NJS", "/NP", "/XD", "__pycache__", "/XF", "*.pyc")
    if ($ExcludeFiles.Count -gt 0) {
        $RoboCopyArgs += $ExcludeFiles
    }
    & robocopy @RoboCopyArgs | Out-Null
    if ($LASTEXITCODE -gt 7) { throw "robocopy failed for ${RelativePath}: $LASTEXITCODE" }
    $global:LASTEXITCODE = 0
}

Copy-Tree "src" -ExcludeFiles @("local_client.py", "local_gateway.py")
Copy-Tree "config"
Copy-Tree "templates"
Copy-Tree "deploy\linux"
Copy-Item (Join-Path $ProjectRoot "requirements.txt") (Join-Path $ReleaseRoot "requirements.txt")
Copy-Item (Join-Path $ProjectRoot "deploy\README-LINUX.md") (Join-Path $ReleaseRoot "README-LINUX.md")

$RequiredOutputFiles = @(
    "output/template-configs/JJMB202603281027102517/template.config.json",
    "output/template-named/JJMB202509231236046265/curved-title-mark-report.json"
)
foreach ($RelativeFile in $RequiredOutputFiles) {
    $Source = Join-Path $ProjectRoot $RelativeFile
    if (-not (Test-Path $Source)) { throw "Missing required runtime file: $Source" }
    $Target = Join-Path $ReleaseRoot $RelativeFile
    New-Item -ItemType Directory -Force -Path (Split-Path -Parent $Target) | Out-Null
    Copy-Item $Source $Target
}

function Sanitize-ReleaseJson {
    foreach ($File in (Get-ChildItem -Path $ReleaseRoot -Recurse -File -Filter "*.json")) {
        $Text = Get-Content -Raw -Encoding UTF8 $File.FullName
        $Text = [regex]::Replace($Text, '("(?:source_ai|scan_path|input_ai|output_ai|output_json)"\s*:\s*")[^"]*(")', '$1$2')
        [System.IO.File]::WriteAllText($File.FullName, $Text, [System.Text.UTF8Encoding]::new($false))
    }
}

function Assert-CleanRelease {
    $TextFiles = Get-ChildItem -Path $ReleaseRoot -Recurse -File |
        Where-Object { $_.Extension.ToLowerInvariant() -in @(".json", ".md", ".py", ".sh", ".txt") }
    $ForbiddenPatterns = @(
        ("C:" + "\\" + "Users"),
        ("C:" + "/" + "Users"),
        ("root" + "@"),
        ("162" + ".14" + ".120" + ".240")
    )
    foreach ($Pattern in $ForbiddenPatterns) {
        $Matches = $TextFiles | Select-String -Pattern $Pattern -SimpleMatch -ErrorAction SilentlyContinue
        if ($Matches) {
            $First = $Matches | Select-Object -First 1
            throw "Linux release privacy check failed: '$Pattern' in $($First.Path):$($First.LineNumber)"
        }
    }
    $SecretPatterns = @(
        ("-----BEGIN " + "(?:RSA |EC |OPENSSH )?PRIVATE KEY-----"),
        ("\b" + "sk-" + "[A-Za-z0-9_-]{16,}\b"),
        '(?im)^\s*(?:password|passwd|pwd|secret|access_token|refresh_token)\s*[:=]\s*["'']?(?!\$|<|YOUR_|REPLACE_)[^\s"'']{12,}'
    )
    foreach ($Pattern in $SecretPatterns) {
        $Matches = $TextFiles | Select-String -Pattern $Pattern -ErrorAction SilentlyContinue
        if ($Matches) {
            $First = $Matches | Select-Object -First 1
            throw "Linux release secret scan failed in $($First.Path):$($First.LineNumber)"
        }
    }
}

Sanitize-ReleaseJson
Assert-CleanRelease

if (-not $NoArchive) {
    if (Test-Path $ArchivePath) { Remove-Item -LiteralPath $ArchivePath -Force }
    Compress-Archive -Path (Join-Path $ReleaseRoot "*") -DestinationPath $ArchivePath -CompressionLevel Optimal
}

Write-Host "Linux release folder: $ReleaseRoot"
if (-not $NoArchive) { Write-Host "Linux release archive: $ArchivePath" }
