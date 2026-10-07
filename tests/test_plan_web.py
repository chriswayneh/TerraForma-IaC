import asyncio
import hashlib
import json
import threading

import httpx
import pytest
from fastapi.testclient import TestClient

from terraforma.web import create_app


def plan_bytes():
    return json.dumps(
        {
            "format_version": "1.2",
            "configuration": {},
            "planned_values": {},
            "complete": True,
            "applyable": True,
            "errored": False,
            "resource_changes": [
                {
                    "address": 'aws_security_group.example["private-secret-marker"]',
                    "type": "aws_security_group",
                    "mode": "managed",
                    "change": {
                        "actions": ["create"],
                        "after_unknown": {},
                        "after": {
                            "description": "private-secret-marker",
                            "ingress": [
                                {
                                    "protocol": "tcp",
                                    "from_port": 22,
                                    "to_port": 22,
                                    "cidr_blocks": ["0.0.0.0/0"],
                                    "ipv6_cidr_blocks": [],
                                }
                            ],
                        },
                    },
                }
            ],
        }
    ).encode()


def test_browser_plan_review_omits_raw_values_and_never_grants_approval(monkeypatch):
    def forbidden(*args, **kwargs):
        raise AssertionError("Plan review cannot execute native tools or use AI")

    monkeypatch.setattr("terraforma.web.ValidationSandbox.validate", forbidden)
    monkeypatch.setattr("terraforma.web.AIDiagnosticsEngine", forbidden)
    with TestClient(create_app(), base_url="http://127.0.0.1") as client:
        token = client.get("/api/session").json()["token"]
        raw = plan_bytes()
        response = client.post(
            "/api/plans/review", content=raw, headers={"X-TerraForma-Token": token}
        )
        assert response.status_code == 200
        report = response.json()
        assert report["status"] == "blocked"
        assert report["approval_granted"] is False
        assert report["artifact_sha256"] == hashlib.sha256(raw).hexdigest()
        assert any(item["code"] == "public_admin_access" for item in report["findings"])
        assert "private-secret-marker" not in response.text


@pytest.mark.parametrize(
    "raw",
    [
        b'{"private-secret-marker":',
        b'{"format_version":"1.2","format_version":"1.2"}',
        b'{"format_version":NaN}',
        b'{"version":4,"values":{}}',
    ],
)
def test_browser_rejects_invalid_or_wrong_plan_formats_without_values(raw):
    with TestClient(create_app(), base_url="http://127.0.0.1") as client:
        token = client.get("/api/session").json()["token"]
        response = client.post(
            "/api/plans/review", content=raw, headers={"X-TerraForma-Token": token}
        )
        assert response.status_code == 422
        assert "private-secret-marker" not in response.text


def test_plan_route_has_bounded_exception_without_expanding_other_routes():
    with TestClient(create_app(), base_url="http://127.0.0.1") as client:
        assert client.post("/api/plans/review", content=plan_bytes()).status_code == 403
        headers = {"X-TerraForma-Token": client.get("/api/session").json()["token"]}
        assert (
            client.post(
                "/api/plans/review", content=plan_bytes() + b" " * 65536, headers=headers
            ).status_code
            == 200
        )
        assert (
            client.post(
                "/api/projects/import", content=plan_bytes() + b" " * 65536, headers=headers
            ).status_code
            == 413
        )
        assert (
            client.post(
                "/api/plans/review", content=b" " * (8 * 1024 * 1024 + 1), headers=headers
            ).status_code
            == 413
        )


def test_plan_review_runs_off_event_loop_and_rejects_overlap(monkeypatch):
    async def execute():
        started = asyncio.Event()
        release = threading.Event()
        loop = asyncio.get_running_loop()

        def review(raw):
            loop.call_soon_threadsafe(started.set)
            assert release.wait(timeout=5)
            return {"status": "manual_review_required", "approval_granted": False}

        monkeypatch.setattr("terraforma.web.review_bytes", review)
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=create_app()), base_url="http://127.0.0.1"
        ) as client:
            headers = {"X-TerraForma-Token": (await client.get("/api/session")).json()["token"]}
            first = asyncio.create_task(
                client.post("/api/plans/review", content=plan_bytes(), headers=headers)
            )
            try:
                await asyncio.wait_for(started.wait(), timeout=5)
                assert (await client.get("/api/session")).status_code == 200
                assert (
                    await client.post("/api/plans/review", content=plan_bytes(), headers=headers)
                ).status_code == 409
            finally:
                release.set()
            assert (await first).json()["approval_granted"] is False

    asyncio.run(execute())
