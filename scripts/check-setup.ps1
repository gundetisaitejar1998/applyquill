$root = Split-Path -Parent $PSScriptRoot
Write-Host 'JobPilot AI setup check'
Write-Host "Python: $(& (Join-Path $root '.venv\Scripts\python.exe') --version 2>&1)"
Write-Host "Node: $(node --version 2>&1)"
Write-Host "npm: $(npm --version 2>&1)"
Write-Host "Ollama: $(ollama --version 2>&1)"
Write-Host 'Ollama models:'
ollama list
if (Test-Path (Join-Path $root 'frontend\node_modules')) { Write-Host 'Frontend dependencies: installed' } else { Write-Host 'Frontend dependencies: missing; run npm install in frontend' }
try { $r=Invoke-RestMethod 'http://127.0.0.1:11434/api/tags' -TimeoutSec 2; if ($r.models.Count) { Write-Host ("Local Ollama models: " + (($r.models | ForEach-Object name) -join ', ')) } else { Write-Host 'Ollama is reachable, but no models are installed.' } } catch { Write-Host 'Ollama is not reachable; the app can still run without AI model inference.' }
