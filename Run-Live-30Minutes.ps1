param([Parameter(Mandatory=$true)][string]$Preflight)
$ErrorActionPreference = 'Stop'
Push-Location -LiteralPath $PSScriptRoot
try {
    if (-not $env:OPENAI_API_KEY) { throw 'OPENAI_API_KEY must be present; no key is printed or copied.' }
    & (Join-Path $PSScriptRoot '.venv\Scripts\python.exe') -B -u -X utf8 -m live_experiment.window --approve-paid --approve-thirty-minute --budget-usd 5 --preflight $Preflight
    if ($LASTEXITCODE -ne 0) { throw "Live window stopped/failed: $LASTEXITCODE" }
} finally {
    Pop-Location
}
