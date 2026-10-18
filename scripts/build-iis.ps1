# Build the web UI and stage static files for IIS (deploy/iis/site).
$ErrorActionPreference = 'Stop'
$Root = Split-Path -Parent $PSScriptRoot
$SiteDir = Join-Path $Root 'deploy\iis\site'
$WebConfig = Join-Path $Root 'deploy\iis\web.config'

Set-Location $Root

Write-Host 'Installing web dependencies...'
Push-Location (Join-Path $Root 'apps\web')
npm ci 2>$null
if ($LASTEXITCODE -ne 0) {
  npm install
}
npm run build
if ($LASTEXITCODE -ne 0) {
  Pop-Location
  throw "Frontend build failed (exit $LASTEXITCODE)."
}
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
