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


def test_redaction_of_environment_values_and_private_key(monkeypatch):
    monkeypatch.setenv("CUSTOM_TOKEN", "test-secret-token")
    text = 'test-secret-token\napi_key = "my-key"\n-----BEGIN RSA PRIVATE KEY-----\nprivate\n-----END RSA PRIVATE KEY-----'
    clean = redact_sensitive_text(text)
    assert "test-secret-token" not in clean
    assert '"my-key"' not in clean
    assert "\nprivate\n" not in clean
