#Requires -RunAsAdministrator
<#
.SYNOPSIS
  Creates or updates a local IIS site for Cacsms-Traders (static UI + /api reverse proxy).

.DESCRIPTION
  1. Enables ARR reverse proxy (if ARR is installed).
  2. Creates app pool + site pointing at deploy/iis/site (run scripts/build-iis.ps1 first).
  3. Registers a startup scheduled task to run the FastAPI backend on 127.0.0.1:8000.

.PARAMETER SiteName
  IIS site name (default: Cacsms-Traders).

.PARAMETER Port
  HTTP port for the site (default: 8080).

.PARAMETER HostHeader
  Optional host header (e.g. cacsms-traders.local). Empty = any host on the port.

.PARAMETER ApiPort
  Port for uvicorn (default: 8000).

.EXAMPLE
  .\scripts\setup-iis.ps1
  .\scripts\setup-iis.ps1 -Port 80 -HostHeader cacsms-traders.local
#>
[CmdletBinding()]
param(
  [string] $SiteName = 'Cacsms-Traders',
  [int] $Port = 8080,
  [string] $HostHeader = '',
  [int] $ApiPort = 8000
)

$ErrorActionPreference = 'Stop'
$Root = Split-Path -Parent $PSScriptRoot
$SiteDir = Join-Path $Root 'deploy\iis\site'
$TaskName = 'CacsmsTradersApi'
$VenvPy = Join-Path $Root '.venv\Scripts\python.exe'
$RunApi = Join-Path $Root 'scripts\run_api.py'

Import-Module WebAdministration -ErrorAction Stop

if (-not (Test-Path (Join-Path $SiteDir 'index.html'))) {
  Write-Host 'Site folder missing - building frontend...'
  & (Join-Path $Root 'scripts\build-iis.ps1')
}

$rewriteDll = Join-Path $env:Windir 'System32\inetsrv\rewrite.dll'
if (-not (Test-Path $rewriteDll)) {
  throw 'IIS URL Rewrite is not installed. Install it from https://www.iis.net/downloads/microsoft/url-rewrite'
}

$arrDir = Join-Path ${env:ProgramFiles} 'IIS\Application Request Routing'
if (Test-Path $arrDir) {
  Write-Host 'Enabling ARR reverse proxy...'
  & "$env:Windir\system32\inetsrv\appcmd.exe" set config -section:system.webServer/proxy /enabled:"True" /commit:apphost | Out-Null
} else {
  Write-Warning 'Application Request Routing (ARR) not found. Install ARR 3.0 for /api reverse proxy to work.'
}

$poolName = $SiteName
if (-not (Test-Path "IIS:\AppPools\$poolName")) {
  Write-Host "Creating app pool $poolName ..."
  New-WebAppPool -Name $poolName | Out-Null
  Set-ItemProperty "IIS:\AppPools\$poolName" -Name managedRuntimeVersion -Value ''
  Set-ItemProperty "IIS:\AppPools\$poolName" -Name startMode -Value 'AlwaysRunning'
}

$binding = "*:${Port}:"
if ($HostHeader) {
  $binding = "*:${Port}:$HostHeader"
}

$existing = Get-Website -Name $SiteName -ErrorAction SilentlyContinue
if ($existing) {
  Write-Host "Updating site $SiteName ..."
  Set-ItemProperty "IIS:\Sites\$SiteName" -Name physicalPath -Value $SiteDir
  Set-ItemProperty "IIS:\Sites\$SiteName" -Name applicationPool -Value $poolName
} else {
  Write-Host "Creating site $SiteName on $binding ..."
  New-Website -Name $SiteName -PhysicalPath $SiteDir -Port $Port -HostHeader $HostHeader -ApplicationPool $poolName | Out-Null
}

# Patch API upstream port in web.config if not 8000
$webConfigPath = Join-Path $SiteDir 'web.config'
if ($ApiPort -ne 8000 -and (Test-Path $webConfigPath)) {
  $xml = Get-Content $webConfigPath -Raw
  $xml = $xml -replace '127\.0\.0\.1:8000', "127.0.0.1:$ApiPort"
  Set-Content -Path $webConfigPath -Value $xml -Encoding UTF8
}

if (-not (Test-Path $VenvPy)) {
  Write-Host 'Creating Python virtual environment...'
  Push-Location $Root
  py -3 -m venv .venv
  & $VenvPy -m pip install -r (Join-Path $Root 'apps\api\requirements.txt')
  & $VenvPy (Join-Path $Root 'scripts\init_db.py')
  Pop-Location
} elseif (-not (Test-Path (Join-Path $Root 'database\db_cacsms-traders.db'))) {
  & $VenvPy (Join-Path $Root 'scripts\init_db.py')
}

Write-Host 'Registering API startup task...'
$actionArgs = "`"$RunApi`""
$action = New-ScheduledTaskAction -Execute $VenvPy -Argument $actionArgs -WorkingDirectory $Root
$trigger = New-ScheduledTaskTrigger -AtStartup
$settings = New-ScheduledTaskSettingsSet -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries -StartWhenAvailable -RestartCount 3 -RestartInterval (New-TimeSpan -Minutes 1)
$principal = New-ScheduledTaskPrincipal -UserId $env:USERNAME -LogonType Interactive -RunLevel Highest
Register-ScheduledTask -TaskName $TaskName -Action $action -Trigger $trigger -Settings $settings -Principal $principal -Force | Out-Null

$envFile = Join-Path $Root '.env'
if (-not (Test-Path $envFile)) {
  $origin = if ($HostHeader) { "http://${HostHeader}:$Port" } else { "http://localhost:$Port" }
  @(
    'APP_ENV=development'
    'APP_HOST=127.0.0.1'
    "APP_PORT=$ApiPort"
    "WEB_ORIGINS=$origin"
    '# Leave API_PROXY_SECRET unset for local IIS unless you add x-ct-proxy-secret in web.config.'
  ) | Set-Content -Path $envFile -Encoding UTF8
  Write-Host "Created $envFile - review credentials before production use."
}

Write-Host 'Starting API (background)...'
$env:APP_HOST = '127.0.0.1'
$env:APP_PORT = "$ApiPort"
Start-Process -FilePath $VenvPy -ArgumentList $RunApi -WorkingDirectory $Root -WindowStyle Hidden

Start-Website -Name $SiteName

$url = if ($HostHeader) { "http://${HostHeader}:$Port" } else { "http://localhost:$Port" }
Write-Host ''
Write-Host 'Cacsms-Traders IIS setup complete.'
Write-Host "  Site:  $url"
Write-Host "  API:   http://127.0.0.1:${ApiPort}/api/health"
Write-Host '         Same path through IIS: /api/health on the site URL above.'
Write-Host "  Task:  Scheduled task $TaskName starts the API at logon."
Write-Host ''
Write-Host 'If you use a custom host header, add it to hosts file and set WEB_ORIGINS in .env to match.'
