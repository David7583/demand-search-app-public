"""Explicit synthetic-provider fixture; never loadable through a production mock flag."""

import argparse
import hashlib
import json
import re

import uvicorn
from demand_search.config import ROOT, Settings
from demand_search.errors import AppError
from demand_search.main import create_app
from demand_search.providers import ProviderClient


class SyntheticProvider(ProviderClient):
    """Exercise actual provider response parsing without any external network request."""

    def request_json(self, base_url, provider, api_key, method, path, body=None):
        if provider != "custom" or not api_key.startswith("synthetic-http-only-"):
            raise AppError("SYNTHETIC_FIXTURE_ONLY", "Fixture accepts synthetic credentials only.")
        if method == "GET" and path == "/v1/models":
            return {
                "data": [
                    {"id": "synthetic-v1"},
                    {"id": "synthetic-v2"},
                    {"id": "synthetic-failure"},
                ]
            }
        if method != "POST" or path != "/v1/chat/completions":
            raise AppError("SYNTHETIC_FIXTURE_ONLY", "Unsupported synthetic request.")
        if body["model"] == "synthetic-failure":
            raise AppError("MODEL_KEY_INVALID", "Synthetic provider authentication failure.", 502)
        text = body["messages"][-1]["content"]
        parsed = {
            "desired_outcome": "synthetic preview",
            "required": [{"text": text[:20], "source": "user_explicit", "evidence": text[:20]}],
            "preferred": [],
            # Deliberate malicious echo: production ProviderClient must redact it.
            "unknown": [api_key],
        }
        return {
            "model": body["model"] + "-reply-" + hashlib.sha256(api_key.encode()).hexdigest()[:16],
            "choices": [{"finish_reason": "stop", "message": {"content": json.dumps(parsed)}}],
        }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--port", type=int, required=True)
    parser.add_argument("--data-subdir", required=True)
    args = parser.parse_args()
    if not re.fullmatch(r"test-model-http-[0-9a-f]{32}", args.data_subdir):
        raise SystemExit("Fixture requires an explicit isolated synthetic test directory.")
    target = (ROOT / "runtime" / args.data_subdir).resolve()
    if target.parent != (ROOT / "runtime").resolve():
        raise SystemExit("Fixture data directory escaped project runtime.")
    if not 1024 <= args.port <= 65535:
        raise SystemExit("Invalid loopback test port.")
    app = create_app(Settings(data_dir=target), provider_client=SyntheticProvider())
    uvicorn.run(
        app,
        host="127.0.0.1",
        port=args.port,
        proxy_headers=False,
        access_log=False,
        log_level="error",
    )


if __name__ == "__main__":
    main()
