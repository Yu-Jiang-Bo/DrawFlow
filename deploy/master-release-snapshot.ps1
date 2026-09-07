function Enter-MasterReleaseSnapshot {
    param([Parameter(Mandatory = $true)][string]$InvocationRoot)

    $OriginalLocation = (Get-Location).Path
    $ResolvedInvocationRoot = (Resolve-Path -LiteralPath $InvocationRoot).Path
    $InheritedRepositoryRoot = [string]$env:DRAWFLOW_MASTER_REPOSITORY_ROOT
    if ($InheritedRepositoryRoot) {
        $RepositoryRoot = (Resolve-Path -LiteralPath $InheritedRepositoryRoot).Path
        $SourceRoot = (Resolve-Path -LiteralPath $env:DRAWFLOW_MASTER_SNAPSHOT_ROOT).Path
        if (-not $SourceRoot.Equals($ResolvedInvocationRoot, [StringComparison]::OrdinalIgnoreCase)) {
            throw "Nested release packaging must run from the verified master snapshot."
        }
        & (Join-Path $RepositoryRoot "deploy\assert-master-release.ps1") -ProjectRoot $RepositoryRoot
        $SnapshotHead = ([string](& git -C $SourceRoot rev-parse HEAD)).Trim()
        $MasterHead = ([string](& git -C $RepositoryRoot rev-parse master)).Trim()
        & git -C $SourceRoot symbolic-ref --quiet HEAD 2>$null
        if ($LASTEXITCODE -eq 0 -or $SnapshotHead -ne $MasterHead) {
            throw "Nested release source is not the detached snapshot of current master."
        }
        $SnapshotStatus = @(& git -C $SourceRoot status --porcelain=v1 --untracked-files=all)
        if ($LASTEXITCODE -ne 0 -or $SnapshotStatus.Count -gt 0) {
            throw "Nested release source snapshot contains uncommitted files."
        }
        $RepositoryCommonValue = ([string](& git -C $RepositoryRoot rev-parse --git-common-dir)).Trim()
        $RepositoryCommonDir = if ([IO.Path]::IsPathRooted($RepositoryCommonValue)) {
            [IO.Path]::GetFullPath($RepositoryCommonValue)
        } else {
            [IO.Path]::GetFullPath((Join-Path $RepositoryRoot $RepositoryCommonValue))
        }
        $SnapshotCommonValue = ([string](& git -C $SourceRoot rev-parse --git-common-dir)).Trim()
        $SnapshotCommonDir = if ([IO.Path]::IsPathRooted($SnapshotCommonValue)) {
            [IO.Path]::GetFullPath($SnapshotCommonValue)
        } else {
            [IO.Path]::GetFullPath((Join-Path $SourceRoot $SnapshotCommonValue))
        }
        $RegisteredWorktrees = @(& git -C $RepositoryRoot worktree list --porcelain) |
            Where-Object { $_ -like "worktree *" } |
            ForEach-Object { [IO.Path]::GetFullPath($_.Substring(9)) }
        if (
            -not $RepositoryCommonDir.Equals($SnapshotCommonDir, [StringComparison]::OrdinalIgnoreCase) -or
            -not ($RegisteredWorktrees | Where-Object { $_.Equals($SourceRoot, [StringComparison]::OrdinalIgnoreCase) })
        ) {
            throw "Nested release source is not a registered worktree of the master repository."
        }
        return [pscustomobject]@{
            RepositoryRoot = $RepositoryRoot
            SourceRoot = $SourceRoot
            ReleaseBase = (Join-Path $RepositoryRoot "release")
            Head = $SnapshotHead
            OwnsSnapshot = $false
            OriginalLocation = $OriginalLocation
        }
    }

    $RepositoryRoot = $ResolvedInvocationRoot
    & (Join-Path $RepositoryRoot "deploy\assert-master-release.ps1") -ProjectRoot $RepositoryRoot
    $Head = ([string](& git -C $RepositoryRoot rev-parse HEAD)).Trim()
    if ($LASTEXITCODE -ne 0 -or $Head -notmatch '^[0-9a-f]{40,64}$') {
        throw "Unable to resolve the master commit for the release snapshot."
    }

    $ReleaseBase = Join-Path $RepositoryRoot "release"
    New-Item -ItemType Directory -Force -Path $ReleaseBase | Out-Null
    $SnapshotBase = if ($env:DRAWFLOW_RELEASE_SNAPSHOT_BASE) {
        [IO.Path]::GetFullPath($env:DRAWFLOW_RELEASE_SNAPSHOT_BASE)
    } else {
        Join-Path $ReleaseBase ".master-snapshots"
    }
    New-Item -ItemType Directory -Force -Path $SnapshotBase | Out-Null
    $SourceRoot = Join-Path $SnapshotBase ("{0}-{1}" -f $PID, [guid]::NewGuid().ToString("N"))
    & git -C $RepositoryRoot worktree add --detach $SourceRoot $Head | Out-Null
    if ($LASTEXITCODE -ne 0 -or -not (Test-Path -LiteralPath $SourceRoot -PathType Container)) {
        & git -C $RepositoryRoot worktree remove --force $SourceRoot 2>$null | Out-Null
        & git -C $RepositoryRoot worktree prune | Out-Null
        throw "Unable to create the immutable master release snapshot."
    }

    $env:DRAWFLOW_MASTER_REPOSITORY_ROOT = $RepositoryRoot
    $env:DRAWFLOW_MASTER_SNAPSHOT_ROOT = $SourceRoot
    return [pscustomobject]@{
        RepositoryRoot = $RepositoryRoot
        SourceRoot = $SourceRoot
        ReleaseBase = $ReleaseBase
        Head = $Head
        OwnsSnapshot = $true
        OriginalLocation = $OriginalLocation
    }
}

function Exit-MasterReleaseSnapshot {
    param([Parameter(Mandatory = $true)]$Context)

    if (-not $Context.OwnsSnapshot) {
        if (Test-Path -LiteralPath $Context.OriginalLocation -PathType Container) {
            Set-Location -LiteralPath $Context.OriginalLocation
        }
        return
    }
    try {
        Set-Location -LiteralPath $Context.RepositoryRoot
        & git -C $Context.RepositoryRoot worktree remove --force $Context.SourceRoot | Out-Null
        if ($LASTEXITCODE -ne 0) {
            throw "Unable to remove the master release snapshot: $($Context.SourceRoot)"
        }
    } finally {
        Remove-Item Env:DRAWFLOW_MASTER_REPOSITORY_ROOT -ErrorAction SilentlyContinue
        Remove-Item Env:DRAWFLOW_MASTER_SNAPSHOT_ROOT -ErrorAction SilentlyContinue
        if (
            -not ([IO.Path]::GetFullPath($Context.OriginalLocation)).StartsWith(
                [IO.Path]::GetFullPath($Context.SourceRoot),
                [StringComparison]::OrdinalIgnoreCase
            ) -and
            (Test-Path -LiteralPath $Context.OriginalLocation -PathType Container)
        ) {
            Set-Location -LiteralPath $Context.OriginalLocation
        }
    }
}
