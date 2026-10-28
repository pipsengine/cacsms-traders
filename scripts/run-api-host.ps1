# Keeps the local API listening for IIS. The scheduled task runs this script.
# Python is restarted if it exits, and also if /api/health/live stops answering.
# Output is appended to deploy\iis\api*.log.
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

function Write-HostLog([string]$message) {
  Add-Content -Path $errLog -Value "$(Get-Date -Format 'yyyy-MM-dd HH:mm:ss') $message"
}

function Test-ApiLive {
  try {
    $req = [System.Net.WebRequest]::Create('http://127.0.0.1:8000/api/health/live')
    $req.Proxy = $null
    $req.Timeout = 8000
    $req.ReadWriteTimeout = 8000
    $resp = $req.GetResponse()
    $code = [int]$resp.StatusCode
    $resp.Close()
    return $code -eq 200
  } catch {
    return $false
  }
}

function Stop-Tree([int]$procId) {
  Get-CimInstance Win32_Process -Filter "ParentProcessId=$procId" -ErrorAction SilentlyContinue |
    ForEach-Object { Stop-Tree ([int]$_.ProcessId) }
  Stop-Process -Id $procId -Force -ErrorAction SilentlyContinue
}

function Start-ApiCmd {
  # cmd strips the first and last quote. The doubled quote keeps paths that contain spaces.
  $psi = New-Object System.Diagnostics.ProcessStartInfo
  $psi.FileName = 'cmd.exe'
  $psi.Arguments = '/c ""' + $py + '" "' + $run + '" >> "' + $outLog + '" 2>> "' + $errLog + '""'
  $psi.WorkingDirectory = $Root
  $psi.UseShellExecute = $false
  $psi.CreateNoWindow = $true
  return [System.Diagnostics.Process]::Start($psi)
}

while ($true) {
  Write-HostLog "API host starting $py"
  $cmd = Start-ApiCmd
  $started = Get-Date
  $misses = 0
  while (-not $cmd.HasExited) {
    Start-Sleep -Seconds 5
    if (((Get-Date) - $started).TotalSeconds -lt 45) { continue }
    if (Test-ApiLive) {
      $misses = 0
      continue
    }
    $misses++
    Write-HostLog "API health missed ($misses)"
    if ($misses -ge 3) {
      Write-HostLog "API stopped answering. Restarting it."
      Stop-Tree $cmd.Id
      break
    }
  }
  if (-not $cmd.HasExited) { Stop-Tree $cmd.Id }
  $cmd.Refresh()
  $code = if ($cmd.HasExited) { $cmd.ExitCode } else { -1 }
  Write-HostLog "API host exited $code"
  Start-Sleep -Seconds 3
}
