$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $MyInvocation.MyCommand.Path
$python = Join-Path $root ".venv\Scripts\python.exe"

if (-not (Test-Path $python)) {
    throw "Python virtual environment was not found. Install dependencies first."
}

Set-Location $root
& $python -m uvicorn app.main:app --host 127.0.0.1 --port 8787
