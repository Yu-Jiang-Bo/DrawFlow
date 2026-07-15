param(
    [string]$ReleaseName = "",
    [switch]$NoArchive
)

$ErrorActionPreference = "Stop"

$ProjectRoot = Resolve-Path (Join-Path $PSScriptRoot "..")
if (-not $ReleaseName) {
    $ReleaseName = "custom-renderer-windows-{0}" -f (Get-Date -Format "yyyyMMdd-HHmm")
}

$ReleaseBase = Join-Path $ProjectRoot "release"
$ReleaseRoot = Join-Path $ReleaseBase $ReleaseName
$ArchivePath = Join-Path $ReleaseBase "$ReleaseName.zip"

New-Item -ItemType Directory -Force -Path $ReleaseBase | Out-Null
if (Test-Path $ReleaseRoot) {
    throw "Release folder already exists: $ReleaseRoot"
}
New-Item -ItemType Directory -Force -Path $ReleaseRoot | Out-Null

function Copy-Tree {
    param(
        [Parameter(Mandatory = $true)][string]$RelativePath,
        [string[]]$ExcludeDirs = @("__pycache__"),
        [string[]]$ExcludeFiles = @("*.pyc")
    )

    $Source = Join-Path $ProjectRoot $RelativePath
    $Target = Join-Path $ReleaseRoot $RelativePath
    if (-not (Test-Path $Source)) {
        throw "Missing source path: $Source"
    }

    New-Item -ItemType Directory -Force -Path $Target | Out-Null
    $args = @($Source, $Target, "/E", "/NFL", "/NDL", "/NJH", "/NJS", "/NP")
    if ($ExcludeDirs.Count -gt 0) {
        $args += "/XD"
        $args += $ExcludeDirs
    }
    if ($ExcludeFiles.Count -gt 0) {
        $args += "/XF"
        $args += $ExcludeFiles
    }
    & robocopy @args | Out-Null
    if ($LASTEXITCODE -gt 7) {
        throw "robocopy failed for $RelativePath with exit code $LASTEXITCODE"
    }
    $global:LASTEXITCODE = 0
}

Copy-Tree "src"
Copy-Tree "config"
Copy-Tree "templates" -ExcludeDirs @("__pycache__", "onboarding")
Copy-Tree "deploy"

Copy-Item (Join-Path $ProjectRoot "requirements.txt") (Join-Path $ReleaseRoot "requirements.txt")
if (Test-Path (Join-Path $ProjectRoot "pytest.ini")) {
    Copy-Item (Join-Path $ProjectRoot "pytest.ini") (Join-Path $ReleaseRoot "pytest.ini")
}

$RuntimeIllustratorScripts = @(
    "export_202508_config.jsx",
    "export_template_config.jsx",
    "inspect_rule_pack.jsx",
    "render_202508_grouped.jsx",
    "render_202509_curved.jsx",
    "render_config_grouped_text_sheet.jsx",
    "render_generic_rule_pack.jsx",
    "render_template_text.jsx",
    "render_template_text_sheet.jsx",
    "render_text.jsx",
    "report_ai_sizes.jsx"
)
$ScriptTarget = Join-Path $ReleaseRoot "scripts\illustrator"
New-Item -ItemType Directory -Force -Path $ScriptTarget | Out-Null
foreach ($ScriptName in $RuntimeIllustratorScripts) {
    $Source = Join-Path $ProjectRoot "scripts\illustrator\$ScriptName"
    if (-not (Test-Path $Source)) {
        throw "Missing Illustrator runtime script: $Source"
    }
    Copy-Item $Source (Join-Path $ScriptTarget $ScriptName)
}

$RequiredOutputFiles = @(
    "output/template-configs/JJMB202603281027102517/template.config.json",
    "output/template-named/JJMB202509231236046265/curved-title-mark-report.json"
)
foreach ($RelativeFile in $RequiredOutputFiles) {
    $Source = Join-Path $ProjectRoot $RelativeFile
    if (-not (Test-Path $Source)) {
        throw "Missing required runtime file: $Source"
    }
    $Target = Join-Path $ReleaseRoot $RelativeFile
    New-Item -ItemType Directory -Force -Path (Split-Path -Parent $Target) | Out-Null
    Copy-Item $Source $Target
}

New-Item -ItemType Directory -Force -Path (Join-Path $ReleaseRoot "output/service-jobs") | Out-Null
New-Item -ItemType Directory -Force -Path (Join-Path $ReleaseRoot "output/service-uploads") | Out-Null
New-Item -ItemType Directory -Force -Path (Join-Path $ReleaseRoot "output/logs") | Out-Null

function Sanitize-ReleaseJson {
    $JsonFiles = Get-ChildItem -Path $ReleaseRoot -Recurse -File -Filter "*.json"
    foreach ($File in $JsonFiles) {
        $Text = Get-Content -Raw -Encoding UTF8 $File.FullName
        $Text = [regex]::Replace(
            $Text,
            '("(?:source_ai|scan_path|input_ai|output_ai|output_json)"\s*:\s*")[^"]*(")',
            '$1$2'
        )
        [System.IO.File]::WriteAllText(
            $File.FullName,
            $Text,
            [System.Text.UTF8Encoding]::new($false)
        )
    }
}

function Assert-CleanRelease {
    $Patterns = @(
        ("C:" + "\" + "\" + "Users"),
        ("C:" + "/" + "Users"),
        ("/" + "Users" + "/"),
        ("root" + "@"),
        ("162" + ".14" + ".120" + ".240")
    )
    foreach ($Pattern in $Patterns) {
        $Matches = Get-ChildItem -Path $ReleaseRoot -Recurse -File |
            Select-String -Pattern $Pattern -SimpleMatch -ErrorAction SilentlyContinue
        if ($Matches) {
            $First = $Matches | Select-Object -First 1
            throw "Release privacy check failed: pattern '$Pattern' found in $($First.Path):$($First.LineNumber)"
        }
    }
}

Sanitize-ReleaseJson
Assert-CleanRelease

if (-not $NoArchive) {
    if (Test-Path $ArchivePath) {
        Remove-Item -LiteralPath $ArchivePath -Force
    }
    Compress-Archive -Path (Join-Path $ReleaseRoot "*") -DestinationPath $ArchivePath -CompressionLevel Optimal
}

Write-Host "Release folder: $ReleaseRoot"
if (-not $NoArchive) {
    Write-Host "Release archive: $ArchivePath"
}
