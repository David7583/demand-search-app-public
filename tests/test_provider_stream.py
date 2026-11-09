"""Synthetic SSE transport tests. No credentials, internet or user data."""

import json

import pytest
from demand_search import providers
from demand_search.errors import AppError
from demand_search.providers import JsonStreamRedactor, ProviderClient, collect_stream, iter_sse
from test_provider_transport import Response, fake_transport

CONFIG = {
    "provider": "custom",
    "base_url": "https://model.example/v1",
    "api_mode": "chat_completions",
    "model": "requested-model",
}
KEY = 'synthetic-"credential\\value'
VALUE = {
    "desired_outcome": "先给三条路径，随后讨论 🪑",
    "required": [],
    "preferred": [],
    "unknown": [],
}


def event(value, *, name=None):
    raw = value if isinstance(value, str) else json.dumps(value, ensure_ascii=False)
    return ((("event: " + name + "\r\n") if name else "") + "data: " + raw + "\r\n\r\n").encode()


def chat(delta=None, finish=None, **extra):
    return {
        "model": "actual-model",
        "choices": [{"index": 0, "delta": delta or {}, "finish_reason": finish}],
        **extra,
    }


def wire_for(text, split=23, finish="stop", done=True):
    pieces = [event(chat({"role": "assistant", "reasoning_content": "MUST_NOT_DISPLAY"}))]
    pieces += [event(chat({"content": text[i : i + split]})) for i in range(0, len(text), split)]
    pieces.append(event(chat(finish=finish)))
    if done:
        pieces.append(event("[DONE]"))
    return b"".join(pieces)


class Chunked(Response):
    def __init__(self, raw, chunk_size=7, headers=None, status=200):
        super().__init__(
            status=status,
            raw=raw,
            headers=headers or {"Content-Type": "text/event-stream; charset=utf-8"},
        )
        self.chunk_size = chunk_size

    def read1(self, size):
        return super().read1(min(size, self.chunk_size))


def call(monkeypatch, raw, **response_options):
    response = Chunked(raw, **response_options)
    calls = fake_transport(monkeypatch, response)
    deltas = []
    result = ProviderClient().parse(CONFIG, KEY, "synthetic request", on_delta=deltas.append)
    return result, deltas, calls


def test_live_chunks_utf8_crlf_final_schema_and_no_reasoning(monkeypatch):
    result, deltas, calls = call(monkeypatch, wire_for(json.dumps(VALUE, ensure_ascii=False)))
    assert result["parsed"]["desired_outcome"] == VALUE["desired_outcome"]
    assert result["actual_model"] == "actual-model"
    assert len(deltas) > 2
    assert "MUST_NOT_DISPLAY" not in "".join(deltas)
    assert json.loads("".join(deltas)) == VALUE
    requests = [row for row in calls if row[0] == "request"]
    assert len(requests) == 1
    assert json.loads(requests[0][2]["body"])["stream"] is True
    assert requests[0][2]["headers"]["Accept"] == "text/event-stream"


def test_delta_delivered_before_provider_has_finished_reading(monkeypatch):
    text = json.dumps(VALUE, ensure_ascii=False)
    prefix = event(chat({"content": text[:50]}))
    suffix = event(chat({"content": text[50:]})) + event(chat(finish="stop")) + event("[DONE]")
    callbacks = []

    class Observable(Chunked):
        def __init__(self):
            super().__init__(prefix + suffix, chunk_size=len(prefix))
            self.first = True

        def read1(self, size):
            if not self.first:
                assert callbacks, "No real incremental output was delivered before next read"
            self.first = False
            return super().read1(size)

    fake_transport(monkeypatch, Observable())
    ProviderClient().parse(CONFIG, KEY, "synthetic", on_delta=callbacks.append)


@pytest.mark.parametrize("encoding", ["plain", "unicode", "mixed"])
def test_key_never_crosses_callback_even_when_escaped_and_split(monkeypatch, encoding):
    value = {**VALUE, "desired_outcome": "before " + KEY + " after"}
    text = json.dumps(value, ensure_ascii=False)
    if encoding != "plain":
        encoded = "".join(
            "\\u%04x" % ord(c) if encoding == "unicode" or i % 2 else json.dumps(c)[1:-1]
            for i, c in enumerate(KEY)
        )
        text = text.replace(json.dumps(KEY)[1:-1], encoded)
    result, deltas, _ = call(monkeypatch, wire_for(text, split=1), chunk_size=1)
    displayed = json.loads("".join(deltas))["desired_outcome"]
    assert KEY not in displayed and "[REDACTED]" in displayed
    assert KEY not in json.dumps(result)
    assert result["parsed"]["desired_outcome"] == displayed


