$ErrorActionPreference = 'Stop'
Set-Location $PSScriptRoot
$tkLog = Get-ChildItem -LiteralPath "$PSScriptRoot/runs" -Filter console.log -Recurse | Sort-Object LastWriteTime -Descending | Select-Object -First 1
if (-not $tkLog) { throw 'Run Smoke.ps1 first.' }
Write-Host "Watching $($tkLog.FullName). Ctrl+C to stop."
Get-Content -LiteralPath $tkLog.FullName -Tail 25 -Wait
