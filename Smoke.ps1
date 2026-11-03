$ErrorActionPreference = 'Stop'
Set-Location $PSScriptRoot
& "$PSScriptRoot/.venv/Scripts/python.exe" -u -m trustkernel.experiment --mode offline
exit $LASTEXITCODE
