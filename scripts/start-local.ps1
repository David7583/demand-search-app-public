param([int]$Port = 8000, [switch]$OpenBrowser)
$ErrorActionPreference = "Stop"
$projectRoot = [IO.Path]::GetFullPath((Split-Path -Parent $PSScriptRoot))
$python = Join-Path $projectRoot ".venv\Scripts\python.exe"
if (-not (Test-Path -LiteralPath $python)) { throw "LOCAL_ENV_MISSING: Run scripts/init.ps1 with CPython 3.12.7 first. Nothing was installed." }
if ($Port -lt 1024 -or $Port -gt 65535) { throw "Port must be 1024-65535." }
if ($env:DSA_DATA_SUBDIR) { throw "Clear DSA_DATA_SUBDIR before starting the user application." }
if (-not (Test-Path -LiteralPath (Join-Path $projectRoot "apps\client\dist\h5\index.html"))) {
    throw "LOCAL_BUILD_MISSING: Run npm.cmd --prefix apps/client run build:h5 first. No automatic install or build was attempted."
}
if ($env:DSA_MODE -and $env:DSA_MODE -ne "local-dev") { throw "LOCAL_MODE_REQUIRED: Clear DSA_MODE or use local-dev." }
$environmentCheck = Join-Path $projectRoot "scripts\check_environment.py"
if (-not (Test-Path -LiteralPath $environmentCheck)) { throw "LOCAL_PROJECT_INCOMPLETE: scripts/check_environment.py is missing." }
& $python $environmentCheck | Out-Null
if ($LASTEXITCODE -ne 0) { throw "LOCAL_ENV_INVALID: This project requires its own physical CPython 3.12.7 virtual environment." }
$serveScript = Join-Path $projectRoot "scripts\serve.py"
if (-not (Test-Path -LiteralPath $serveScript)) { throw "LOCAL_PROJECT_INCOMPLETE: scripts/serve.py is missing." }
$servePattern = '(?:^|\s)(?:"' + [regex]::Escape($serveScript) + '"|' + [regex]::Escape($serveScript) + ')(?:\s|$)'
$portPattern = '(?:^|\s)--port\s+"?' + $Port + '"?(?:\s|$)'
function Test-OwnedCommand($process) {
    return $process -and $process.ExecutablePath -in @($python, $basePython) -and
        $process.CommandLine -match $servePattern -and $process.CommandLine -match $portPattern
}
function Open-LocalPage {
    if ($OpenBrowser) {
        try {
            # The user explicitly requests the visible default browser.
            Start-Process -FilePath ("http://127.0.0.1:" + $Port) | Out-Null
        } catch {
            throw "LOCAL_BROWSER_OPEN_FAILED: The service is running. Open http://127.0.0.1:$Port manually."
        }
    }
}
# Protect only this project's private directories, never parent or sibling projects.
$identity = [Security.Principal.WindowsIdentity]::GetCurrent().User
$system = [Security.Principal.SecurityIdentifier]::new("S-1-5-18")
foreach ($name in @("runtime", ".local")) {
    $privatePath = Join-Path $projectRoot $name
    New-Item -ItemType Directory -Force -Path $privatePath | Out-Null
    $item = Get-Item -LiteralPath $privatePath -Force
    if ($item.Attributes -band [IO.FileAttributes]::ReparsePoint) { throw "Private directory must not be linked." }
    if ([IO.Path]::GetFullPath($item.FullName) -ne $privatePath) { throw "Private directory boundary mismatch." }
    $acl = [Security.AccessControl.DirectorySecurity]::new()
    $acl.SetAccessRuleProtection($true, $false)
        foreach ($sid in @($identity, $system)) {
        $rule = [Security.AccessControl.FileSystemAccessRule]::new(
            $sid, "FullControl", "ContainerInherit,ObjectInherit", "None", "Allow")
        $acl.AddAccessRule($rule)
    }
    $existing = Get-Acl -LiteralPath $privatePath
    $existingRules = @($existing.GetAccessRules($true, $true, [Security.Principal.SecurityIdentifier]))
    $allowed = @($identity.Value, $system.Value)
    $unexpected = @($existingRules | Where-Object {
        $_.IdentityReference.Value -notin $allowed -or $_.AccessControlType -ne "Allow" -or
        $_.FileSystemRights -ne "FullControl" -or $_.IsInherited
    })
    $present = @($existingRules | ForEach-Object { $_.IdentityReference.Value } | Select-Object -Unique)
    if (-not $existing.AreAccessRulesProtected -or $unexpected.Count -gt 0 -or $present.Count -ne 2) {
        # Change the DACL only; do not request owner/SACL privileges.
        Set-Acl -LiteralPath $privatePath -AclObject $acl
    }
    $verified = Get-Acl -LiteralPath $privatePath
    if (-not $verified.AreAccessRulesProtected) { throw "Private directory ACL protection failed." }
}
$logs = Join-Path $projectRoot ".local\logs"
New-Item -ItemType Directory -Force -Path $logs | Out-Null
if ((Get-Item -LiteralPath $logs -Force).Attributes -band [IO.FileAttributes]::ReparsePoint) { throw "LOCAL_STATE_LINKED: Log directory must not be linked." }
$pidFile = Join-Path $projectRoot ".local\local-server-$Port.json"
$legacyPidFile = Join-Path $projectRoot ".local\local-server.json"
foreach ($recordPath in @($pidFile, $legacyPidFile)) {
    if ((Test-Path -LiteralPath $recordPath) -and
        ((Get-Item -LiteralPath $recordPath -Force).Attributes -band [IO.FileAttributes]::ReparsePoint)) {
        throw "LOCAL_STATE_LINKED: Process record must not be linked."
    }
}
$basePython = & $python -c "import sys; print(sys._base_executable)"
if ($LASTEXITCODE -ne 0) { throw "Cannot identify this virtual environment's base interpreter." }

