param([string]$Python = "python")
$ErrorActionPreference = "Stop"
$projectRoot = Split-Path -Parent $PSScriptRoot
Push-Location $projectRoot
try {
    $version = & $Python -c "import sys; print('.'.join(map(str,sys.version_info[:3])))"
    if ($LASTEXITCODE -ne 0 -or $version -ne "3.12.7") { throw "CPython 3.12.7 required" }
    if (Test-Path -LiteralPath ".venv") {
        $venvItem = Get-Item -LiteralPath ".venv" -Force
        if ($venvItem.Attributes -band [IO.FileAttributes]::ReparsePoint) { throw "Linked virtual environments are not allowed" }
    }
    if (-not (Test-Path -LiteralPath ".venv/Scripts/python.exe")) {
        & $Python -m venv .venv
        if ($LASTEXITCODE -ne 0) { throw "Virtual environment creation failed" }
    }
    New-Item -ItemType Directory -Force -Path ".local/logs",".local/pip-cache",".local/npm-cache" | Out-Null
    & ./.venv/Scripts/python.exe scripts/check_environment.py
    if ($LASTEXITCODE -ne 0) { throw "Wrong project interpreter" }
    & ./.venv/Scripts/python.exe -m pip install --disable-pip-version-check --require-hashes --cache-dir .local/pip-cache -r requirements.lock
    if ($LASTEXITCODE -ne 0) { throw "Python dependency installation failed" }
    if ((node --version) -ne "v24.18.0" -or (npm.cmd --version) -ne "11.16.0") { throw "Node 24.18.0 and npm 11.16.0 required" }
    npm.cmd --prefix apps/client ci --ignore-scripts --cache .local/npm-cache
    if ($LASTEXITCODE -ne 0) { throw "Frontend dependency installation failed" }
} finally { Pop-Location }
