"""Real local HTTP and Windows DPAPI smoke, exclusively synthetic provider data."""

import hashlib
import http.cookiejar
import json
import os
import socket
import subprocess
import sys
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

from check_environment import require_project_environment

ROOT = Path(__file__).resolve().parents[1]


class Smoke:
    def __init__(self):
        self.run_id = uuid4().hex
        self.test_data = ROOT / "runtime" / ("test-model-http-" + self.run_id)
        self.logs = ROOT / ".local/logs"
        self.logs.mkdir(parents=True, exist_ok=True)
        self.keys = ["synthetic-http-only-" + uuid4().hex for _ in range(2)]
        self.jar = http.cookiejar.CookieJar()
        self.http = urllib.request.build_opener(
            urllib.request.ProxyHandler({}), urllib.request.HTTPCookieProcessor(self.jar)
        )
        self.csrf = None
        self.events = []
        self.processes = []
        self.response_count = 0
        self.child = None
        self.log_handle = None

    def check(self, condition, label):
        if not condition:
            raise RuntimeError(label)
        self.events.append(label)

    def no_keys(self, raw, label):
        self.check(all(key.encode() not in raw for key in self.keys), label)

    def request(self, method, path, body=None, status=200, csrf=True, origin=None):
        headers = {"Origin": origin or self.base}
        if self.csrf and csrf:
            headers["X-DSA-CSRF"] = self.csrf if csrf is True else csrf
        payload = None
        if body is not None:
            payload = json.dumps(body).encode()
            headers["Content-Type"] = "application/json"
        request = urllib.request.Request(
            self.base + path, data=payload, method=method, headers=headers
        )
        try:
            response = self.http.open(request, timeout=8)
        except urllib.error.HTTPError as error:
            response = error
        with response:
            raw = response.read(512 * 1024)
            response_status = response.status
            response_headers = response.headers
        self.response_count += 1
        self.no_keys(raw, f"response_{self.response_count}_no_plaintext_key")
        self.check(response_status == status, f"response_{self.response_count}_status_{status}")
        return json.loads(raw), response_headers

    def start(self, run):
        with socket.socket() as socket_:
            socket_.bind(("127.0.0.1", 0))
            port = socket_.getsockname()[1]
        self.base = f"http://127.0.0.1:{port}"
        log_path = self.logs / f"s2-model-http-{self.run_id}-process-{run}.log"
        self.log_handle = log_path.open("w", encoding="utf-8")
        env = dict(os.environ, PYTHONPATH=str(ROOT / "apps/server/src"))
        self.child = subprocess.Popen(
            [
                sys.executable,
                str(ROOT / "tests/fixtures/model_http_server.py"),
                "--port",
                str(port),
                "--data-subdir",
                self.test_data.name,
            ],
            cwd=ROOT,
            env=env,
            stdout=self.log_handle,
            stderr=self.log_handle,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
        self.processes.append({"run": run, "pid": self.child.pid, "port": port})
        deadline = time.monotonic() + 20
        while True:
            if self.child.poll() is not None:
                raise RuntimeError("synthetic_server_exited")
            try:
                with self.http.open(self.base + "/healthz", timeout=1) as response:
                    healthy = json.load(response)["status"] == "ok"
                self.check(healthy, f"process_{run}_healthy")
                return
            except OSError:
                if time.monotonic() > deadline:
                    raise RuntimeError("synthetic_server_start_timeout") from None
                time.sleep(0.1)

    def stop(self):
        if self.child is not None:
            if self.child.poll() is None:
                self.child.terminate()
                try:
                    self.child.wait(timeout=10)
                except subprocess.TimeoutExpired:
                    self.child.kill()
                    self.child.wait(timeout=5)
            self.child = None
        if self.log_handle is not None:
            self.log_handle.close()
            self.log_handle = None

    def session(self):
        value, headers = self.request("GET", "/api/v1/session", csrf=False)
        self.csrf = value["csrf_token"]
        self.check(value["credential_entry_allowed"], "real_windows_vault_available")
        self.check(
            value["secret_storage"] == "windows_dpapi_current_user",
            "real_windows_dpapi_selected",
        )
        cookie = headers.get("Set-Cookie", "")
        self.check(
            "HttpOnly" in cookie and "SameSite=strict" in cookie,
            "session_cookie_httponly_strict",
        )

    def scan(self, stage, require_ciphertext=False):
        assert self.test_data.resolve().parent == (ROOT / "runtime").resolve()
        for file in self.test_data.rglob("*"):
            if file.is_file():
                self.no_keys(file.read_bytes(), stage + "_database_no_plaintext_key")
        if require_ciphertext:
            raw = (self.test_data / "demand-search.sqlite3").read_bytes()
            self.check(b"DSA-DPAPI-1" in raw, stage + "_dpapi_ciphertext_present")
        if self.log_handle:
            self.log_handle.flush()
        for file in self.logs.glob(f"s2-model-http-{self.run_id}-process-*.log"):
            self.no_keys(file.read_bytes(), stage + "_process_log_no_plaintext_key")

    def draft(self, **changes):
        result = {
            "name": "Synthetic HTTP profile",
            "provider": "custom",
            "base_url": "https://synthetic.example.com/v1",
            "api_mode": "chat_completions",
            "model": "synthetic-v1",
            "api_key": self.keys[0],
            "consent": True,
            "test_text": "synthetic office chair",
        }
        result.update(changes)
        return result

    def save_new(self, **changes):
        ticket, _ = self.request("POST", "/api/v1/config/models/test", self.draft(**changes))
        saved, _ = self.request(
            "POST",
            "/api/v1/config/models/save",
            {"validation_id": ticket["validation_id"], "make_active": True},
        )
        return saved

    def run(self):
        self.start(1)
        value, _ = self.request("GET", "/api/v1/config/models", status=401)
        self.check(value["error"]["code"] == "LOCAL_SESSION_REQUIRED", "session_required")
        self.request("GET", "/api/v1/session", status=403, origin="https://cross-site.example")
        self.session()
        self.request("POST", "/api/v1/config/models/discover", self.draft(), 403, csrf=False)
        self.request("POST", "/api/v1/config/models/discover", self.draft(), 403, csrf="wrong")
        self.request(
            "POST",
            "/api/v1/config/models/discover",
            self.draft(),
            403,
            origin="https://cross-site.example",
        )
        self.request("POST", "/api/v1/config/models/test", {"api_key": self.keys[0]}, 422)
        found, _ = self.request("POST", "/api/v1/config/models/discover", self.draft())
        self.check(found["discovery_supported"] and len(found["models"]) == 3, "discovery_http")
        ticket, _ = self.request("POST", "/api/v1/config/models/test", self.draft())
        result = ticket["result"]
        self.check(
            result["parsed"]["unknown"] == ["[REDACTED]"], "malicious_provider_echo_redacted"
        )
        self.check(
            result["actual_model"].endswith(hashlib.sha256(self.keys[0].encode()).hexdigest()[:16]),
            "provider_used_exact_synthetic_key",
        )
        self.check(
            result["parsed"]["original_text"] == self.draft()["test_text"]
            and result["parsed"]["user_confirmed"] is False,
            "original_text_and_confirmation_boundary",
        )
        value, _ = self.request("GET", "/api/v1/config/models")
        self.check(value == {"configs": [], "active_id": None}, "test_does_not_activate")
        self.scan("pending_ticket", require_ciphertext=True)
        saved, _ = self.request(
            "POST",
            "/api/v1/config/models/save",
            {"validation_id": ticket["validation_id"], "make_active": True},
        )
        first_id = saved["config"]["id"]
        self.check(saved["active_id"] == first_id, "first_profile_saved_active")
        self.request(
            "POST",
            "/api/v1/config/models/save",
            {"validation_id": ticket["validation_id"]},
            status=409,
        )
        self.scan("saved_profile", require_ciphertext=True)
        self.stop()

        self.start(2)
        self.request("GET", "/api/v1/config/models", status=401)
        self.session()
        profiles, _ = self.request("GET", "/api/v1/config/models")
        self.check(profiles["active_id"] == first_id, "saved_default_survived_process_restart")
        parsed, _ = self.request(
            "POST", "/api/v1/config/parse", {"text": "synthetic restart request", "consent": True}
        )
        self.check(
            parsed["actual_model"].endswith(hashlib.sha256(self.keys[0].encode()).hexdigest()[:16]),
            "restart_dpapi_decrypted_exact_key",
        )
        failed, _ = self.request(
            "POST",
            "/api/v1/config/models/test",
            self.draft(existing_id=first_id, api_key=None, model="synthetic-failure"),
            status=502,
        )
        self.check(failed["error"]["code"] == "MODEL_KEY_INVALID", "upstream_failure_diagnostic")
        profiles, _ = self.request("GET", "/api/v1/config/models")
        self.check(
            profiles["active_id"] == first_id and profiles["configs"][0]["model"] == "synthetic-v1",
            "failed_edit_kept_previous_valid_profile",
        )
        edited = self.save_new(existing_id=first_id, api_key=None, model="synthetic-v2")
        self.check(
            edited["config"]["id"] == first_id and edited["config"]["model"] == "synthetic-v2",
            "edited_profile_replaced_only_after_verified_save",
        )
        second = self.save_new(name="Synthetic second profile", api_key=self.keys[1])
        second_id = second["config"]["id"]
        self.check(
            second_id != first_id and second["active_id"] == second_id, "second_profile_added"
        )
        switched, _ = self.request("POST", f"/api/v1/config/models/{first_id}/activate", {})
        self.check(switched["active_id"] == first_id, "active_profile_switched")
        self.scan("restarted_edited_profiles", require_ciphertext=True)
        deleted, _ = self.request("DELETE", f"/api/v1/config/models/{first_id}", {})
        self.check(deleted["active_id"] is None, "active_delete_does_not_switch_provider")
        self.request(
            "POST",
            "/api/v1/config/parse",
            {"text": "synthetic no default", "consent": True},
            status=409,
        )
        parsed, _ = self.request(
            "POST",
            "/api/v1/config/parse",
            {"text": "synthetic explicit profile", "consent": True, "config_id": second_id},
        )
        self.check(
            parsed["actual_model"].endswith(hashlib.sha256(self.keys[1].encode()).hexdigest()[:16]),
            "explicit_profile_used_correct_independent_key",
        )
        self.request("DELETE", f"/api/v1/config/models/{second_id}", {})
        profiles, _ = self.request("GET", "/api/v1/config/models")
        self.check(profiles == {"configs": [], "active_id": None}, "profiles_deleted")
        self.stop()
        self.scan("final_deleted_state")


def main():
    require_project_environment()
    if sys.platform != "win32":
        raise SystemExit("This smoke requires real Windows current-user DPAPI.")
    smoke = Smoke()
    failure = None
    try:
        smoke.run()
    except Exception as error:
        failure = type(error).__name__
    finally:
        smoke.stop()
    report = {
        "passed": failure is None,
        "failure_type": failure,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "run_id": smoke.run_id,
        "data_subdirectory": smoke.test_data.relative_to(ROOT).as_posix(),
        "transport": "real loopback HTTP between independent client/server processes",
        "secret_storage": "real Windows current-user DPAPI; no vault substitute",
        "provider": "explicit synthetic fixture; no external model requests",
        "external_ai_verified": False,
        "production_network_verified": False,
        "processes": smoke.processes,
        "checks_passed": len(smoke.events),
        "http_responses_checked": smoke.response_count,
        "checks": smoke.events,
    }
    output = json.dumps(report, indent=2) + "\n"
    smoke.no_keys(output.encode(), "report_no_plaintext_key")
    (smoke.logs / f"s2-model-http-{smoke.run_id}.json").write_text(output, encoding="utf-8")
    (smoke.logs / "s2-model-http.json").write_text(output, encoding="utf-8")
    print(output)
    return 0 if failure is None else 1


if __name__ == "__main__":
    raise SystemExit(main())
