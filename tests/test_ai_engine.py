import asyncio
import json

import httpx
import pytest

from terraforma.ai_engine import AIDiagnosticsEngine, DiagnosticsError, redact_sensitive_text


def completion(content, finish="stop", refusal=None):
    return {
        "choices": [{"finish_reason": finish, "message": {"content": content, "refusal": refusal}}]
    }


def diagnose(handler, *, attempts=1):
    async def execute():
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            return await AIDiagnosticsEngine(
                api_key="test-api-key", client=client, max_attempts=attempts
            ).diagnose("password = secret-value; test-api-key")

    return asyncio.run(execute())


def test_http_payload_and_validated_response():
    def handler(request):
        payload = json.loads(request.content)
        assert str(request.url) == AIDiagnosticsEngine.endpoint
        assert request.headers["Authorization"] == "Bearer test-api-key"
        assert payload["model"] == "gpt-4o"
        assert payload["response_format"]["json_schema"]["strict"] is True
        assert "secret-value" not in request.content.decode()
        assert "test-api-key" not in request.content.decode()
        return httpx.Response(
            200,
            json=completion(
                json.dumps(
                    {
                        "friendly_explanation": "Missing provider",
                        "recommended_fix": "Add required_providers",
                    }
                )
            ),
        )

    assert diagnose(handler)["friendly_explanation"] == "Missing provider"


@pytest.mark.parametrize(
    "body",
    [
        {},
        {"choices": [None]},
        {"choices": [{"message": None}]},
        completion("not JSON"),
        completion('{"friendly_explanation": "hi"}'),
        completion('{"friendly_explanation": 1, "recommended_fix": "fix"}'),
        completion('{"friendly_explanation": "hi", "recommended_fix": "fix", "extra": true}'),
        completion("{}", finish="length"),
        completion(None, refusal="refused"),
    ],
)
def test_invalid_ai_responses_fail_cleanly(body):
    with pytest.raises(DiagnosticsError):
        diagnose(lambda request: httpx.Response(200, json=body))


def test_duplicate_completion_envelope_is_rejected_without_echoing_response():
    content = b'{"choices":[],"choices":[{"finish_reason":"stop","message":{"content":"private-marker"}}]}'
    with pytest.raises(DiagnosticsError, match="invalid diagnostic response") as error:
        diagnose(lambda request: httpx.Response(200, content=content))
    assert "private-marker" not in str(error.value)


@pytest.mark.parametrize(
    "content",
    [
        '{"friendly_explanation":"private-marker","friendly_explanation":"hi","recommended_fix":"fix"}',
        '{"friendly_explanation":"hi","recommended_fix":"fix","ignored":1e999}',
        "[" * 65 + "0" + "]" * 65,
    ],
)
def test_ambiguous_diagnostic_content_is_rejected_without_echoing_response(content):
    with pytest.raises(DiagnosticsError, match="invalid diagnostic response") as error:
        diagnose(lambda request: httpx.Response(200, json=completion(content)))
    assert "private-marker" not in str(error.value)


def test_transient_status_retries():
    calls = []

    def handler(request):
        calls.append(request)
        if len(calls) == 1:
            return httpx.Response(429, headers={"Retry-After": "0"})
        return httpx.Response(
            200, json=completion('{"friendly_explanation": "hi", "recommended_fix": "fix"}')
        )

    assert diagnose(handler, attempts=2)["recommended_fix"] == "fix"
    assert len(calls) == 2


def test_auth_failure_does_not_leak_server_body_or_key():
    with pytest.raises(DiagnosticsError, match="HTTP 401") as error:
        diagnose(lambda request: httpx.Response(401, text="test-api-key"))
    assert "test-api-key" not in str(error.value)


def test_network_failure_is_readable():
    def handler(request):
        raise httpx.ConnectError("network down", request=request)

    with pytest.raises(DiagnosticsError, match="could not be reached"):
        diagnose(handler)


def test_missing_key(monkeypatch):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    with pytest.raises(DiagnosticsError, match="OPENAI_API_KEY"):
        AIDiagnosticsEngine()


@pytest.mark.parametrize("timeout", [0, -1, float("nan"), float("inf"), True, "30", 121])
def test_nonfinite_or_unsupported_timeouts_are_rejected(timeout):
    with pytest.raises(ValueError, match="finite HTTP timeout"):
        AIDiagnosticsEngine(api_key="test-key", timeout=timeout)


@pytest.mark.parametrize("attempts", [True, 1.5, "3", 0, 6])
def test_attempt_limit_requires_a_bounded_integer(attempts):
    with pytest.raises(ValueError, match="integer attempts"):
        AIDiagnosticsEngine(api_key="test-key", max_attempts=attempts)


