$ErrorActionPreference = 'Stop'
Set-Location $PSScriptRoot
if (-not $env:OPENAI_API_KEY) { throw 'OPENAI_API_KEY must be present in this shell.' }
& "$PSScriptRoot/.venv/Scripts/python.exe" -u -m trustkernel.window --approve-paid --approve-thirty-minute --budget-usd 5
exit $LASTEXITCODE
