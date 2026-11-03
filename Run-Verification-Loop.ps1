param()
$ErrorActionPreference = 'Stop'
Push-Location -LiteralPath $PSScriptRoot
try {
    Write-Host 'TrustKernel: offline synthetic verification loop. No model/API call or trading execution.'
    & (Join-Path $PSScriptRoot '.venv\Scripts\python.exe') -B -X utf8 -m procedural_loop.runner run
    if ($LASTEXITCODE -ne 0) { throw "Verification loop failed with exit code $LASTEXITCODE" }
} finally {
    Pop-Location
}
