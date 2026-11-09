"""Test desktop launchers in a synthetic project; never touch the user's 8000 service."""

import json
import os
import shutil
import socket
import subprocess
import sys
import time
from pathlib import Path
from uuid import uuid4

from check_environment import require_project_environment

ROOT = Path(__file__).resolve().parents[1]
FAKE_SERVER = """import argparse, json
from http.server import HTTPServer, BaseHTTPRequestHandler
from pathlib import Path
parser=argparse.ArgumentParser()
parser.add_argument('--port', type=int)
args=parser.parse_args()
class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        bad=Path(__file__).with_name('unhealthy.flag').exists()
        body=json.dumps({'status':'bad' if bad else 'ok','stage':'S2'}).encode()
        self.send_response(200)
        self.send_header('Content-Length',str(len(body)))
        self.end_headers()
        self.wfile.write(body)
    def log_message(self,*args): pass
HTTPServer(('127.0.0.1',args.port),Handler).serve_forever()
"""


def listening(port):
    with socket.socket() as sock:
        sock.settimeout(1)
        return sock.connect_ex(("127.0.0.1", port)) == 0


def main():
    require_project_environment()
    run_id = uuid4().hex
    fixture = ROOT / ".local" / ("launcher fixture 中文 [isolated] " + run_id)
    assert fixture.resolve().is_relative_to((ROOT / ".local").resolve())
    shell = Path(os.environ["SystemRoot"]) / "System32/WindowsPowerShell/v1.0/powershell.exe"
    if not shell.is_file():
        raise RuntimeError("Windows PowerShell is required")
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        port = sock.getsockname()[1]
    if port == 8000:
        raise RuntimeError("Synthetic launcher must never use port 8000")
    (fixture / "scripts").mkdir(parents=True)
    for name in ("start-local.ps1", "stop-local.ps1", "check_environment.py"):
        shutil.copyfile(ROOT / "scripts" / name, fixture / "scripts" / name)
    (fixture / "scripts/serve.py").write_text(FAKE_SERVER, encoding="utf-8")
    env = dict(os.environ)
    env.pop("DSA_DATA_SUBDIR", None)
    env.pop("DSA_MODE", None)
    env = {key: value for key, value in env.items() if key.casefold() != "psmodulepath"}
    logs = ROOT / ".local/logs" / ("desktop-launcher-" + run_id)
    logs.mkdir(parents=True, exist_ok=False)
    events = []
    foreign = None

    def execute(command, operation, expected_error=None, cwd=fixture):
        log_path = logs / (str(len(events) + 1).zfill(2) + "-" + operation + ".log")
        with log_path.open("w", encoding="utf-8") as log:
            result = subprocess.run(
                command,
                cwd=cwd,
                env=env,
                stdin=subprocess.DEVNULL,
                stdout=log,
                stderr=subprocess.STDOUT,
                timeout=50,
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
            )
        diagnostic = log_path.read_text(encoding="utf-8", errors="replace")
        accepted = (
            result.returncode == 0
            if expected_error is None
            else result.returncode != 0 and expected_error in diagnostic
        )
        events.append(
            {
                "operation": operation,
                "exit_code": result.returncode,
                "expected_error": expected_error,
                "passed": accepted,
                "log": log_path.relative_to(ROOT).as_posix(),
            }
        )
        if not accepted:
            raise RuntimeError("Synthetic launcher check failed: " + operation)

    def run(script, operation, expected_error=None):
        execute(
            [
                str(shell),
                "-NoProfile",
                "-ExecutionPolicy",
                "RemoteSigned",
                "-File",
                str(fixture / "scripts" / script),
                "-Port",
                str(port),
            ],
            operation,
            expected_error,
        )

    try:
        run("start-local.ps1", "missing-environment", "LOCAL_ENV_MISSING")
        subprocess.run(
            [sys.executable, "-m", "venv", "--without-pip", str(fixture / ".venv")],
            check=True,
            capture_output=True,
            timeout=40,
        )
        run("start-local.ps1", "missing-build", "LOCAL_BUILD_MISSING")
        assets = fixture / "apps/client/dist/h5"
        assets.mkdir(parents=True)
        (assets / "index.html").write_text("Synthetic launcher fixture only", encoding="utf-8")
        run("start-local.ps1", "missing-dependencies", "LOCAL_DEPENDENCIES_MISSING")
        # These module markers satisfy the launcher's existence preflight only.
        # The health fixture is stdlib-only; this is not a real backend/API test.
        for name in ("uvicorn", "fastapi", "httpx", "pydantic", "jsonschema"):
            (fixture / ".venv/Lib/site-packages" / (name + ".py")).write_text(
                "# Synthetic presence marker only\n"
            )
        run("start-local.ps1", "start-hidden-server")
        record_path = fixture / f".local/local-server-{port}.json"
        record = json.loads(record_path.read_text(encoding="utf-8-sig"))
        preserved = fixture / "runtime/synthetic-history.txt"
        preserved.write_text("Synthetic history must survive stop\n", encoding="utf-8")
        run("start-local.ps1", "reuse-healthy-server")
        second = json.loads(record_path.read_text(encoding="utf-8-sig"))
        assert record["pid"] == second["pid"]
        marker = fixture / "scripts/unhealthy.flag"
        marker.write_text("Synthetic unhealthy response\n", encoding="utf-8")
        run("start-local.ps1", "refuse-unhealthy-reuse", "LOCAL_SERVICE_UNHEALTHY")
        assert listening(port)
        marker.unlink()
        run("stop-local.ps1", "stop-owned-server")
        for _ in range(20):
            if not listening(port):
                break
            time.sleep(0.1)
        assert not listening(port)
        assert preserved.read_text(encoding="utf-8") == "Synthetic history must survive stop\n"
        run("stop-local.ps1", "stop-idempotent")

        # An independently started synthetic process owns the same test port.
        # Neither launcher may kill it even when stale own PID metadata remains.
        foreign_script = fixture / "foreign_server.py"
        foreign_script.write_text(FAKE_SERVER, encoding="utf-8")
        foreign = subprocess.Popen(
            [sys._base_executable, str(foreign_script), "--port", str(port)],
            cwd=fixture,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
        for _ in range(30):
            if listening(port):
                break
            time.sleep(0.1)
        assert listening(port) and foreign.poll() is None
        run("start-local.ps1", "refuse-foreign-port", "LOCAL_PORT_IN_USE")
        assert foreign.poll() is None
        run("stop-local.ps1", "refuse-foreign-stop", "Listener ownership mismatch")
        assert foreign.poll() is None

        # Copy the real CMD entry points into a synthetic directory. Their target
        # scripts only record the arguments; they never start a service/browser.
        wrapper = fixture / "wrapper path 中文"
        (wrapper / "scripts").mkdir(parents=True)
        for name in ("Start-Demand-Assistant.cmd", "Stop-Demand-Assistant.cmd"):
            shutil.copyfile(ROOT / name, wrapper / name)
        (wrapper / "scripts/start-local.ps1").write_text(
            "param([switch]$OpenBrowser)\n"
            "if (-not $OpenBrowser) { throw 'Expected browser flag' }\n"
            "[IO.File]::WriteAllText((Join-Path $PSScriptRoot 'start-marker.txt'), "
            "'http://127.0.0.1:8000')\n",
            encoding="utf-8",
        )
        (wrapper / "scripts/stop-local.ps1").write_text(
            "[IO.File]::WriteAllText((Join-Path $PSScriptRoot 'stop-marker.txt'), 'stop')\n",
            encoding="utf-8",
        )
        for name in ("Start-Demand-Assistant.cmd", "Stop-Demand-Assistant.cmd"):
            execute(
                ["cmd.exe", "/d", "/c", str(wrapper / name)],
                "wrapper-" + name.split("-")[0].lower(),
                cwd=ROOT,
            )
        assert (wrapper / "scripts/start-marker.txt").read_text() == "http://127.0.0.1:8000"
        assert (wrapper / "scripts/stop-marker.txt").read_text() == "stop"
        result = {
            "passed": True,
            "fixture": "synthetic project with spaces, Chinese and brackets in its path",
            "user_instance_touched": False,
            "real_browser_opened": False,
            "real_api_or_private_data_used": False,
            "project_python_environment_checked": True,
            "events": events,
            "checks": {
                "missing_environment_build_dependencies": True,
                "start_hidden_repeat_health_stop": True,
                "unhealthy_existing_service_not_restarted": True,
                "foreign_port_and_process_not_stopped": True,
                "data_preserved_after_stop": True,
                "cmd_paths_and_browser_argument_with_stub_targets": True,
            },
        }
        (logs / "launcher-smoke.json").write_text(
            json.dumps(result, indent=2) + "\n", encoding="utf-8"
        )
        print(
            json.dumps(
                {
                    "passed": True,
                    "operations_passed": len(events),
                    "evidence": (logs / "launcher-smoke.json").relative_to(ROOT).as_posix(),
                    "user_instance_touched": False,
                    "real_browser_opened": False,
                },
                indent=2,
            )
        )
    finally:
        (logs / "operations.json").write_text(json.dumps(events, indent=2), encoding="utf-8")
        if foreign is not None and foreign.poll() is None:
            foreign.terminate()
            foreign.wait(timeout=10)
        if (fixture / f".local/local-server-{port}.json").exists():
            subprocess.run(
                [
                    str(shell),
                    "-NoProfile",
                    "-ExecutionPolicy",
                    "RemoteSigned",
                    "-File",
                    str(fixture / "scripts/stop-local.ps1"),
                    "-Port",
                    str(port),
                ],
                cwd=fixture,
                env=env,
                stdin=subprocess.DEVNULL,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                timeout=40,
            )
        assert fixture.resolve().is_relative_to((ROOT / ".local").resolve())
        shutil.rmtree(fixture)


if __name__ == "__main__":
    main()
