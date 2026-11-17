# TradeMind AI - local development on Windows PowerShell (no Docker).
# Usage (from the repository root):
#   .\scripts\dev.ps1 setup    # create .venv, install backend + frontend deps
#   .\scripts\dev.ps1 test     # run backend tests
#   .\scripts\dev.ps1 api      # start FastAPI on http://127.0.0.1:8000 (docs at /docs)
#   .\scripts\dev.ps1 web      # start the Vite frontend on http://localhost:5173
param([ValidateSet("setup", "test", "api", "web")][string]$Task = "api")

$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $PSScriptRoot
$Py = Join-Path $Root ".venv\Scripts\python.exe"

switch ($Task) {
    "setup" {
        if (-not (Test-Path $Py)) { py -3.12 -m venv (Join-Path $Root ".venv") }
        & $Py -m pip install --upgrade pip
        & $Py -m pip install -e "$Root\backend[dev,providers]"
        if (-not (Test-Path "$Root\.env")) { Copy-Item "$Root\.env.example" "$Root\.env" }
        Push-Location "$Root\frontend"; npm install; Pop-Location
    }
    "test" { Push-Location "$Root\backend"; & $Py -m pytest -q; Pop-Location }
    "api"  { Push-Location "$Root\backend"; & $Py -m uvicorn trademind.api.main:app --reload --host 127.0.0.1 --port 8000; Pop-Location }
    "web"  { Push-Location "$Root\frontend"; npm run dev; Pop-Location }
}
