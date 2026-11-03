$ErrorActionPreference = 'Stop'
Set-Location $PSScriptRoot
$Host.UI.RawUI.WindowTitle = 'TrustKernel research monitor — no trading authority'
Write-Host "TrustKernel: $PSScriptRoot" -ForegroundColor Cyan
Write-Host 'Local viewer: http://127.0.0.1:8765'
Write-Host 'Offline smoke uses scripted responses; no Sol/Terra inference or API cost.'
Write-Host 'Paid and three-hour runs require explicit approval. Ctrl+C closes monitoring.'
Write-Host ''
if (Test-Path tests.log) { Get-Content tests.log -Tail 5 }
Write-Host ''
Write-Host 'Latest smoke event log:'
$tkActiveLog = if (Test-Path "$PSScriptRoot/thirty-minute.log") { "$PSScriptRoot/thirty-minute.log" } elseif (Test-Path "$PSScriptRoot/paid-smoke.log") { "$PSScriptRoot/paid-smoke.log" } else { "$PSScriptRoot/smoke.log" }
Get-Content -LiteralPath $tkActiveLog -Tail 20 -Wait
