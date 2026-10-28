# Keeps the local API listening for IIS. The scheduled task runs this script.
# Python is restarted here if it exits, and output is appended to deploy\iis\api*.log.
$ErrorActionPreference = 'Continue'
$Root = Split-Path -Parent $PSScriptRoot
Set-Location $Root
$env:PYTHONDONTWRITEBYTECODE = '1'

$py = Join-Path $Root '.venv\Scripts\python.exe'
$embed = Join-Path $env:LOCALAPPDATA 'Programs\Python\Python312-embed\python.exe'
if (-not (Test-Path $py) -and (Test-Path $embed)) {
  $py = $embed
}
$run = Join-Path $Root 'scripts\run_api.py'
$logDir = Join-Path $Root 'deploy\iis'
New-Item -ItemType Directory -Force -Path $logDir | Out-Null
$outLog = Join-Path $logDir 'api.log'
$errLog = Join-Path $logDir 'api.err.log'

while ($true) {
  $stamp = Get-Date -Format 'yyyy-MM-dd HH:mm:ss'
  Add-Content -Path $errLog -Value "$stamp API host starting $py"
  & cmd.exe /c "`"$py`" `"$run`" >> `"$outLog`" 2>> `"$errLog`""
  $code = $LASTEXITCODE
  Add-Content -Path $errLog -Value "$(Get-Date -Format 'yyyy-MM-dd HH:mm:ss') API host exited $code"
  Start-Sleep -Seconds 3
}