$listeners = @(Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue)
if ($listeners.Count -gt 0) {
    $own = $null
    if (Test-Path -LiteralPath $pidFile) { $own = Get-Content -LiteralPath $pidFile -Raw | ConvertFrom-Json }
    elseif (Test-Path -LiteralPath $legacyPidFile) { $own = Get-Content -LiteralPath $legacyPidFile -Raw | ConvertFrom-Json }
    $ownedServers = @()
    if ($own -and $own.port -eq $Port) {
        foreach ($listener in $listeners) {
            $candidate = Get-CimInstance Win32_Process -Filter "ProcessId = $($listener.OwningProcess)"
            if ((Test-OwnedCommand $candidate) -and
                ($candidate.ProcessId -eq $own.pid -or $candidate.ParentProcessId -eq $own.pid)) {
                $ownedServers += $candidate
            }
        }
    }
    if ($ownedServers.Count -ne $listeners.Count -or @($ownedServers.ProcessId | Select-Object -Unique).Count -ne 1) {
        throw "LOCAL_PORT_IN_USE: Port $Port is not exclusively owned by this project. Nothing was stopped."
    }
    try {
        $health = Invoke-RestMethod "http://127.0.0.1:$Port/healthz" -TimeoutSec 2 -MaximumRedirection 0
        if ($health.status -ne "ok" -or $health.stage -ne "S2") { throw "Unexpected health response" }
    } catch {
        throw "LOCAL_SERVICE_UNHEALTHY: This project's process exists but health failed. Nothing was restarted or stopped."
    }
    $ownedServer = $ownedServers[0]
    @{pid=$ownedServer.ProcessId;launcher_pid=$own.pid;port=$Port} | ConvertTo-Json | Set-Content -LiteralPath $pidFile -Encoding utf8
    Write-Output "Already running: http://127.0.0.1:$Port"
    Open-LocalPage
    exit 0
}
$missing = & $python -c "import importlib.util; names=('uvicorn','fastapi','httpx','pydantic','jsonschema'); print(', '.join(name for name in names if importlib.util.find_spec(name) is None))"
if ($LASTEXITCODE -ne 0 -or $missing) {
    throw "LOCAL_DEPENDENCIES_MISSING: Run scripts/init.ps1 using CPython 3.12.7. Missing: $missing. No global packages were installed."
}
$startOptions = @{
    FilePath=$python
    ArgumentList=@(('"' + (Join-Path $projectRoot "scripts\serve.py") + '"'), "--port", "$Port")
    WorkingDirectory=[System.Management.Automation.WildcardPattern]::Escape($projectRoot)
    WindowStyle="Hidden"
    PassThru=$true
    RedirectStandardOutput=[System.Management.Automation.WildcardPattern]::Escape((Join-Path $logs "s1-live-$Port.stdout.log"))
    RedirectStandardError=[System.Management.Automation.WildcardPattern]::Escape((Join-Path $logs "s1-live-$Port.stderr.log"))
}
$child = Start-Process @startOptions
@{pid=$child.Id;launcher_pid=$child.Id;port=$Port} | ConvertTo-Json | Set-Content -LiteralPath $pidFile -Encoding utf8
$ready = $false
for ($i=0; $i -lt 40; $i++) {
    if ($child.HasExited) { throw "Local server exited; inspect private .local/logs/s1-live-$Port.stderr.log." }
    try {
        $health = Invoke-RestMethod "http://127.0.0.1:$Port/healthz" -TimeoutSec 1
        if ($health.status -eq "ok" -and $health.stage -eq "S2") { $ready = $true; break }
    } catch {}
    Start-Sleep -Milliseconds 250
}
if (-not $ready) { throw "Server startup not confirmed; inspect private logs." }
$server = @(Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction Stop |
    ForEach-Object { Get-CimInstance Win32_Process -Filter "ProcessId = $($_.OwningProcess)" } |
    Where-Object {
        (Test-OwnedCommand $_) -and
        ($_.ProcessId -eq $child.Id -or $_.ParentProcessId -eq $child.Id)
    })
if ($server.Count -ne 1) { throw "Cannot verify server process ownership." }
@{pid=$server[0].ProcessId;launcher_pid=$child.Id;port=$Port} | ConvertTo-Json | Set-Content -LiteralPath $pidFile -Encoding utf8
Write-Output "Ready: http://127.0.0.1:$Port"
Write-Output "Windows current-user DPAPI; private directory ACLs protected; loopback only."
Open-LocalPage
