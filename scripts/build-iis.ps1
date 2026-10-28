# Build the web UI and stage static files for IIS (deploy/iis/site).
$ErrorActionPreference = 'Stop'
$Root = Split-Path -Parent $PSScriptRoot
$SiteDir = Join-Path $Root 'deploy\iis\site'
$WebConfig = Join-Path $Root 'deploy\iis\web.config'

Set-Location $Root

Write-Host 'Installing web dependencies...'
Push-Location (Join-Path $Root 'apps\web')
# npm writes warnings to stderr. PowerShell treats that as a terminating error when ErrorAction is Stop.
$prevEap = $ErrorActionPreference
$ErrorActionPreference = 'Continue'
cmd /c "npm ci"
if ($LASTEXITCODE -ne 0) {
  cmd /c "npm install"
}
if ($LASTEXITCODE -ne 0) {
  $ErrorActionPreference = $prevEap
  Pop-Location
  throw "npm install failed (exit $LASTEXITCODE)."
}
cmd /c "npm run build"
if ($LASTEXITCODE -ne 0) {
  $ErrorActionPreference = $prevEap
  Pop-Location
  throw "Frontend build failed (exit $LASTEXITCODE)."
}
$ErrorActionPreference = $prevEap
Pop-Location

if (-not (Test-Path (Join-Path $Root 'apps\web\dist\index.html'))) {
  throw 'Frontend build failed: apps/web/dist/index.html missing.'
}

Write-Host "Staging site to $SiteDir ..."
if (Test-Path $SiteDir) {
  Remove-Item -Recurse -Force $SiteDir
}
New-Item -ItemType Directory -Path $SiteDir | Out-Null
Copy-Item -Recurse -Force (Join-Path $Root 'apps\web\dist\*') $SiteDir
Copy-Item -Force $WebConfig (Join-Path $SiteDir 'web.config')

Write-Host 'IIS site files ready in deploy/iis/site'