@pytest.mark.parametrize(
    "finish,done,code",
    [
        ("length", True, "AI_OUTPUT_INCOMPLETE"),
        ("content_filter", True, "AI_OUTPUT_INCOMPLETE"),
        ("tool_calls", True, "AI_OUTPUT_INCOMPLETE"),
        ("stop", False, "PROVIDER_STREAM_INVALID"),
    ],
)
def test_truncation_and_missing_terminal_never_retried(monkeypatch, finish, done, code):
    calls = fake_transport(
        monkeypatch, Chunked(wire_for(json.dumps(VALUE), finish=finish, done=done))
    )
    with pytest.raises(AppError, match=code):
        ProviderClient().parse(CONFIG, KEY, "synthetic", on_delta=lambda _: None)
    assert len([row for row in calls if row[0] == "request"]) == 1


@pytest.mark.parametrize(
    "raw,code",
    [
        (event(chat({"refusal": "no"})), "AI_REFUSED"),
        (event({"error": {"message": KEY}}), "PROVIDER_STREAM_ERROR"),
        (event(chat({"tool_calls": [{"id": "forbidden"}]})), "PROVIDER_STREAM_INVALID"),
        (event(chat({"role": "tool", "content": "forbidden"})), "PROVIDER_STREAM_INVALID"),
        (event(chat({"content": "bad"}, choices=[{}, {}])), "PROVIDER_STREAM_INVALID"),
        (b'data: {"choices":[],"choices":[]}\n\n', "PROVIDER_STREAM_INVALID"),
        (b"data: \xff\n\n", "PROVIDER_STREAM_INVALID"),
    ],
)
def test_malformed_or_untrusted_stream_fails_without_error_body(monkeypatch, raw, code):
    calls = fake_transport(monkeypatch, Chunked(raw))
    with pytest.raises(AppError, match=code) as error:
        ProviderClient().parse(CONFIG, KEY, "synthetic", on_delta=lambda _: None)
    assert KEY not in str(error.value)
    assert len([row for row in calls if row[0] == "request"]) == 1


def responses_wire(text, *, status="completed", final_text=None):
    created = {"type": "response.created", "response": {"model": "actual-model"}}
    events = [event(created, name=created["type"])]
    events.append(
        event({"type": "response.reasoning_summary_text.delta", "delta": "PRIVATE_THINKING"})
    )
    for i in range(0, len(text), 13):
        row = {
            "type": "response.output_text.delta",
            "output_index": 1,
            "content_index": 0,
            "item_id": "message1",
            "delta": text[i : i + 13],
        }
        events.append(event(row, name=row["type"]))
    final = {
        "type": "response.completed",
        "response": {
            "status": status,
            "model": "actual-model",
            "output": [
                {"type": "reasoning", "summary": []},
                {
                    "type": "message",
                    "role": "assistant",
                    "content": [
                        {"type": "output_text", "text": text if final_text is None else final_text},
                    ],
                },
            ],
        },
    }
    events.append(event(final, name=final["type"]))
    return b"".join(events)


def test_responses_stream_tracks_text_channel_not_reasoning_index(monkeypatch):
    fake_transport(monkeypatch, Chunked(responses_wire(json.dumps(VALUE))))
    delta = []
    result = ProviderClient().parse(
        {**CONFIG, "api_mode": "responses"},
        KEY,
        "synthetic",
        on_delta=delta.append,
    )
    assert result["parsed"]["desired_outcome"] == VALUE["desired_outcome"]
    assert "PRIVATE_THINKING" not in "".join(delta)


