param(
    [Parameter(Mandatory = $true)][string]$ClientVersion
)

$ErrorActionPreference = "Stop"

if ($ClientVersion -notmatch '^(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)$') {
    throw "ClientVersion must be a stable SemVer value such as 1.2.3."
}

. (Join-Path $PSScriptRoot "master-release-snapshot.ps1")
$ReleaseContext = Enter-MasterReleaseSnapshot -InvocationRoot (Join-Path $PSScriptRoot "..")
$ProjectRoot = $ReleaseContext.SourceRoot
$ReleaseBase = $ReleaseContext.ReleaseBase
try {
$PayloadRoot = Join-Path $ReleaseBase ".client-payload-$ClientVersion"
$BuildRoot = Join-Path $ReleaseBase ".client-build"
$DistRoot = Join-Path $ReleaseBase ".client-dist"
$VenvPython = Join-Path $ProjectRoot ".venv\Scripts\python.exe"
$Python = if (Test-Path $VenvPython) { $VenvPython } else { "python" }

New-Item -ItemType Directory -Force -Path $ReleaseBase | Out-Null
if (Test-Path $PayloadRoot) {
    Remove-Item -LiteralPath $PayloadRoot -Recurse -Force
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

$DataSeparator = [IO.Path]::PathSeparator
$PyInstallerArgs = @(
    "--noconfirm",
    "--clean",
    "--onedir",
    "--name", "DrawFlowClient",
    "--paths", $ProjectRoot,
    "--distpath", $DistRoot,
    "--workpath", $BuildRoot,
    "--specpath", $BuildRoot,
    "--add-data", ((Join-Path $ProjectRoot "scripts\\illustrator") + $DataSeparator + "scripts\\illustrator"),
    "--add-data", ((Join-Path $ProjectRoot "src\\service\\static\\v2-workbench") + $DataSeparator + "src\\service\\static\\v2-workbench"),
    "--add-data", ((Join-Path $ProjectRoot "src\\service\\v2_workbench_page_head.py") + $DataSeparator + "src\\service"),
    "--add-data", ((Join-Path $ProjectRoot "src\\service\\v2_workbench_page_main.py") + $DataSeparator + "src\\service"),
    "--add-data", ((Join-Path $ProjectRoot "src\\service\\v2_workbench_page_finish.py") + $DataSeparator + "src\\service"),
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

New-Item -ItemType Directory -Force -Path $PayloadRoot | Out-Null
Copy-Item -Recurse -Path (Join-Path $BuiltApp "*") -Destination $PayloadRoot

function Assert-CleanClientRelease {
    $TextExtensions = @(".bat", ".json", ".jsx", ".md", ".py", ".txt")
    $TextFiles = Get-ChildItem -Path $PayloadRoot -Recurse -File |
        Where-Object { $TextExtensions -contains $_.Extension.ToLowerInvariant() }

    $RegexPatterns = @(
        ("-----BEGIN " + "(?:RSA |EC |OPENSSH )?PRIVATE KEY-----"),
        "C:\\Users",
        "C:/Users",
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

$SourceCommit = ([string](& git -C $ProjectRoot rev-parse HEAD)).Trim()
$SourceTree = ([string](& git -C $ProjectRoot rev-parse 'HEAD^{tree}')).Trim()
if ($LASTEXITCODE -ne 0 -or $SourceCommit -notmatch '^[0-9a-f]{40,64}$' -or $SourceTree -notmatch '^[0-9a-f]{40,64}$') {
    throw "Unable to record the verified master source for the client payload."
}
$SourceMetadata = [ordered]@{
    schema = "drawflow/client-build-source/v1"
    branch = "master"
    commit = $SourceCommit
    tree = $SourceTree
    version = $ClientVersion
    minimum_launcher_version = "1.0.0"
}
[System.IO.File]::WriteAllText(
    (Join-Path $PayloadRoot "drawflow-release-source.json"),
    ($SourceMetadata | ConvertTo-Json -Depth 3) + [Environment]::NewLine,
    [System.Text.UTF8Encoding]::new($false)
)

Assert-CleanClientRelease

$PayloadPath = Join-Path $ReleaseBase "drawflow-client-$ClientVersion.payload.zip"
if (Test-Path $PayloadPath) {
    Remove-Item -LiteralPath $PayloadPath -Force
}
Compress-ArchiveWithRetry -Source (Join-Path $PayloadRoot "*") -Destination $PayloadPath
$PayloadHash = (Get-FileHash -LiteralPath $PayloadPath -Algorithm SHA256).Hash.ToLowerInvariant()
$PayloadManifest = [ordered]@{
    schema = "drawflow/client-release/v1"
    channel = "stable"
    version = $ClientVersion
    minimum_launcher_version = "1.0.0"
    source = [ordered]@{
        branch = "master"
        commit = $SourceCommit
        tree = $SourceTree
    }
    artifact = [ordered]@{
        payload_file = (Split-Path -Leaf $PayloadPath)
        sha256 = $PayloadHash
        size = (Get-Item -LiteralPath $PayloadPath).Length
    }
}
$PayloadManifestPath = Join-Path $ReleaseBase "drawflow-client-$ClientVersion.release.json"
[System.IO.File]::WriteAllText(
    $PayloadManifestPath,
    ($PayloadManifest | ConvertTo-Json -Depth 4) + [Environment]::NewLine,
    [System.Text.UTF8Encoding]::new($false)
)

Write-Host "Internal payload folder: $PayloadRoot"
Write-Host "Client payload: $PayloadPath"
Write-Host "Client payload SHA256: $PayloadHash"
} finally {
    Exit-MasterReleaseSnapshot -Context $ReleaseContext
}
