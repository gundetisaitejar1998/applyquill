$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $PSScriptRoot
$python = Join-Path $root '.venv\Scripts\python.exe'
$nodeModules = Join-Path $root 'frontend\node_modules'
if (!(Test-Path $python)) { throw 'Project .venv Python was not found.' }
if (!(Test-Path $nodeModules)) { throw 'Frontend packages are missing. Run npm install in frontend first.' }
if (!(Test-Path (Join-Path $root 'frontend\dist'))) {
  Push-Location (Join-Path $root 'frontend')
  try { npm run build } finally { Pop-Location }
}
$apiPidFile = Join-Path $root 'logs\backend.pid'
$apiProc = $null
if (Test-Path $apiPidFile) { $apiProc = Get-CimInstance Win32_Process -Filter "ProcessId=$((Get-Content $apiPidFile -Raw).Trim())" -ErrorAction SilentlyContinue }
$apiRunning = $apiProc -and $apiProc.CommandLine.Contains('uvicorn backend.app.main:app')
if (!$apiRunning) {
  if (Get-NetTCPConnection -LocalPort 8000 -State Listen -ErrorAction SilentlyContinue) { throw 'Port 8000 is in use by another process. Stop it before starting JobPilot.' }
  $p = Start-Process -FilePath $python -ArgumentList @('-m','uvicorn','backend.app.main:app','--host','127.0.0.1','--port','8000') -WorkingDirectory $root -WindowStyle Hidden -PassThru -RedirectStandardOutput (Join-Path $root 'logs\backend.log') -RedirectStandardError (Join-Path $root 'logs\backend-error.log')
  Set-Content -Path (Join-Path $root 'logs\backend.pid') -Value $p.Id
}
$frontendPidFile = Join-Path $root 'logs\frontend.pid'
$frontendProc = $null
if (Test-Path $frontendPidFile) { $frontendProc = Get-CimInstance Win32_Process -Filter "ProcessId=$((Get-Content $frontendPidFile -Raw).Trim())" -ErrorAction SilentlyContinue }
$vite = Join-Path $root 'frontend\node_modules\vite\bin\vite.js'
$frontendPort = 0
$frontendRunning = $false
if ($frontendProc -and $frontendProc.CommandLine.Contains($vite)) {
  $match = [regex]::Match($frontendProc.CommandLine, '--port\s+(\d+)')
  if ($match.Success) {
    $frontendPort = [int]$match.Groups[1].Value
    $frontendRunning = Test-NetConnection -ComputerName 127.0.0.1 -Port $frontendPort -InformationLevel Quiet
  }
}
if (!$frontendRunning) {
  $frontendPort = 5173
  $portOpen = $false
  while (!$portOpen) {
    $probe = [System.Net.Sockets.TcpListener]::new([System.Net.IPAddress]::Parse('127.0.0.1'), $frontendPort)
    try { $probe.Start(); $probe.Stop(); $portOpen = $true } catch { try { $probe.Stop() } catch {}; $frontendPort++ }
  }
  $node = (Get-Command node.exe -ErrorAction Stop).Source
  $p = Start-Process -FilePath $node -ArgumentList @($vite,'--host','127.0.0.1','--port',"$frontendPort",'--strictPort') -WorkingDirectory (Join-Path $root 'frontend') -WindowStyle Hidden -PassThru -RedirectStandardOutput (Join-Path $root 'logs\frontend.log') -RedirectStandardError (Join-Path $root 'logs\frontend-error.log')
  Set-Content -Path (Join-Path $root 'logs\frontend.pid') -Value $p.Id
}
$ready = $false
for ($i=0; $i -lt 25; $i++) {
  Start-Sleep -Seconds 1
  if (Test-NetConnection -ComputerName 127.0.0.1 -Port $frontendPort -InformationLevel Quiet) { $ready = $true; break }
}
if (!$ready) { throw 'Dashboard did not start. Check logs\frontend-error.log and logs\backend-error.log.' }
Start-Process "http://localhost:$frontendPort"
Write-Host "JobPilot AI is running at http://localhost:$frontendPort"
