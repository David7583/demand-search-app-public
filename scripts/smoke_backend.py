"""Real loopback history persistence across restarts; synthetic isolated database only."""

import http.cookiejar
import json
import os
import shutil
import socket
import subprocess
import sys
import time
import urllib.request
from pathlib import Path
from uuid import uuid4

from check_environment import require_project_environment

ROOT = Path(__file__).resolve().parents[1]


def main():
    require_project_environment()
    logs = ROOT / ".local/logs/s2-validation"
    logs.mkdir(parents=True, exist_ok=True)
    subdir = "test-http-s2-" + uuid4().hex
    data = ROOT / "runtime" / subdir
    env = dict(os.environ, DSA_DATA_SUBDIR=subdir)
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        port = sock.getsockname()[1]
    events, conversation_a, conversation_b = [], None, None
    try:
        for run in (1, 2):
            with (logs / f"backend-process-{run}.log").open("w") as log:
                child = subprocess.Popen(
                    [sys.executable, str(ROOT / "scripts/serve.py"), "--port", str(port)],
                    cwd=ROOT,
                    env=env,
                    stdout=log,
                    stderr=log,
                    creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
                )
                try:
                    origin = f"http://127.0.0.1:{port}"
                    opener = urllib.request.build_opener(
                        urllib.request.ProxyHandler({}),
                        urllib.request.HTTPCookieProcessor(http.cookiejar.CookieJar()),
                    )
                    csrf = ""

                    def request(path, method="GET", value=None):
                        headers = {"Origin": origin}
                        raw = None
                        if method != "GET":
                            headers.update({"Content-Type": "application/json", "X-DSA-CSRF": csrf})
                            raw = json.dumps(value if value is not None else {}).encode()
                        req = urllib.request.Request(
                            origin + path, data=raw, method=method, headers=headers
                        )
                        with opener.open(req, timeout=3) as response:
                            return json.load(response)

                    deadline = time.monotonic() + 20
                    while True:
                        if child.poll() is not None:
                            raise RuntimeError("Backend exited; inspect private process log")
                        try:
                            health = request("/healthz")
                            break
                        except OSError:
                            if time.monotonic() > deadline:
                                raise RuntimeError("Backend startup timed out") from None
                            time.sleep(0.1)
                    csrf = request("/api/v1/session")["csrf_token"]
                    assert health == {"status": "ok", "stage": "S2"}
                    status = request("/api/v1/status")
                    assert not status["ai_configured"] and status["history_enabled"]
                    if run == 1:
                        conversation_a = request(
                            "/api/v1/conversations", "POST", {"title": "Synthetic A"}
                        )["id"]
                        conversation_b = request(
                            "/api/v1/conversations", "POST", {"title": "Synthetic B"}
                        )["id"]
                        for identifier, content in (
                            (conversation_a, "synthetic chair"),
                            (conversation_b, "synthetic laptop"),
                        ):
                            request(
                                f"/api/v1/conversations/{identifier}/messages",
                                "POST",
                                {"content": content, "client_message_id": str(uuid4())},
                            )
                    else:
                        a = request(f"/api/v1/conversations/{conversation_a}")
                        b = request(f"/api/v1/conversations/{conversation_b}")
                        assert [m["content"] for m in a["messages"]] == ["synthetic chair"]
                        assert [m["content"] for m in b["messages"]] == ["synthetic laptop"]
                        message = {
                            "content": "synthetic continuation",
                            "client_message_id": str(uuid4()),
                        }
                        first = request(
                            f"/api/v1/conversations/{conversation_a}/messages", "POST", message
                        )
                        retry = request(
                            f"/api/v1/conversations/{conversation_a}/messages", "POST", message
                        )
                        assert not first["duplicate"] and retry["duplicate"]
                        assert (
                            len(request(f"/api/v1/conversations/{conversation_a}")["messages"]) == 2
                        )
                        assert (
                            len(request(f"/api/v1/conversations/{conversation_b}")["messages"]) == 1
                        )
                    events.append({"run": run, "pid": child.pid, "health": health})
                finally:
                    child.terminate()
                    child.wait(timeout=10)
        result = {
            "passed": True,
            "data": "synthetic isolated test directory",
            "transport": "real loopback HTTP",
            "restart_runs": events,
            "history_resume_and_retry_verified": True,
            "external_ai_tested": False,
            "product_api_tested": False,
            "ncp_transport_tested": False,
        }
        (logs / "backend-smoke.json").write_text(
            json.dumps(result, indent=2) + "\n", encoding="utf-8"
        )
        print(json.dumps(result, indent=2))
    finally:
        assert data.resolve().is_relative_to((ROOT / "runtime").resolve()) and data.name == subdir
        if data.exists():
            shutil.rmtree(data)


if __name__ == "__main__":
    main()
