import asyncio
import json

import pytest
from fastapi.testclient import TestClient

from terraforma.request_limits import RequestSizeLimitMiddleware, bounded_json_depth
from terraforma.web import create_app


def test_json_depth_boundary_ignores_escaped_quotes_and_brackets_in_strings():
    value = json.dumps('brackets [[[ with quote " and backslash \\')
    bounded_json_depth("[" * 64 + value + "]" * 64)
    with pytest.raises(ValueError, match="nesting"):
        bounded_json_depth("[" * 65 + value + "]" * 65)


@pytest.mark.parametrize(
    "body",
    [
        b'{"verify_target":false,"verify_target":true}',
        b'{"inputs":{"private-marker":false,"private-marker":true}}',
        b'{"value":NaN}',
        b'{"value":Infinity}',
        b'{"value":-Infinity}',
        b'{"value":1e999}',
        b'{"value":-1e999}',
        b'{"private-marker":',
        b'{"value":"\xff"}',
        b"\xff\xfe{\x00}\x00",
        pytest.param(b"[" * 30000 + b"]" * 30000, id="excessive-depth"),
    ],
)
@pytest.mark.parametrize("route", ["/api/projects/preflight", "/api/validate", "/api/generate"])
def test_ambiguous_json_is_rejected_before_tool_or_generation_calls(body, route, monkeypatch):
    def forbidden(*args, **kwargs):
        pytest.fail("Rejected JSON reached a route operation.")

    monkeypatch.setattr("terraforma.web.target_preflight", forbidden)
    monkeypatch.setattr("terraforma.web.configured_project", forbidden)
    monkeypatch.setattr("terraforma.web.ValidationSandbox", forbidden)
    with TestClient(create_app(), base_url="http://127.0.0.1") as client:
        token = client.get("/api/session").json()["token"]
        response = client.post(
            route,
            content=body,
            headers={"X-TerraForma-Token": token, "Content-Type": "application/json"},
        )
    assert response.status_code == 422
    assert "unambiguous UTF-8 JSON" in response.json()["detail"]
    assert "private-marker" not in response.text


@pytest.mark.parametrize(
    "content_type",
    [None, "application/json", "Application/JSON; charset=utf-8", "application/project+json"],
)
def test_strict_json_replays_original_chunked_utf8_bytes(content_type):
    original = json.dumps({"label": "cafÃ©", "nested": [{"value": 1.25}]}).encode("utf-8")
    chunks = [original[:18], original[18:23], original[23:]]
    messages = iter(
        {"type": "http.request", "body": chunk, "more_body": index < len(chunks) - 1}
        for index, chunk in enumerate(chunks)
    )
    headers = [] if content_type is None else [(b"content-type", content_type.encode())]
    scope = {"type": "http", "method": "POST", "path": "/api/generate", "headers": headers}
    captured = []

    async def receive():
        return next(messages)

    async def send(message):
        pytest.fail("Valid JSON was rejected.")

    async def app(scope, receive, send):
        for _ in chunks:
            captured.append(await receive())

    asyncio.run(RequestSizeLimitMiddleware(app)(scope, receive, send))
    assert b"".join(message["body"] for message in captured) == original
    assert [message["more_body"] for message in captured] == [True, True, False]


def test_non_json_content_is_replayed_for_route_specific_parsing():
    original = b"route-specific-content"
    captured = []

    async def receive():
        return {"type": "http.request", "body": original, "more_body": False}

    async def send(message):
        pytest.fail("Non-JSON content was parsed by the middleware.")

    async def app(scope, receive, send):
        captured.append(await receive())

    asyncio.run(
        RequestSizeLimitMiddleware(app)(
            {
                "type": "http",
                "method": "POST",
                "path": "/api/plans/review",
                "headers": [(b"content-type", b"text/plain")],
            },
            receive,
            send,
        )
    )
    assert captured[0]["body"] == original
