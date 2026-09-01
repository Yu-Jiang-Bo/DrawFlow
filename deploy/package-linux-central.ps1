param(
    [string]$ReleaseName = "",
    [string]$V2TemplateDataPath = "",
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

function Get-ActiveTemplates {
    $RegistryPath = Join-Path $ProjectRoot "config\templates.json"
    if (-not (Test-Path $RegistryPath)) { throw "Missing template registry: $RegistryPath" }
    $Registry = Get-Content -Raw -Encoding UTF8 $RegistryPath | ConvertFrom-Json
    @($Registry.templates | Where-Object { $_.status -eq "active" })
}

function Assert-RequiredAiFile {
    param(
        [Parameter(Mandatory = $true)][string]$PathValue,
        [Parameter(Mandatory = $true)][string]$Label,
        [Parameter(Mandatory = $true)][string]$BasePath
    )
    if ([string]::IsNullOrWhiteSpace($PathValue)) {
        throw "Active template is missing ${Label}."
    }
    if ([System.IO.Path]::GetExtension($PathValue).ToLowerInvariant() -ne ".ai") {
        throw "Active template ${Label} must point to a .ai file: $PathValue"
    }
    $ResolvedPath = if ([System.IO.Path]::IsPathRooted($PathValue)) {
        $PathValue
    } else {
        Join-Path $BasePath $PathValue
    }
    if (-not (Test-Path $ResolvedPath -PathType Leaf)) {
        throw "Active template ${Label} .ai file is missing: $ResolvedPath"
    }
}

function Assert-ActiveTemplateAiFiles {
    param([Parameter(Mandatory = $true)][string]$BasePath)
    foreach ($Template in (Get-ActiveTemplates)) {
        Assert-RequiredAiFile -PathValue ([string]$Template.template_ai) -Label "$($Template.template_id) template_ai" -BasePath $BasePath
        foreach ($Asset in @($Template.assets)) {
            $StoredPath = [string]$Asset.stored_path
            if ($StoredPath -and [System.IO.Path]::GetExtension($StoredPath).ToLowerInvariant() -eq ".ai") {
                Assert-RequiredAiFile -PathValue $StoredPath -Label "$($Template.template_id) asset $($Asset.file_name)" -BasePath $BasePath
            }
        }
    }
}

function Get-ActiveV2TemplateRecords {
    param([Parameter(Mandatory = $true)][string]$DataRoot)
    if (-not (Test-Path -LiteralPath $DataRoot -PathType Container)) {
        if ($V2TemplateDataPath) { throw "V2 template data path does not exist: $DataRoot" }
        return @()
    }

    $records = @()
    foreach ($TemplateDirectory in (Get-ChildItem -LiteralPath $DataRoot -Directory)) {
        $StatePath = Join-Path $TemplateDirectory.FullName "state.json"
        if (-not (Test-Path -LiteralPath $StatePath -PathType Leaf)) { continue }
        $State = Get-Content -LiteralPath $StatePath -Raw -Encoding UTF8 | ConvertFrom-Json
        $Publication = $State.publication
        if ($Publication.status -ne "active") { continue }
        $VersionNames = @($State.versions | ForEach-Object { [string]$_.version } | Where-Object { $_ })
        $CurrentVersion = [string]$Publication.current_version
        if (-not $CurrentVersion -or $VersionNames -notcontains $CurrentVersion) {
            throw "Active V2 template $($TemplateDirectory.Name) has no valid current version."
        }
        foreach ($VersionName in $VersionNames) {
            if ($VersionName -notmatch '^v\d{4}$') {
                throw "V2 template version name is invalid: $VersionName"
            }
        }
        $DraftRevision = [string]$State.draft.revision
        if ($DraftRevision -and $DraftRevision -notmatch '^d\d{4}$') {
            throw "V2 template draft revision is invalid: $DraftRevision"
        }
        $records += [pscustomobject]@{
            TemplateId = $TemplateDirectory.Name
            SourceDirectory = $TemplateDirectory.FullName
            Versions = $VersionNames
            DraftRevision = $DraftRevision
        }
    }
    return @($records)
}

function Resolve-V2ChildPath {
    param(
        [Parameter(Mandatory = $true)][string]$BaseDirectory,
        [Parameter(Mandatory = $true)][string]$RelativePath,
        [Parameter(Mandatory = $true)][string]$Label
    )
    if ([IO.Path]::IsPathRooted($RelativePath)) {
        throw "V2 template ${Label} must be a relative path."
    }
    $BaseFullPath = [IO.Path]::GetFullPath($BaseDirectory).TrimEnd([IO.Path]::DirectorySeparatorChar, [IO.Path]::AltDirectorySeparatorChar)
    $CandidatePath = [IO.Path]::GetFullPath((Join-Path $BaseFullPath $RelativePath))
    $RequiredPrefix = $BaseFullPath + [IO.Path]::DirectorySeparatorChar
    if (-not $CandidatePath.StartsWith($RequiredPrefix, [StringComparison]::OrdinalIgnoreCase)) {
        throw "V2 template ${Label} escapes its template directory."
    }
    return $CandidatePath
}

function Assert-V2VersionAiFiles {
    param(
        [Parameter(Mandatory = $true)][string]$TemplateDirectory,
        [Parameter(Mandatory = $true)][string]$Version
    )
    if ($Version -notmatch '^v\d{4}$') { throw "V2 template version name is invalid: $Version" }
    $VersionDirectory = Resolve-V2ChildPath -BaseDirectory $TemplateDirectory -RelativePath (Join-Path "versions" $Version) -Label "version directory"
    $ManifestPath = Join-Path $VersionDirectory "manifest.json"
    if (-not (Test-Path -LiteralPath $ManifestPath -PathType Leaf)) {
        throw "V2 template version manifest is missing: $VersionDirectory"
    }
    $Manifest = Get-Content -LiteralPath $ManifestPath -Raw -Encoding UTF8 | ConvertFrom-Json
    $AiAssets = @($Manifest.assets | Where-Object { [IO.Path]::GetExtension([string]$_.path).ToLowerInvariant() -eq ".ai" })
    if ($AiAssets.Count -eq 0) {
        throw "V2 template version has no .ai template asset: $VersionDirectory"
    }
    foreach ($Asset in $AiAssets) {
        $RelativePath = ([string]$Asset.path).Replace("/", [IO.Path]::DirectorySeparatorChar)
        $AssetPath = Resolve-V2ChildPath -BaseDirectory $VersionDirectory -RelativePath $RelativePath -Label "asset path"
        if (-not (Test-Path -LiteralPath $AssetPath -PathType Leaf)) {
            throw "V2 template .ai asset is missing: $AssetPath"
        }
    }
}

function Copy-ActiveV2TemplateData {
    param(
        [Parameter(Mandatory = $true)][object[]]$Records,
        [Parameter(Mandatory = $true)][string]$TargetDataRoot
    )
    foreach ($Record in $Records) {
        foreach ($Version in $Record.Versions) {
            Assert-V2VersionAiFiles -TemplateDirectory $Record.SourceDirectory -Version $Version
        }
        $TargetDirectory = Join-Path $TargetDataRoot $Record.TemplateId
        New-Item -ItemType Directory -Force -Path $TargetDirectory | Out-Null
        Copy-Item -LiteralPath (Join-Path $Record.SourceDirectory "state.json") -Destination (Join-Path $TargetDirectory "state.json")
        foreach ($Version in $Record.Versions) {
            $SourceVersionDirectory = Resolve-V2ChildPath -BaseDirectory $Record.SourceDirectory -RelativePath (Join-Path "versions" $Version) -Label "source version directory"
            $TargetVersionDirectory = Resolve-V2ChildPath -BaseDirectory $TargetDirectory -RelativePath (Join-Path "versions" $Version) -Label "target version directory"
            New-Item -ItemType Directory -Force -Path $TargetVersionDirectory | Out-Null
            Copy-Item -Path (Join-Path $SourceVersionDirectory "*") -Destination $TargetVersionDirectory -Recurse
        }
        if ($Record.DraftRevision) {
            $DraftDirectory = Resolve-V2ChildPath -BaseDirectory $Record.SourceDirectory -RelativePath (Join-Path "drafts" $Record.DraftRevision) -Label "source draft directory"
            if (-not (Test-Path -LiteralPath $DraftDirectory -PathType Container)) {
                throw "Active V2 template draft is missing: $DraftDirectory"
            }
            $TargetDraftDirectory = Resolve-V2ChildPath -BaseDirectory $TargetDirectory -RelativePath (Join-Path "drafts" $Record.DraftRevision) -Label "target draft directory"
            New-Item -ItemType Directory -Force -Path $TargetDraftDirectory | Out-Null
            Copy-Item -Path (Join-Path $DraftDirectory "*") -Destination $TargetDraftDirectory -Recurse
        }
    }
}

function Normalize-LinuxShellScripts {
    foreach ($File in (Get-ChildItem -Path (Join-Path $ReleaseRoot "deploy\linux") -Recurse -File -Filter "*.sh")) {
        $Text = [System.IO.File]::ReadAllText($File.FullName)
        $Text = $Text -replace "`r`n", "`n"
        $Text = $Text -replace "`r", "`n"
        [System.IO.File]::WriteAllText($File.FullName, $Text, [System.Text.UTF8Encoding]::new($false))
    }
}

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

Assert-ActiveTemplateAiFiles -BasePath $ProjectRoot
$DefaultV2DataRoot = Join-Path $ProjectRoot "drawflow-data\v2-templates"
$SourceV2DataRoot = if ($V2TemplateDataPath) { (Resolve-Path -LiteralPath $V2TemplateDataPath).Path } else { $DefaultV2DataRoot }
$ActiveV2TemplateRecords = Get-ActiveV2TemplateRecords -DataRoot $SourceV2DataRoot
New-Item -ItemType Directory -Force -Path $ReleaseRoot | Out-Null

Copy-Tree "src" -ExcludeFiles @("local_client.py", "local_gateway.py", "local_scan_client.py")
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

if ($ActiveV2TemplateRecords.Count -gt 0) {
    $ReleaseV2DataRoot = Join-Path $ReleaseRoot "drawflow-data\v2-templates"
    New-Item -ItemType Directory -Force -Path $ReleaseV2DataRoot | Out-Null
    Copy-ActiveV2TemplateData -Records $ActiveV2TemplateRecords -TargetDataRoot $ReleaseV2DataRoot
    foreach ($Record in $ActiveV2TemplateRecords) {
        foreach ($Version in $Record.Versions) {
            Assert-V2VersionAiFiles -TemplateDirectory (Join-Path $ReleaseV2DataRoot $Record.TemplateId) -Version $Version
        }
    }
}

function Sanitize-ReleaseJson {
    foreach ($File in (Get-ChildItem -Path $ReleaseRoot -Recurse -File -Filter "*.json")) {
        if ($File.FullName.StartsWith((Join-Path $ReleaseRoot "drawflow-data"), [StringComparison]::OrdinalIgnoreCase)) {
            continue
        }
        $Text = Get-Content -Raw -Encoding UTF8 $File.FullName
        $Text = [regex]::Replace($Text, '("(?:source_ai|scan_path|input_ai|output_ai|output_json)"\s*:\s*")[^"]*(")', '$1$2')
        [System.IO.File]::WriteAllText($File.FullName, $Text, [System.Text.UTF8Encoding]::new($false))
    }
}

function Assert-CleanRelease {
    $ForbiddenPaths = @(
        "src\service\local_client.py",
        "src\service\local_gateway.py",
        "src\service\local_scan_client.py"
    )
    foreach ($RelativePath in $ForbiddenPaths) {
        $Path = Join-Path $ReleaseRoot $RelativePath
        if (Test-Path -LiteralPath $Path) {
            throw "Central release boundary check failed: $RelativePath must not be included."
        }
    }

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

Normalize-LinuxShellScripts
Assert-ActiveTemplateAiFiles -BasePath $ReleaseRoot
Sanitize-ReleaseJson
Assert-CleanRelease

if (-not $NoArchive) {
    if (Test-Path $ArchivePath) { Remove-Item -LiteralPath $ArchivePath -Force }
    Compress-Archive -Path (Join-Path $ReleaseRoot "*") -DestinationPath $ArchivePath -CompressionLevel Optimal
}

Write-Host "Linux release folder: $ReleaseRoot"
Write-Host "Bundled active V2 templates: $($ActiveV2TemplateRecords.Count)"
if (-not $NoArchive) { Write-Host "Linux release archive: $ArchivePath" }
