#Requires -RunAsAdministrator
$ErrorActionPreference = 'Continue'
$Root = Split-Path -Parent $PSScriptRoot
$SiteName = 'Cacsms-Traders'
$VenvPy = Join-Path $Root '.venv\Scripts\python.exe'
$RunApi = Join-Path $Root 'scripts\run_api.py'
$Log = Join-Path $Root 'deploy\iis\restart-api.log'

function Say([string]$msg) {
    Write-Host $msg
    Add-Content -Path $Log -Value "$(Get-Date -Format o) $msg"
}

Set-Content -Path $Log -Value "restart started $(Get-Date -Format o)"
Say 'Cacsms-Traders IIS + API restart'

Say 'Stopping listeners on port 8000...'
Get-NetTCPConnection -LocalPort 8000 -State Listen -ErrorAction SilentlyContinue |
    ForEach-Object { Stop-Process -Id $_.OwningProcess -Force -ErrorAction SilentlyContinue }
Start-Sleep -Seconds 2

Say "Recycling IIS app pool / site ($SiteName)..."
$appcmd = Join-Path $env:Windir 'system32\inetsrv\appcmd.exe'
if (Test-Path $appcmd) {
    & $appcmd recycle apppool "/apppool.name:$SiteName" 2>&1 | ForEach-Object { Say $_ }
    & $appcmd start site "/site.name:$SiteName" 2>&1 | ForEach-Object { Say $_ }
} else {
    Say 'appcmd not found; skip IIS recycle'
}

Say 'Starting FastAPI on 127.0.0.1:8000...'
$env:APP_HOST = '127.0.0.1'
$env:APP_PORT = '8000'
Start-Process -FilePath $VenvPy -ArgumentList $RunApi -WorkingDirectory $Root -WindowStyle Hidden

Start-Sleep -Seconds 8
try {
    $health = Invoke-WebRequest -Uri 'http://127.0.0.1:8000/api/health/live' -UseBasicParsing -TimeoutSec 15
    Say "API health HTTP $($health.StatusCode): $($health.Content)"
} catch {
    Say "API health check failed: $($_.Exception.Message)"
    Say 'Wait 30s then try http://127.0.0.1:8000/api/health/live in a browser.'
}

Say 'Done. You can close this window.'
Start-Sleep -Seconds 3
