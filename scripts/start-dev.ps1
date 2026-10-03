# Starts API + Vite in one terminal (preferred). Installs root dev deps if needed.
$Root = Split-Path -Parent $PSScriptRoot
Set-Location $Root

if (-not (Test-Path "node_modules\concurrently")) {
  Write-Host "Installing root dev dependencies (concurrently)..."
  npm install
}

Write-Host "Starting API (8000) and web (5173) — Ctrl+C stops both."
npm run dev
