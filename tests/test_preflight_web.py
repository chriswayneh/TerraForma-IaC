import asyncio
import json
import threading

import httpx
import pytest
from fastapi.testclient import TestClient

from terraforma.generator import WizardConfig
from terraforma.process import CommandResult
from terraforma.project import ProjectSpecification
from terraforma.web import create_app


def specification(provider="aws"):
    return ProjectSpecification(
        recipe=WizardConfig(
            provider=provider, project_name="target-test", architecture_type="static_site"
        ),
        inputs={
            "aws": {"aws_account_id": "123456789012"},
            "azure": {"subscription_id": "abcdef12-1234-1234-1234-123456789abc"},
            "gcp": {"gcp_project_id": "example-project"},
        }[provider],
    ).model_dump()


def headers(client):
    return {"X-TerraForma-Token": client.get("/api/session").json()["token"]}


@pytest.mark.parametrize("provider", ["aws", "azure", "gcp"])
@pytest.mark.parametrize("opt_in", [False, True])
def test_route_requires_opt_in_for_cloud_execution_and_omits_raw_values(
    provider, opt_in, monkeypatch
):
    calls = []
    data = {
        "aws": {"Account": "123456789012", "Arn": "private-principal-marker"},
        "azure": {"subscriptionId": "abcdef12-1234-1234-1234-123456789abc", "state": "Enabled"},
        "gcp": {"projectId": "example-project", "lifecycleState": "ACTIVE"},
    }[provider]

    def run(*args, **kwargs):
        calls.append(kwargs)
        return CommandResult(0, json.dumps(data).encode(), b"private-diagnostics")

    monkeypatch.setattr("terraforma.preflight.shutil.which", lambda name: "fake-cli")
    monkeypatch.setattr("terraforma.preflight.run_bounded", run)
    with TestClient(create_app(), base_url="http://127.0.0.1") as client:
        response = client.post(
            "/api/projects/preflight",
            headers=headers(client),
            json={"specification": specification(provider), "verify_target": opt_in},
        )
    assert response.status_code == 200
    assert response.json()["status"] == ("target_confirmed" if opt_in else "not_checked")
    assert len(calls) == int(opt_in)
    if calls:
        assert calls[0]["timeout"] == 30
    assert "private-" not in response.text
    assert response.json()["approval_granted"] is False


@pytest.mark.parametrize("consent", ["true", 1, None, {}])
def test_route_rejects_nonboolean_consent_without_cloud_execution(consent, monkeypatch):
    def forbidden(*args, **kwargs):
        raise AssertionError("Invalid consent must not execute a tool.")

    monkeypatch.setattr("terraforma.web.target_preflight", forbidden)
    with TestClient(create_app(), base_url="http://127.0.0.1") as client:
        response = client.post(
            "/api/projects/preflight",
            headers=headers(client),
            json={"specification": specification(), "verify_target": consent},
        )
    assert response.status_code == 422


def test_route_rejects_cross_origin_missing_token_and_oversized_body(monkeypatch):
    def forbidden(*args, **kwargs):
        raise AssertionError("Unauthorized or oversized input must not execute a tool.")

    monkeypatch.setattr("terraforma.web.target_preflight", forbidden)
    with TestClient(create_app(), base_url="http://127.0.0.1") as client:
        payload = {"specification": specification(), "verify_target": True}
        assert client.post("/api/projects/preflight", json=payload).status_code == 403
        request_headers = headers(client)
        assert (
            client.post(
                "/api/projects/preflight",
                json=payload,
                headers={**request_headers, "Origin": "https://example.invalid"},
            ).status_code
            == 403
        )
        assert (
            client.post(
                "/api/projects/preflight", headers=request_headers, content=b" " * (65536 + 1)
            ).status_code
            == 413
        )
        response = client.post(
            "/api/projects/preflight",
            headers=request_headers,
            json={**payload, "private-value": "unsupported"},
        )
        assert response.status_code == 422
        assert "private-value" not in response.text


@pytest.mark.parametrize("first_path", ["/api/projects/preflight", "/api/validate"])
def test_preflight_and_validation_share_one_tool_slot_without_blocking_reads(
    first_path, monkeypatch
):
    async def execute():
        started = asyncio.Event()
        release = threading.Event()
        loop = asyncio.get_running_loop()

        def blocked(*args, **kwargs):
            loop.call_soon_threadsafe(started.set)
            assert release.wait(timeout=5)
            return {"status": "target_confirmed", "is_valid": True, "errors": [], "logs": "ok"}

        monkeypatch.setattr("terraforma.web.target_preflight", blocked)
        monkeypatch.setattr("terraforma.web.ValidationSandbox.validate", blocked)
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=create_app()), base_url="http://127.0.0.1"
        ) as client:
            token = (await client.get("/api/session")).json()["token"]
            request_headers = {"X-TerraForma-Token": token}
            payloads = {
                "/api/projects/preflight": {
                    "specification": specification(),
                    "verify_target": True,
                },
                "/api/validate": {"config": specification(), "explain_with_ai": False},
            }
            first = asyncio.create_task(
                client.post(first_path, headers=request_headers, json=payloads[first_path])
            )
            try:
                await asyncio.wait_for(started.wait(), timeout=5)
                assert (await client.get("/api/session")).status_code == 200
                assert (
                    await client.post(
                        "/api/projects/compile", headers=request_headers, json=specification()
                    )
                ).status_code == 200
                for path, payload in payloads.items():
                    assert (
                        await client.post(path, headers=request_headers, json=payload)
                    ).status_code == 409
            finally:
                release.set()
            assert (await first).status_code == 200

    asyncio.run(execute())
