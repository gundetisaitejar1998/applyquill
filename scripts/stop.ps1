$root = Split-Path -Parent $PSScriptRoot
foreach ($name in @('backend','frontend')) {
  $file = Join-Path $root "logs\$name.pid"
  if (!(Test-Path $file)) { continue }
  $id = 0
  if ([int]::TryParse((Get-Content $file -Raw).Trim(), [ref]$id)) {
    $proc = Get-CimInstance Win32_Process -Filter "ProcessId=$id" -ErrorAction SilentlyContinue
    if ($proc -and (($proc.CommandLine -match 'uvicorn backend.app.main' -and $name -eq 'backend') -or ($proc.CommandLine -match 'node_modules[\\/]vite[\\/]bin[\\/]vite.js' -and $name -eq 'frontend'))) {
      Stop-Process -Id $id -Force -ErrorAction SilentlyContinue
      Write-Host "Stopped JobPilot $name (PID $id)"
    } else { Write-Host "No matching JobPilot $name process for saved PID." }
  }
  Remove-Item $file -Force -ErrorAction SilentlyContinue
}
