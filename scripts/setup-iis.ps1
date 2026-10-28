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

.PARAMETER BindAddresses
  IPv4 addresses to bind. When set, the site listens only on these addresses
  (for example the LAN address and the public NIC address). Empty = all addresses.

.EXAMPLE
  .\scripts\setup-iis.ps1
  .\scripts\setup-iis.ps1 -Port 80 -HostHeader cacsms-traders.local
  .\scripts\setup-iis.ps1 -Port 80 -BindAddresses 192.168.5.5,129.18.144.134
#>
[CmdletBinding()]
param(
  [string] $SiteName = 'Cacsms-Traders',
  [int] $Port = 8080,
  [string] $HostHeader = '',
  [int] $ApiPort = 8000,
  [string[]] $BindAddresses = @()
)

$ErrorActionPreference = 'Stop'
$Root = Split-Path -Parent $PSScriptRoot
$SiteDir = Join-Path $Root 'deploy\iis\site'
$TaskName = 'CacsmsTradersApi'
$VenvPy = Join-Path $Root '.venv\Scripts\python.exe'
$EmbedPy = Join-Path $env:LOCALAPPDATA 'Programs\Python\Python312-embed\python.exe'
if (-not (Test-Path $VenvPy) -and (Test-Path $EmbedPy)) {
  $VenvPy = $EmbedPy
}
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

$addresses = @($BindAddresses | ForEach-Object { $_ -split ',' } | Where-Object { $_ -and $_.Trim() } | ForEach-Object { $_.Trim() })
if ($addresses.Count -eq 0) { $addresses = @('*') }

function Clear-ConflictingHttpBindings {
  param([string] $KeepSite, [int] $ListenPort, [string[]] $ListenAddresses)
  foreach ($site in @(Get-Website)) {
    if ($site.Name -eq $KeepSite) { continue }
    foreach ($binding in @(Get-WebBinding -Name $site.Name -Protocol 'http' -ErrorAction SilentlyContinue)) {
      $parts = $binding.bindingInformation -split ':'
      if ($parts.Count -lt 2) { continue }
      $bindIp = $parts[0]
      $bindPort = 0
      if (-not [int]::TryParse($parts[1], [ref] $bindPort)) { continue }
      if ($bindPort -ne $ListenPort) { continue }
      $overlaps = ($bindIp -eq '*' -or $bindIp -eq '0.0.0.0' -or $bindIp -eq '' -or $ListenAddresses -contains '*' -or $ListenAddresses -contains $bindIp)
      if (-not $overlaps) { continue }
      Write-Host "Removing conflicting binding $($binding.bindingInformation) from $($site.Name)"
      Remove-WebBinding -Name $site.Name -Protocol 'http' -BindingInformation $binding.bindingInformation
    }
  }
}

Clear-ConflictingHttpBindings -KeepSite $SiteName -ListenPort $Port -ListenAddresses $addresses

$existing = Get-Website -Name $SiteName -ErrorAction SilentlyContinue
if ($existing) {
  Write-Host "Updating site $SiteName ..."
  Set-ItemProperty "IIS:\Sites\$SiteName" -Name physicalPath -Value $SiteDir
  Set-ItemProperty "IIS:\Sites\$SiteName" -Name applicationPool -Value $poolName
} else {
  Write-Host "Creating site $SiteName ..."
  New-Website -Name $SiteName -PhysicalPath $SiteDir -Port $Port -IPAddress $addresses[0] -HostHeader $HostHeader -ApplicationPool $poolName | Out-Null
}

Get-WebBinding -Name $SiteName -ErrorAction SilentlyContinue | ForEach-Object {
  Remove-WebBinding -Name $SiteName -Protocol $_.protocol -BindingInformation $_.bindingInformation
}
foreach ($ip in $addresses) {
  $shown = if ($HostHeader) { "${ip}:${Port}:$HostHeader" } else { "${ip}:${Port}:" }
  Write-Host "Binding $shown"
  New-WebBinding -Name $SiteName -Protocol http -IPAddress $ip -Port $Port -HostHeader $HostHeader | Out-Null
}

