param(
    [string]$ReleaseName = "",
    [switch]$NoArchive
)

$ErrorActionPreference = "Stop"

. (Join-Path $PSScriptRoot "master-release-snapshot.ps1")
$ReleaseContext = Enter-MasterReleaseSnapshot -InvocationRoot (Join-Path $PSScriptRoot "..")
$ProjectRoot = $ReleaseContext.SourceRoot
$ReleaseBase = $ReleaseContext.ReleaseBase
. (Join-Path $PSScriptRoot "release-path-guards.ps1")
try {
if (-not $ReleaseName) {
    $ReleaseName = "drawflow-central-{0}" -f (Get-Date -Format "yyyyMMdd-HHmm")
}

$ReleaseRoot = Resolve-SafeReleaseChildPath -BaseDirectory $ReleaseBase -Name $ReleaseName -Label "ReleaseName"
$ArchivePath = Resolve-SafeReleaseChildPath -BaseDirectory $ReleaseBase -Name "$ReleaseName.zip" -Label "ReleaseName"

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

Copy-Tree "src" -ExcludeFiles @("*.pyc", "local_client.py", "local_gateway.py")
Copy-Tree "config"
Copy-Tree "templates" -ExcludeDirs @("__pycache__", "onboarding")
$ExternalTemplates = Join-Path $ReleaseContext.RepositoryRoot "templates"
if (Test-Path -LiteralPath $ExternalTemplates -PathType Container) {
    Copy-Item -Path (Join-Path $ExternalTemplates "*") -Destination (Join-Path $ReleaseRoot "templates") -Recurse -Force
}
Copy-Tree "deploy" -ExcludeDirs @("__pycache__", "client") -ExcludeFiles @("*.pyc", "package-client.ps1")

Copy-Item (Join-Path $ProjectRoot "requirements.txt") (Join-Path $ReleaseRoot "requirements.txt")
if (Test-Path (Join-Path $ProjectRoot "pytest.ini")) {
    Copy-Item (Join-Path $ProjectRoot "pytest.ini") (Join-Path $ReleaseRoot "pytest.ini")
}

$RequiredOutputFiles = @(
    "output/template-configs/JJMB202603281027102517/template.config.json",
    "output/template-named/JJMB202509231236046265/curved-title-mark-report.json"
)
foreach ($RelativeFile in $RequiredOutputFiles) {
    $Source = Join-Path $ReleaseContext.RepositoryRoot $RelativeFile
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
    $ForbiddenPaths = @(
        "deploy\client",
        "deploy\package-client.ps1",
        "scripts",
        "src\service\local_client.py",
        "src\service\local_gateway.py"
    )
    foreach ($RelativePath in $ForbiddenPaths) {
        $Path = Join-Path $ReleaseRoot $RelativePath
        if (Test-Path $Path) {
            throw "Central release boundary check failed: $RelativePath must not be included."
        }
    }

    $TextExtensions = @(".bat", ".css", ".html", ".ini", ".js", ".json", ".jsx", ".md", ".ps1", ".py", ".txt")
    $TextFiles = Get-ChildItem -Path $ReleaseRoot -Recurse -File |
        Where-Object { $TextExtensions -contains $_.Extension.ToLowerInvariant() }

    $SimplePatterns = @(
        ("C:" + "\" + "\" + "Users"),
        ("C:" + "/" + "Users"),
        ("/" + "Users" + "/"),
        ("root" + "@"),
        ("162" + ".14" + ".120" + ".240"),
        ("43" + ".139" + ".43" + ".11")
    )
    foreach ($Pattern in $SimplePatterns) {
        $Matches = $TextFiles | Select-String -Pattern $Pattern -SimpleMatch -ErrorAction SilentlyContinue
        if ($Matches) {
            $First = $Matches | Select-Object -First 1
            throw "Release privacy check failed: pattern '$Pattern' found in $($First.Path):$($First.LineNumber)"
        }
    }

    $RegexPatterns = @(
        ("-----BEGIN " + "(?:RSA |EC |OPENSSH )?PRIVATE KEY-----"),
        ("\b" + "s" + "k-" + "[A-Za-z0-9_-]{16,}\b"),
        '(?im)^\s*(?:setx?\s+|\$env:)?(?:DRAWFLOW|CUSTOM_RENDERER)_LLM_API_KEY\s*(?:=|\s)\s*["'']?(?!\$|<|YOUR_|REPLACE_)[A-Za-z0-9+/.=_\-!@#%^&*()]{12,}["'']?\s*$',
        '(?im)^\s*(?:password|passwd|pwd|secret|access_token|refresh_token)\s*[:=]\s*["'']?(?!\$|<|YOUR_|REPLACE_)[^\s"'']{12,}'
    )
    foreach ($Pattern in $RegexPatterns) {
        $Matches = $TextFiles | Select-String -Pattern $Pattern -ErrorAction SilentlyContinue
        if ($Matches) {
            $First = $Matches | Select-Object -First 1
            throw "Release secret scan failed in $($First.Path):$($First.LineNumber)"
        }
    }

    $SensitiveFiles = Get-ChildItem -Path $ReleaseRoot -Recurse -File |
        Where-Object { $_.Name -match '(?i)(^\.env(?:\.|$)|\.(?:pem|pfx|p12|key)$|credentials?|secrets?)' }
    if ($SensitiveFiles) {
        $First = $SensitiveFiles | Select-Object -First 1
        throw "Release secret filename check failed: $($First.FullName)"
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
} finally {
    Exit-MasterReleaseSnapshot -Context $ReleaseContext
}