@pytest.mark.parametrize("kwargs", [{"status": "incomplete"}, {"final_text": "different"}])
def test_responses_completion_must_match_generated_text(monkeypatch, kwargs):
    fake_transport(monkeypatch, Chunked(responses_wire(json.dumps(VALUE), **kwargs)))
    with pytest.raises(AppError, match="PROVIDER_STREAM_INVALID"):
        ProviderClient().parse(
            {**CONFIG, "api_mode": "responses"},
            KEY,
            "synthetic",
            on_delta=lambda _: None,
        )


@pytest.mark.parametrize(
    "kind,code",
    [
        ("response.failed", "AI_OUTPUT_INCOMPLETE"),
        ("response.incomplete", "AI_OUTPUT_INCOMPLETE"),
        ("response.refusal.delta", "AI_REFUSED"),
    ],
)
def test_responses_error_events_fail_closed(monkeypatch, kind, code):
    fake_transport(monkeypatch, Chunked(event({"type": kind, "message": KEY})))
    with pytest.raises(AppError, match=code):
        ProviderClient().parse(
            {**CONFIG, "api_mode": "responses"},
            KEY,
            "synthetic",
            on_delta=lambda _: None,
        )


@pytest.mark.parametrize(
    "status,headers,code",
    [
        (302, None, "PROVIDER_REDIRECT_BLOCKED"),
        (401, None, "MODEL_KEY_INVALID"),
        (200, {"Content-Type": "application/json"}, "PROVIDER_STREAM_UNSUPPORTED"),
        (
            200,
            {"Content-Type": "text/event-stream", "Content-Encoding": "gzip"},
            "PROVIDER_STREAM_INVALID",
        ),
    ],
)
def test_stream_transport_preserves_safe_http_boundaries(monkeypatch, status, headers, code):
    calls = fake_transport(monkeypatch, Chunked(KEY.encode(), status=status, headers=headers))
    with pytest.raises(AppError, match=code) as error:
        ProviderClient().parse(CONFIG, KEY, "synthetic", on_delta=lambda _: None)
    assert KEY not in str(error.value)
    assert len([row for row in calls if row[0] == "request"]) == 1


def test_stream_byte_limit(monkeypatch):
    fake_transport(monkeypatch, Chunked(b": " + b"x" * providers.MAX_RESPONSE, chunk_size=16384))
    with pytest.raises(AppError, match="PROVIDER_RESPONSE_TOO_LARGE"):
        ProviderClient().parse(CONFIG, KEY, "synthetic", on_delta=lambda _: None)


def test_event_limit_and_partial_framing_rejected():
    with pytest.raises(AppError, match="PROVIDER_STREAM_INVALID"):
        list(iter_sse([event("{}") * 16385]))
    with pytest.raises(AppError, match="PROVIDER_STREAM_INVALID"):
        list(iter_sse([b'data: {"x":1}']))


def test_stream_concurrency_slot_released_on_failure(monkeypatch):
    semaphore = providers.threading.BoundedSemaphore(1)
    monkeypatch.setattr(providers, "STREAM_SLOTS", semaphore)
    semaphore.acquire()
    with pytest.raises(AppError, match="PROVIDER_BUSY"):
        ProviderClient().parse(CONFIG, KEY, "synthetic", on_delta=lambda _: None)
    semaphore.release()
    fake_transport(monkeypatch, Chunked(b"invalid"))
    with pytest.raises(AppError):
        ProviderClient().parse(CONFIG, KEY, "synthetic", on_delta=lambda _: None)
    assert semaphore.acquire(blocking=False)
    semaphore.release()


def test_callback_cancellation_propagates_without_retry(monkeypatch):
    calls = fake_transport(monkeypatch, Chunked(wire_for(json.dumps(VALUE))))

    def cancel(_):
        raise AppError("COLLABORATION_CANCELLED", "synthetic cancelled", 409)

    with pytest.raises(AppError, match="COLLABORATION_CANCELLED"):
        ProviderClient().parse(CONFIG, KEY, "synthetic", on_delta=cancel)
    assert len([row for row in calls if row[0] == "request"]) == 1


def test_schema_validation_still_applies_after_deltas(monkeypatch):
    fake_transport(monkeypatch, Chunked(wire_for('{"desired_outcome":"incomplete"}')))
    with pytest.raises(AppError, match="AI_SCHEMA_INVALID"):
        ProviderClient().parse(CONFIG, KEY, "synthetic", on_delta=lambda _: None)


