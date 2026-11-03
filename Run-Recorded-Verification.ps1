param()
$ErrorActionPreference = 'Stop'
Push-Location -LiteralPath $PSScriptRoot
try {
    Write-Host 'TrustKernel: read-only recorded-log verification replay. No new model call or historical rewrite.'
    & (Join-Path $PSScriptRoot '.venv\Scripts\python.exe') -B -X utf8 -m recorded_loop.runner run
    if ($LASTEXITCODE -ne 0) { throw "Recorded verification replay failed: $LASTEXITCODE" }
} finally {
    Pop-Location
}
