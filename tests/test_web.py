import asyncio
import io
import threading
import zipfile

import httpx
import pytest
from fastapi.testclient import TestClient

from terraforma.web import create_app

CONFIG = {
    "provider": "aws",
    "project_name": "example",
    "architecture_type": "static_site",
    "is_public": False,
    "enable_encryption": True,
}


@pytest.fixture
def client():
    with TestClient(create_app(), base_url="http://127.0.0.1") as client:
        yield client


def headers(client):
    return {"X-TerraForma-Token": client.get("/api/session").json()["token"]}


def test_local_ui_and_assets(client):
    result = client.get("/")
    assert result.status_code == 200
    assert "TerraForma-IaC" in result.text
    assert "frame-ancestors 'none'" in result.headers["content-security-policy"]
    for name in ("app.js", "styles.css", "theme.css"):
        assert client.get(f"/static/{name}").status_code == 200


def test_session_reports_presence_without_secrets(client, monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "private-test-key")
    monkeypatch.setattr("terraforma.web.shutil.which", lambda name: None)
    response = client.get("/api/session")
    assert response.json()["ai_available"] is True
    assert response.json()["tools"] == {"terraform": False, "tflint": False}
    assert "private-test-key" not in response.text


def test_mutation_requires_session_token(client):
    assert client.post("/api/generate", json=CONFIG).status_code == 403
    assert (
        client.post(
            "/api/generate", json=CONFIG, headers={"X-TerraForma-Token": "wrong"}
        ).status_code
        == 403
    )


def test_cross_origin_and_untrusted_host_are_rejected(client):
    request_headers = {**headers(client), "Origin": "https://external.example"}
    assert client.post("/api/generate", json=CONFIG, headers=request_headers).status_code == 403
    assert client.get("/api/session", headers={"Host": "external.example"}).status_code == 400
    assert (
        client.post(
            "/api/generate", json=CONFIG, headers={**headers(client), "Origin": "http://["}
        ).status_code
        == 403
    )


def test_same_origin_can_generate(client):
    result = client.post(
        "/api/generate", json=CONFIG, headers={**headers(client), "Origin": "http://127.0.0.1"}
    )
    assert result.status_code == 200
    assert set(result.json()["files"]) == {"main.tf", "variables.tf", "outputs.tf"}


def test_required_inputs_are_explained(client):
    result = client.post(
        "/api/generate",
        json={**CONFIG, "provider": "azure", "architecture_type": "secure_database"},
        headers=headers(client),
    )
    assert result.status_code == 200
    inputs = {item["name"]: item for item in result.json()["required_inputs"]}
    assert inputs["database_password"]["sensitive"]
    assert "subscription_id" in inputs
    assert len(result.json()["guide"]["route"]) == 3
    assert any("PostgreSQL" in item["name"] for item in result.json()["guide"]["components"])


def test_download_contains_expected_files_only(client):
    response = client.post("/api/download", json=CONFIG, headers=headers(client))
    assert response.status_code == 200
    assert 'filename="example.zip"' in response.headers["content-disposition"]
    with zipfile.ZipFile(io.BytesIO(response.content)) as archive:
        assert set(archive.namelist()) == {"main.tf", "variables.tf", "outputs.tf", "README.md"}
        assert "terraform plan" in archive.read("README.md").decode()


@pytest.mark.parametrize(
    "values",
    [
        {"project_name": "../escape"},
        {"provider": "unknown"},
        {"source_code": "arbitrary HCL"},
        {"architecture_type": "unsupported"},
    ],
)
def test_invalid_state_cannot_execute_or_generate(client, values):
    assert (
        client.post("/api/generate", json={**CONFIG, **values}, headers=headers(client)).status_code
        == 422
    )


def test_validation_uses_all_generated_files_and_returns_readable_errors(client, monkeypatch):
    captured = []

    def validate(self):
        captured.append(self.generated_files)
        return {
            "is_valid": False,
            "logs": "log",
            "errors": [{"tool": "tflint", "raw_output": "missing tool"}],
        }

    monkeypatch.setattr("terraforma.web.ValidationSandbox.validate", validate)
    response = client.post("/api/validate", json={"config": CONFIG}, headers=headers(client))
    assert response.status_code == 200
    assert set(captured[0]) == {"main.tf", "variables.tf", "outputs.tf"}
    assert not response.json()["is_valid"]
    assert response.json()["errors"][0]["message"] == "missing tool"
    assert response.json()["suggestion"] is None


def test_ai_only_runs_when_requested(client, monkeypatch):
    monkeypatch.setattr(
        "terraforma.web.ValidationSandbox.validate",
        lambda self: {"is_valid": False, "logs": "raw log", "errors": []},
    )
    calls = []

    class Engine:
        async def diagnose(self, logs):
            calls.append(logs)
            return {"friendly_explanation": "Explanation", "recommended_fix": "Fix"}

    monkeypatch.setattr("terraforma.web.AIDiagnosticsEngine", Engine)
    client.post("/api/validate", json={"config": CONFIG}, headers=headers(client))
    assert not calls
    response = client.post(
        "/api/validate", json={"config": CONFIG, "explain_with_ai": True}, headers=headers(client)
    )
    assert calls == ["raw log"]
    assert response.json()["suggestion"]["recommended_fix"] == "Fix"


def test_generated_files_cannot_escape_sandbox():
    from terraforma.sandbox import ValidationSandbox

    sandbox = ValidationSandbox(
        generated_files={"main.tf": "terraform {}", "../escape.tf": "unsafe"}
    )
    with pytest.raises(ValueError, match="filenames"):
        sandbox.create_environment()
    assert sandbox.temp_dir is None


def test_validation_does_not_block_session_checks_and_rejects_overlap(monkeypatch):
    async def execute():
        started = asyncio.Event()
        release = threading.Event()
        loop = asyncio.get_running_loop()

        def validate(self):
            loop.call_soon_threadsafe(started.set)
            assert release.wait(timeout=5)
            return {"is_valid": True, "logs": "ok", "errors": []}

        monkeypatch.setattr("terraforma.web.ValidationSandbox.validate", validate)
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=create_app()), base_url="http://127.0.0.1"
        ) as client:
            token = (await client.get("/api/session")).json()["token"]
            request_headers = {"X-TerraForma-Token": token}
            first = asyncio.create_task(
                client.post("/api/validate", json={"config": CONFIG}, headers=request_headers)
            )
            try:
                await asyncio.wait_for(started.wait(), timeout=5)
                assert (await client.get("/api/session")).status_code == 200
                second = await client.post(
                    "/api/validate", json={"config": CONFIG}, headers=request_headers
                )
                assert second.status_code == 409
            finally:
                release.set()
            assert (await first).json()["is_valid"]

    asyncio.run(execute())
