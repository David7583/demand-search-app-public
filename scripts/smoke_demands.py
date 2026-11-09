"""S2 real HTTP/restart/DPAPI lifecycle with a clearly synthetic model provider."""

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
    subdir = "test-s2-http-" + uuid4().hex
    path = ROOT / "runtime" / subdir
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        port = sock.getsockname()[1]
    env = dict(os.environ, PYTHONPATH=str(ROOT / "apps/server/src"))
    events, calls, a, b, initial_export, immutable_version = [], 0, None, None, None, None
    try:
        for run in (1, 2):
            with (logs / f"demand-process-{run}.log").open("w") as log:
                child = subprocess.Popen(
                    [
                        sys.executable,
                        str(ROOT / "tests/fixtures/s2_model_server.py"),
                        "--port",
                        str(port),
                        "--data-subdir",
                        subdir,
                    ],
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

                    def request(route, method="GET", data=None):
                        nonlocal calls
                        headers = {"Origin": origin}
                        raw = None
                        if method != "GET":
                            headers.update({"Content-Type": "application/json", "X-DSA-CSRF": csrf})
                            raw = json.dumps(data or {}, ensure_ascii=False).encode()
                        req = urllib.request.Request(
                            origin + "/api/v1" + route, data=raw, method=method, headers=headers
                        )
                        with opener.open(req, timeout=4) as response:
                            result = json.load(response)
                        calls += 1
                        assert "synthetic-s2-only-http-key" not in json.dumps(result)
                        return result

                    deadline = time.monotonic() + 15
                    while True:
                        if child.poll() is not None:
                            raise RuntimeError("Synthetic S2 server exited")
                        try:
                            csrf = request("/session")["csrf_token"]
                            break
                        except OSError:
                            if time.monotonic() > deadline:
                                raise RuntimeError("Synthetic S2 startup timeout") from None
                            time.sleep(0.1)
                    if run == 1:
                        tested = request(
                            "/config/models/test",
                            "POST",
                            {
                                "name": "Synthetic S2",
                                "provider": "custom",
                                "base_url": "https://models.example.com/v1",
                                "api_mode": "chat_completions",
                                "model": "synthetic-s2",
                                "api_key": "synthetic-s2-only-http-key",
                                "consent": True,
                                "test_text": "synthetic connection",
                            },
                        )
                        request(
                            "/config/models/save",
                            "POST",
                            {"validation_id": tested["validation_id"], "make_active": True},
                        )
                        a = request("/conversations", "POST", {"title": "Synthetic A"})["id"]
                        b = request("/conversations", "POST", {"title": "Synthetic B"})["id"]
                        base = f"/conversations/{a}/demand"
                        current = None
                        for amount in (1500, 3000):
                            text = f"想找适合久坐的办公椅，预算{amount}元。"
                            message = request(
                                f"/conversations/{a}/messages",
                                "POST",
                                {"content": text, "client_message_id": str(uuid4())},
                            )
                            payload = {
                                "message_id": message["message"]["id"],
                                "expected_version_id": current,
                                "request_id": str(uuid4()),
                                "consent": True,
                            }
                            draft = request(base + "/parse", "POST", payload)
                            assert not draft["current_version"]["user_confirmed"]
                            repeated = request(base + "/parse", "POST", payload)
                            assert repeated["duplicate"]
                            version = draft["current_version"]
                            edits = {
                                "desired_outcome": version["data"]["desired_outcome"],
                                "required": [item["text"] for item in version["data"]["required"]],
                                "preferred": [],
                                "unknown": version["data"]["unknown"],
                                "budget_ceiling": {"amount": amount, "currency": "CNY"},
                                "readiness": "need",
                                "alternatives_acceptable": True,
                            }
                            confirmed = request(
                                base + "/confirm",
                                "POST",
                                {
                                    "version_id": version["id"],
                                    "request_id": str(uuid4()),
                                    "confirm": True,
                                    "continue_current_intent": False,
                                    "edits": edits,
                                },
                            )
                            current = confirmed["current_version"]["id"]
                            assert confirmed["current_version"]["user_confirmed"]
                            if amount == 1500:
                                immutable_version = confirmed["current_version"]
                        assert len(confirmed["versions"]) == 4
                        assert (
                            next(
                                v
                                for v in confirmed["versions"]
                                if v["id"] == immutable_version["id"]
                            )
                            == immutable_version
                        )
                        initial_export = request(
                            base + "/export", "POST", {"acknowledge_private_export": True}
                        )
                        assert [p["message_type"] for p in initial_export["packets"]] == [
                            "intent.publish",
                            "intent.update",
                        ]
                        assert request(f"/conversations/{b}/demand")["demand"] is None
                    else:
                        base = f"/conversations/{a}/demand"
                        detail = request(base)
                        assert detail["current_version"]["data"]["budget_ceiling"]["amount"] == 3000
                        assert (
                            next(
                                v for v in detail["versions"] if v["id"] == immutable_version["id"]
                            )
                            == immutable_version
                        )
                        exported = request(
                            base + "/export", "POST", {"acknowledge_private_export": True}
                        )
                        assert exported == initial_export
                        assert request(f"/conversations/{b}/demand")["demand"] is None
                        request(
                            base + "/withdraw",
                            "POST",
                            {
                                "request_id": str(uuid4()),
                                "expected_version_id": detail["current_version"]["id"],
                                "confirm": True,
                                "reason": "Synthetic withdrawal",
                            },
                        )
                        final = request(
                            base + "/export", "POST", {"acknowledge_private_export": True}
                        )
                        assert final["packets"][-1]["message_type"] == "intent.withdraw"
                        assert not final["network_transmitted"]
                        assert request(base)["demand"]["status"] == "withdrawn"
                    events.append({"run": run, "pid": child.pid})
                finally:
                    child.terminate()
                    child.wait(timeout=10)
        assert b"synthetic-s2-only-http-key" not in (path / "demand-search.sqlite3").read_bytes()
        result = {
            "passed": True,
            "http_responses": calls,
            "restart_runs": events,
            "data_and_provider": "synthetic",
            "dpapi_and_loopback_http": "real",
            "immutable_budget_revision": True,
            "exact_export_after_restart": True,
            "cross_conversation_isolation": True,
            "withdrawal_verified": True,
            "real_external_ai_tested": False,
            "ncp_network_tested": False,
        }
        (logs / "demand-smoke.json").write_text(
            json.dumps(result, indent=2) + "\n", encoding="utf-8"
        )
        print(json.dumps(result, indent=2))
    finally:
        assert path.resolve().is_relative_to((ROOT / "runtime").resolve()) and path.name == subdir
        if path.exists():
            shutil.rmtree(path)


if __name__ == "__main__":
    main()
