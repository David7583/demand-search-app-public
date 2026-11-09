param([int]$Port = 8000)
$ErrorActionPreference = "Stop"
if ($Port -lt 1024 -or $Port -gt 65535) { throw "Port must be 1024-65535." }
$projectRoot = [IO.Path]::GetFullPath((Split-Path -Parent $PSScriptRoot))
$privateRoot = Join-Path $projectRoot ".local"
if ((Test-Path -LiteralPath $privateRoot) -and
    ((Get-Item -LiteralPath $privateRoot -Force).Attributes -band [IO.FileAttributes]::ReparsePoint)) {
    throw "LOCAL_STATE_LINKED: Private directory must not be linked."
}
$pidFile = Join-Path $projectRoot ".local\local-server-$Port.json"
if (-not (Test-Path -LiteralPath $pidFile)) { Write-Output "No recorded local server."; exit 0 }
if ((Get-Item -LiteralPath $pidFile -Force).Attributes -band [IO.FileAttributes]::ReparsePoint) { throw "LOCAL_STATE_LINKED: Process record must not be linked." }
$record = Get-Content -LiteralPath $pidFile -Raw | ConvertFrom-Json
if ($record.port -ne $Port) { throw "Recorded port mismatch; nothing stopped." }
$python = Join-Path $projectRoot ".venv\Scripts\python.exe"
if (-not (Test-Path -LiteralPath $python)) { throw "LOCAL_ENV_MISSING: Cannot safely identify this project's interpreter; nothing stopped." }
$serveScript = Join-Path $projectRoot "scripts\serve.py"
$servePattern = '(?:^|\s)(?:"' + [regex]::Escape($serveScript) + '"|' + [regex]::Escape($serveScript) + ')(?:\s|$)'
$basePython = & $python -c "import sys; print(sys._base_executable)"
if ($LASTEXITCODE -ne 0) { throw "Cannot identify base interpreter." }
$portPattern = '(?:^|\s)--port\s+"?' + $Port + '"?(?:\s|$)'
function Test-OwnedServer($process) {
    return $process -and $process.ExecutablePath -in @($python, $basePython) -and
        $process.CommandLine -match $servePattern -and
        $process.CommandLine -match $portPattern
}
$listeners = @(Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue)
$targets = @()
if ($listeners.Count -gt 0) {
    foreach ($listener in $listeners) {
        $candidate = Get-CimInstance Win32_Process -Filter "ProcessId = $($listener.OwningProcess)"
        if ((Test-OwnedServer $candidate) -and
            ($candidate.ProcessId -eq $record.pid -or $candidate.ParentProcessId -eq $record.pid)) {
            $targets += $candidate.ProcessId
        }
    }
    if ($targets.Count -ne $listeners.Count) { throw "Listener ownership mismatch; nothing stopped." }
} else {
    $process = Get-CimInstance Win32_Process -Filter "ProcessId = $($record.pid)"
    if (-not $process) { Write-Output "Recorded local server already stopped."; exit 0 }
    if (-not (Test-OwnedServer $process)) { throw "PID no longer belongs to this instance; nothing stopped." }
    # A venv redirector may still have a child while startup is failing.
    $children = @(Get-CimInstance Win32_Process -Filter "ParentProcessId = $($record.pid)")
    foreach ($child in $children) {
        if (Test-OwnedServer $child) { $targets += $child.ProcessId }
    }
    $targets += $record.pid
}
foreach ($serverPid in ($targets | Select-Object -Unique)) {
    Stop-Process -Id $serverPid -ErrorAction SilentlyContinue
}
Write-Output "This project's local server stopped."
