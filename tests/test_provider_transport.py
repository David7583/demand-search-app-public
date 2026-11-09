"""No real external requests: exercise SSRF, DNS pinning, bounded HTTP and protocols."""

import io
import json
import ssl

import pytest
from demand_search import providers
from demand_search.errors import AppError
from demand_search.providers import (
    PinnedHTTPSConnection,
    ProviderClient,
    normalize_base,
    resolve_public,
)


@pytest.mark.parametrize(
    "url",
    [
        "http://example.com/v1",
        "https://localhost/v1",
        "https://127.0.0.1/v1",
        "https://2130706433/v1",
        "https://0x7f000001/v1",
        "https://[::1]/v1",
        "https://user:password@example.com/v1",
        "https://example.com:444/v1",
        "https://example.com/v1?key=value",
        "https://example.com/v1#fragment",
        "https://example.com/a/../v1",
        "https://example.com/%2e%2e/v1",
        "https://example.com./v1",
        "https://example.com\\@127.0.0.1/v1",
    ],
)
def test_unsafe_base_rejected(url):
    with pytest.raises(AppError):
        normalize_base(url, "custom")


def test_vendor_key_destination_cannot_be_silently_changed():
    with pytest.raises(AppError, match="PROVIDER_HOST_MISMATCH"):
        normalize_base("https://untrusted.example/v1", "openai")
    assert normalize_base("https://api.openai.com/v1/", "openai") == "https://api.openai.com/v1"


@pytest.mark.parametrize(
    "addresses",
    [
        ["127.0.0.1"],
        ["10.0.0.2"],
        ["169.254.169.254"],
        ["100.64.0.2"],
        ["::1"],
        ["::ffff:8.8.8.8"],
        ["2002:0808:0808::1"],
        ["8.8.8.8", "192.168.1.2"],
    ],
)
def test_any_nonpublic_dns_result_rejects_entire_request(monkeypatch, addresses):
    monkeypatch.setattr(
        providers.socket,
        "getaddrinfo",
        lambda *args: [(2, 1, 6, "", (ip, 443)) for ip in addresses],
    )
    with pytest.raises(AppError, match="SSRF_BLOCKED"):
        resolve_public("example.com")


def test_tls_connects_vetted_ip_but_verifies_original_hostname(monkeypatch):
    called = {}

    class Socket:
        def close(self):
            called["closed"] = True

    raw = Socket()

    class TLS:
        def wrap_socket(self, sock, server_hostname):
            called["sni"] = server_hostname
            return sock

    def connect(address, timeout):
        called["address"] = address
        return raw

    monkeypatch.setattr(providers.socket, "create_connection", connect)
    connection = PinnedHTTPSConnection("models.example.com", "8.8.8.8", 5)
    assert connection._context.verify_mode == ssl.CERT_REQUIRED
    assert connection._context.check_hostname is True
    connection._context = TLS()
    connection.connect()
    assert called["address"] == ("8.8.8.8", 443)
    assert called["sni"] == "models.example.com"


class Response:
    def __init__(self, status=200, raw=b"{}", headers=None):
        self.status = status
        self.file = io.BytesIO(raw)
        self.headers = headers or {}

    def getheader(self, name, default=None):
        return self.headers.get(name, default)

    def read1(self, size):
        return self.file.read(size)


def fake_transport(monkeypatch, response):
    calls = []

    class Connection:
        sock = None

        def __init__(self, *args, **kwargs):
            calls.append(("init", args))

        def request(self, *args, **kwargs):
            calls.append(("request", args, kwargs))

        def getresponse(self):
            return response

        def close(self):
            pass

    monkeypatch.setattr(providers, "resolve_public", lambda host: ["8.8.8.8"])
    monkeypatch.setattr(providers, "PinnedHTTPSConnection", Connection)
    return calls


@pytest.mark.parametrize(
    "status,code",
    [
        (301, "PROVIDER_REDIRECT_BLOCKED"),
        (401, "MODEL_KEY_INVALID"),
        (403, "MODEL_PERMISSION_DENIED"),
        (429, "PROVIDER_RATE_OR_QUOTA_LIMIT"),
    ],
)
def test_errors_never_echo_body_or_follow_redirect(monkeypatch, status, code):
    sentinel = "synthetic-credential-value"
    calls = fake_transport(monkeypatch, Response(status, sentinel.encode()))
    with pytest.raises(AppError, match=code) as error:
        ProviderClient().request_json(
            "https://models.example.com/v1", "custom", sentinel, "GET", "/v1/models"
        )
    assert sentinel not in str(error.value) and sentinel not in error.value.message
    assert len([row for row in calls if row[0] == "request"]) == 1


def test_oversized_response_rejected(monkeypatch):
    fake_transport(monkeypatch, Response(raw=b"x" * (providers.MAX_RESPONSE + 1)))
    with pytest.raises(AppError, match="PROVIDER_RESPONSE_TOO_LARGE"):
        ProviderClient().request_json(
            "https://models.example.com", "custom", "synthetic-key", "GET", "/models"
        )


def test_qwen_directory_and_openai_responses_contract():
    client = ProviderClient()
    calls = []

    def request(base, provider, key, method, path, body=None):
        calls.append((provider, path, body))
        if method == "GET":
            return {"output": {"models": [{"model": "from-real-shaped-directory"}]}}
        value = {"desired_outcome": "chair", "required": [], "preferred": [], "unknown": []}
        return {
            "model": "actual-model",
            "status": "completed",
            "output": [
                {"type": "message", "content": [{"type": "output_text", "text": json.dumps(value)}]}
            ],
        }

    client.request_json = request
    result = client.discover(
        {"provider": "qwen", "base_url": "https://dashscope.aliyuncs.com/compatible-mode/v1"},
        "synthetic-key",
    )
    assert result["models"] == [{"id": "from-real-shaped-directory"}]
    assert calls[-1][1] == "/api/v1/models"
    client.parse(
        {
            "provider": "openai",
            "base_url": "https://api.openai.com/v1",
            "api_mode": "responses",
            "model": "chosen-model",
        },
        "synthetic-key",
        "chair",
    )
    body = calls[-1][2]
    assert calls[-1][1] == "/v1/responses" and body["store"] is False
    assert body["text"]["format"]["strict"] is True
    assert "tools" not in body


@pytest.mark.parametrize(
    "failure,code",
    [
        (TimeoutError("synthetic timeout"), "PROVIDER_TIMEOUT"),
        (ssl.SSLCertVerificationError("synthetic cert"), "TLS_VERIFY_FAILED"),
        (OSError("synthetic network"), "PROVIDER_NETWORK_ERROR"),
    ],
)
def test_transport_failures_are_bounded_and_safe(monkeypatch, failure, code):
    fake_transport(monkeypatch, Response())

    def fail(self, *args, **kwargs):
        raise failure

    monkeypatch.setattr(providers.PinnedHTTPSConnection, "request", fail)
    with pytest.raises(AppError, match=code):
        ProviderClient().request_json(
            "https://models.example.com", "custom", "synthetic-key", "GET", "/models"
        )


def test_dns_failure_has_safe_diagnostic(monkeypatch):
    def fail(*args, **kwargs):
        raise OSError("synthetic resolver details not exposed")

    monkeypatch.setattr(providers.socket, "getaddrinfo", fail)
    with pytest.raises(AppError, match="DNS_FAILED") as result:
        resolve_public("models.example.com")
    assert "resolver details" not in result.value.message
