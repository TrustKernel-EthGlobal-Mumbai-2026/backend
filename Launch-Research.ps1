param(
  [switch]$PaidSmoke,
  [switch]$ApprovePaid,
  [switch]$ApproveThreeHour,
  [double]$BudgetUsd = 5
)
$ErrorActionPreference = 'Stop'
Set-Location $PSScriptRoot
if (-not $ApprovePaid -or $BudgetUsd -le 0) {
  throw 'Approval required: inspect README.md and provide -ApprovePaid -BudgetUsd <approved ceiling>.'
}
if (-not $env:OPENAI_API_KEY) { throw 'OPENAI_API_KEY must be set in this shell. No credentials are auto-loaded.' }
$tkArgs = @('-u','-m','trustkernel.experiment','--mode','paid','--approve-paid','--budget-usd', "$BudgetUsd")
if (-not $PaidSmoke) {
  if (-not $ApproveThreeHour) { throw 'Three-hour research requires -ApproveThreeHour and a successful paid smoke.' }
  $tkArgs += @('--hours','3','--approve-three-hour')
}
& "$PSScriptRoot/.venv/Scripts/python.exe" @tkArgs
exit $LASTEXITCODE