def test_redactor_rejects_incomplete_json_strings_without_exposing_suffix():
    seen = []
    guard = JsonStreamRedactor(KEY, seen.append)
    guard.feed('{"a":"before ' + json.dumps(KEY)[1:-1])
    with pytest.raises(AppError, match="AI_SCHEMA_INVALID"):
        guard.finish()
    assert KEY not in "".join(seen)


def test_no_sse_reasoning_or_usage_can_be_mistaken_for_assistant_text():
    seen = []
    with pytest.raises(AppError, match="PROVIDER_STREAM_INVALID"):
        collect_stream(
            [
                ("", json.dumps(chat({"reasoning_content": "hidden"}, finish="stop"))),
                ("", "[DONE]"),
            ],
            "chat_completions",
            seen.append,
        )
    assert seen == []


def test_redaction_marker_cannot_itself_equal_or_contain_the_key():
    seen = []
    guard = JsonStreamRedactor("REDACTED", seen.append)
    for part in ['{"text":"RE', 'DACTED"}']:
        guard.feed(part)
    guard.finish()
    assert json.loads("".join(seen)) == {"text": "*"}


def test_api_strict_schema_requires_new_optional_legacy_fields_without_mutation():
    source = {
        "type": "object",
        "properties": {
            "reply": {"type": "string", "default": ""},
            "nested": {
                "anyOf": [
                    {"type": "null"},
                    {"type": "object", "properties": {"x": {"type": "string", "default": "x"}}},
                ],
                "default": None,
            },
        },
        "required": [],
    }
    strict = providers.strict_response_schema(source)
    assert strict["required"] == ["reply", "nested"]
    assert strict["properties"]["nested"]["anyOf"][1]["required"] == ["x"]
    assert "default" not in strict["properties"]["reply"]
    assert source["required"] == [] and source["properties"]["reply"]["default"] == ""


@pytest.mark.parametrize(
    "raw,key",
    [
        ('{"number":12345678}', "12345678"),
        ("secretvalue", "secretvalue"),
        ('{"a":secretvalue}', "secretvalue"),
    ],
)
def test_invalid_plaintext_or_numeric_credential_is_never_streamed(raw, key):
    seen = []
    guard = JsonStreamRedactor(key, seen.append)
    with pytest.raises(AppError):
        for char in raw:
            guard.feed(char)
        guard.finish()
    assert key not in "".join(seen)


def test_json_redactor_preserves_null_boolean_numbers_and_pretty_printed_whitespace():
    value = {
        "nullable": None,
        "truth": True,
        "false": False,
        "amount": 123.5,
        "nested": [1, -2.3e-5],
    }
    raw = json.dumps(value, indent=2)
    chunks = []
    guard = JsonStreamRedactor(KEY, chunks.append)
    for char in raw:
        guard.feed(char)
    guard.finish()
    assert json.loads("".join(chunks)) == value


@pytest.mark.parametrize(
    "failure,code",
    [
        (TimeoutError("private timeout details"), "PROVIDER_TIMEOUT"),
        (providers.ssl.SSLCertVerificationError("private TLS details"), "TLS_VERIFY_FAILED"),
        (OSError("private socket details"), "PROVIDER_NETWORK_ERROR"),
    ],
)
def test_stream_network_errors_do_not_leak_details_or_retry(monkeypatch, failure, code):
    calls = fake_transport(monkeypatch, Chunked(b""))

    def fail(*args, **kwargs):
        raise failure

    monkeypatch.setattr(providers.PinnedHTTPSConnection, "getresponse", fail)
    with pytest.raises(AppError, match=code) as error:
        ProviderClient().parse(CONFIG, KEY, "synthetic", on_delta=lambda _: None)
    assert "private" not in error.value.message
    assert len([row for row in calls if row[0] == "request"]) == 1


def test_stream_total_deadline_applies_before_any_extra_read(monkeypatch):
    fake_transport(monkeypatch, Chunked(wire_for(json.dumps(VALUE))))
    ticks = iter([0, 0, 46])
    monkeypatch.setattr(providers.time, "monotonic", lambda: next(ticks))
    with pytest.raises(AppError, match="PROVIDER_TIMEOUT"):
        ProviderClient().parse(CONFIG, KEY, "synthetic", on_delta=lambda _: None)
