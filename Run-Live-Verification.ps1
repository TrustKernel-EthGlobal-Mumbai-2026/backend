$ErrorActionPreference = 'Stop'
Push-Location -LiteralPath $PSScriptRoot
try {
    & (Join-Path $PSScriptRoot '.venv\Scripts\python.exe') -B -X utf8 -m live_verification.runner
    if ($LASTEXITCODE -ne 0) { throw "Offline live-corpus verification failed with exit code $LASTEXITCODE" }
}
finally {
    Pop-Location
}
