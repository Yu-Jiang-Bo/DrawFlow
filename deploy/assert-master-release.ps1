param(
    [Parameter(Mandatory = $true)][string]$ProjectRoot
)

$ErrorActionPreference = "Stop"
$ResolvedProjectRoot = (Resolve-Path -LiteralPath $ProjectRoot).Path

$RepositoryRoot = & git -C $ResolvedProjectRoot rev-parse --show-toplevel
if ($LASTEXITCODE -ne 0 -or -not $RepositoryRoot) {
    throw "Release packaging requires a Git repository."
}
$RepositoryRoot = [IO.Path]::GetFullPath(([string]$RepositoryRoot).Trim())
if (-not $RepositoryRoot.Equals($ResolvedProjectRoot, [StringComparison]::OrdinalIgnoreCase)) {
    throw "Release packaging must run from the repository root: $ResolvedProjectRoot"
}

$Branch = & git -C $ResolvedProjectRoot symbolic-ref --quiet --short HEAD
if ($LASTEXITCODE -ne 0 -or ([string]$Branch).Trim() -ne "master") {
    $ActualBranch = if ($Branch) { ([string]$Branch).Trim() } else { "detached HEAD" }
    throw "Release packaging is allowed only from master; current branch is $ActualBranch."
}

$WorkingTreeStatus = @(& git -C $ResolvedProjectRoot status --porcelain=v1 --untracked-files=all)
if ($LASTEXITCODE -ne 0) {
    throw "Unable to verify the repository working tree before release packaging."
}
if ($WorkingTreeStatus.Count -gt 0) {
    throw "Release packaging requires a clean master with no uncommitted files."
}

$Head = & git -C $ResolvedProjectRoot rev-parse HEAD
if ($LASTEXITCODE -ne 0 -or -not $Head) {
    throw "Unable to resolve the master commit for release packaging."
}
Write-Host "Release source verified: master@$(([string]$Head).Trim())"
