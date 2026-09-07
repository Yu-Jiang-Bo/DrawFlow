function Resolve-SafeReleaseChildPath {
    param(
        [Parameter(Mandatory = $true)][string]$BaseDirectory,
        [Parameter(Mandatory = $true)][string]$Name,
        [Parameter(Mandatory = $true)][string]$Label
    )

    if ($Name -notmatch '^[A-Za-z0-9][A-Za-z0-9._-]*$') {
        throw "$Label must contain only letters, numbers, dots, underscores, and hyphens."
    }

    $BaseFullPath = [IO.Path]::GetFullPath($BaseDirectory).TrimEnd(
        [IO.Path]::DirectorySeparatorChar,
        [IO.Path]::AltDirectorySeparatorChar
    )
    $CandidatePath = [IO.Path]::GetFullPath((Join-Path $BaseFullPath $Name))
    $RequiredPrefix = $BaseFullPath + [IO.Path]::DirectorySeparatorChar
    if (-not $CandidatePath.StartsWith($RequiredPrefix, [StringComparison]::OrdinalIgnoreCase)) {
        throw "$Label must resolve inside the release directory."
    }
    return $CandidatePath
}
