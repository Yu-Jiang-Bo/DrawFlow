param(
    [string]$BaseUrl = "",
    [string]$Model = "deepseek-v4-pro"
)

$ErrorActionPreference = "Stop"

if (-not $BaseUrl) {
    $BaseUrl = Read-Host "DeepSeek relay base URL"
}
if (-not $BaseUrl) {
    throw "DeepSeek relay base URL is required."
}

$SecureKey = Read-Host "DeepSeek relay API key" -AsSecureString
$KeyPointer = [Runtime.InteropServices.Marshal]::SecureStringToBSTR($SecureKey)
try {
    $ApiKey = [Runtime.InteropServices.Marshal]::PtrToStringBSTR($KeyPointer)
}
finally {
    [Runtime.InteropServices.Marshal]::ZeroFreeBSTR($KeyPointer)
}

if ([string]::IsNullOrWhiteSpace($ApiKey)) {
    throw "DeepSeek relay API key is required."
}

$Settings = @{
    DRAWFLOW_LLM_API_KEY = $ApiKey
    DRAWFLOW_LLM_BASE_URL = $BaseUrl.Trim()
    DRAWFLOW_LLM_MODEL = $Model.Trim()
}

foreach ($Name in $Settings.Keys) {
    [Environment]::SetEnvironmentVariable($Name, $Settings[$Name], "User")
    [Environment]::SetEnvironmentVariable($Name, $Settings[$Name], "Process")
}

$ApiKey = $null
Write-Host "DrawFlow LLM settings saved for $env:USERNAME. Restart DrawFlow to apply them."
