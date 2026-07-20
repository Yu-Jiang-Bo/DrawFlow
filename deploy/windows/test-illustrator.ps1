$ErrorActionPreference = "Stop"

$Illustrator = New-Object -ComObject Illustrator.Application
try {
    try {
        $Illustrator.Visible = $true
    }
    catch {
        Write-Warning "Illustrator COM is available, but Visible could not be changed: $($_.Exception.Message)"
    }
    Write-Host "Illustrator COM OK. Version=$($Illustrator.Version)"
}
finally {
    [void][Runtime.InteropServices.Marshal]::ReleaseComObject($Illustrator)
}
