@echo off
cd /d "%~dp0.."
if not exist "node_modules\concurrently" (
  echo Installing root dev dependencies...
  call npm install
)
echo Starting API and web — Ctrl+C stops both.
call npm run dev