class ObservedStream(httpx.AsyncByteStream):
    def __init__(self, chunks, delay=0):
        self.chunks = chunks
        self.delay = delay
        self.reads = 0
        self.closed = False

    async def __aiter__(self):
        for chunk in self.chunks:
            self.reads += 1
            if self.delay:
                await asyncio.sleep(self.delay)
            yield chunk

    async def aclose(self):
        self.closed = True


def test_oversized_stream_stops_reading_closes_and_omits_body():
    stream = ObservedStream([b"private-marker".ljust(8192, b"x")] * 20)
    with pytest.raises(DiagnosticsError, match="64 KiB limit") as error:
        diagnose(lambda request: httpx.Response(200, stream=stream))
    assert stream.closed and stream.reads == 9
    assert "private-marker" not in str(error.value)


def test_response_at_exact_byte_limit_is_accepted_and_closed():
    raw = json.dumps(completion('{"friendly_explanation":"hi","recommended_fix":"fix"}')).encode()
    stream = ObservedStream([raw + b" " * (64 * 1024 - len(raw))])
    assert diagnose(lambda request: httpx.Response(200, stream=stream))["recommended_fix"] == "fix"
    assert stream.closed


def test_error_response_body_is_not_read_and_is_closed():
    stream = ObservedStream([b"private-marker"])
    with pytest.raises(DiagnosticsError, match="HTTP 401"):
        diagnose(lambda request: httpx.Response(401, stream=stream))
    assert stream.closed and stream.reads == 0


def test_absolute_attempt_timeout_closes_slow_response():
    stream = ObservedStream([b"{"], delay=0.1)

    async def execute():
        async with httpx.AsyncClient(
            transport=httpx.MockTransport(lambda request: httpx.Response(200, stream=stream))
        ) as client:
            await AIDiagnosticsEngine(
                api_key="test-key", client=client, timeout=0.01, max_attempts=1
            ).diagnose("log")

    with pytest.raises(DiagnosticsError, match="could not be reached"):
        asyncio.run(execute())
    assert stream.closed


def test_injected_client_cannot_follow_diagnostic_redirects():
    calls = []

    def handler(request):
        calls.append(str(request.url))
        return httpx.Response(302, headers={"Location": "https://different.example/private-marker"})

    async def execute():
        async with httpx.AsyncClient(
            transport=httpx.MockTransport(handler), follow_redirects=True
        ) as client:
            await AIDiagnosticsEngine(api_key="test-key", client=client, max_attempts=1).diagnose(
                "log"
            )

    with pytest.raises(DiagnosticsError, match="HTTP 302"):
        asyncio.run(execute())
    assert calls == [AIDiagnosticsEngine.endpoint]


@pytest.mark.parametrize(
    "retry_after,expected",
    [("NaN", 1), ("Infinity", 1), ("private-marker", 1), ("1000", 10), ("-3", 0)],
)
def test_retry_delays_are_finite_and_bounded(retry_after, expected, monkeypatch):
    calls = []
    delays = []

    async def sleep(delay):
        delays.append(delay)

    def handler(request):
        calls.append(request)
        if len(calls) == 1:
            return httpx.Response(429, headers={"Retry-After": retry_after})
        return httpx.Response(
            200, json=completion('{"friendly_explanation":"hi","recommended_fix":"fix"}')
        )

    monkeypatch.setattr("terraforma.ai_engine.asyncio.sleep", sleep)
    assert diagnose(handler, attempts=2)["recommended_fix"] == "fix"
    assert delays == [expected]


def test_redaction_of_environment_values_and_private_key(monkeypatch):
    monkeypatch.setenv("CUSTOM_TOKEN", "test-secret-token")
    text = 'test-secret-token\napi_key = "my-key"\n-----BEGIN RSA PRIVATE KEY-----\nprivate\n-----END RSA PRIVATE KEY-----'
    clean = redact_sensitive_text(text)
    assert "test-secret-token" not in clean
    assert '"my-key"' not in clean
    assert "\nprivate\n" not in clean


def test_model_defaults_and_environment_override(monkeypatch):
    monkeypatch.delenv("TERRAFORMA_OPENAI_MODEL", raising=False)
    assert AIDiagnosticsEngine(api_key="k").model == "gpt-4o"
    monkeypatch.setenv("TERRAFORMA_OPENAI_MODEL", " gpt-4.1-mini ")
    assert AIDiagnosticsEngine(api_key="k").model == "gpt-4.1-mini"
    assert AIDiagnosticsEngine(api_key="k", model="gpt-4o").model == "gpt-4o"
    monkeypatch.setenv("TERRAFORMA_OPENAI_MODEL", "")
    assert AIDiagnosticsEngine(api_key="k").model == "gpt-4o"


@pytest.mark.parametrize("value", ["bad model", "-leading", "x" * 129, "model\nname"])
def test_invalid_model_name_is_rejected(monkeypatch, value):
    monkeypatch.setenv("TERRAFORMA_OPENAI_MODEL", value)
    with pytest.raises(DiagnosticsError):
        AIDiagnosticsEngine(api_key="k")