Write-Host 'Granting IIS read access to the site folder...'
& icacls $SiteDir /grant "IIS_IUSRS:(OI)(CI)RX" "IUSR:(OI)(CI)RX" | Out-Null

$dbDir = Join-Path $Root 'database'
if (Test-Path $dbDir) {
  Write-Host 'Granting the current user write access to the database folder...'
  & icacls $dbDir /grant "${env:USERDOMAIN}\${env:USERNAME}:(OI)(CI)M" | Out-Null
}

$fwName = "Cacsms-Traders HTTP $Port"
if (-not (Get-NetFirewallRule -DisplayName $fwName -ErrorAction SilentlyContinue)) {
  Write-Host "Opening Windows Firewall for TCP $Port on all profiles..."
  New-NetFirewallRule -DisplayName $fwName -Direction Inbound -Action Allow -Protocol TCP -LocalPort $Port -Profile Any | Out-Null
}

Set-Service W3SVC -StartupType Automatic
Set-Service WAS -StartupType Automatic
Start-Service WAS -ErrorAction SilentlyContinue
Start-Service W3SVC -ErrorAction SilentlyContinue

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
$hostScript = Join-Path $Root 'scripts\run-api-host.ps1'
$action = New-ScheduledTaskAction -Execute 'powershell.exe' -Argument "-NoProfile -WindowStyle Hidden -ExecutionPolicy Bypass -File `"$hostScript`"" -WorkingDirectory $Root
$trigger = New-ScheduledTaskTrigger -AtStartup
$settings = New-ScheduledTaskSettingsSet -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries -StartWhenAvailable -RestartCount 999 -RestartInterval (New-TimeSpan -Minutes 1) -ExecutionTimeLimit ([TimeSpan]::Zero) -MultipleInstances IgnoreNew
# The settings cmdlet turns StopOnIdleEnd on. That stops the API when someone uses the PC, and IIS then returns Bad Gateway.
$settings.IdleSettings.StopOnIdleEnd = $false
$settings.IdleSettings.RestartOnIdle = $false
# Limited, not Highest: an elevated API creates database journal files the desktop user cannot write.
$principal = New-ScheduledTaskPrincipal -UserId $env:USERNAME -LogonType Interactive -RunLevel Limited
Register-ScheduledTask -TaskName $TaskName -Action $action -Trigger $trigger -Settings $settings -Principal $principal -Force | Out-Null

$envFile = Join-Path $Root '.env'
if (-not (Test-Path $envFile)) {
  $origins = foreach ($ip in $addresses) {
    $hostName = if ($ip -eq '*') { 'localhost' } else { $ip }
    if ($HostHeader) { $hostName = $HostHeader }
    if ($Port -eq 80) { "http://$hostName" } else { "http://${hostName}:$Port" }
  }
  $origin = ($origins | Select-Object -Unique) -join ','
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
Start-ScheduledTask -TaskName $TaskName

Start-Website -Name $SiteName

Write-Host ''
Write-Host 'Cacsms-Traders IIS setup complete.'
foreach ($ip in $addresses) {
  $hostName = if ($ip -eq '*') { 'localhost' } else { $ip }
  if ($HostHeader) { $hostName = $HostHeader }
  $url = if ($Port -eq 80) { "http://$hostName" } else { "http://${hostName}:$Port" }
  Write-Host "  Site:  $url"
}
Write-Host "  API:   http://127.0.0.1:${ApiPort}/api/health"
Write-Host '         Same path through IIS: /api/health on the site URLs above.'
Write-Host "  Task:  Scheduled task $TaskName starts the API at logon."
Write-Host ''
Write-Host 'If you use a custom host header, add it to hosts file and set WEB_ORIGINS in .env to match.'
