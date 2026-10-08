import hashlib
import json

import pytest
from fastapi.testclient import TestClient

from terraforma.backend import MAX_BACKEND_BYTES, backend_input_contract, review_backend
from terraforma.web import create_app
from tests.test_backend import intent


@pytest.fixture
def client():
    with TestClient(create_app(), base_url="http://127.0.0.1") as client:
        yield client


def headers(client):
    return {"X-TerraForma-Token": client.get("/api/session").json()["token"]}


@pytest.mark.parametrize("backend", ["s3", "azurerm", "gcs"])
def test_browser_contract_check_and_download_match_terminal(client, backend, monkeypatch):
    monkeypatch.setattr("subprocess.run", lambda *a, **k: pytest.fail("No tools or cloud CLIs."))
    auth = headers(client)
    contract = client.post("/api/backends/input-contract", headers=auth, json={"backend": backend})
    assert contract.status_code == 200
    assert contract.json()["inputs"] == backend_input_contract(backend)
    raw = json.dumps(intent(backend)).encode()
    checked = client.post("/api/backends/check", headers=auth, content=raw)
    assert checked.status_code == 200
    assert checked.json() == review_backend(raw)
    assert "private-" not in checked.text
    download = client.post("/api/backends/download", headers=auth, content=raw)
    assert download.status_code == 200
    assert download.json() == intent(backend)
    assert (
        download.headers["content-disposition"] == 'attachment; filename="terraforma.backend.json"'
    )
    assert download.headers["content-type"] == "application/json"
    assert download.headers["cache-control"] == "no-store"
    assert download.headers["x-content-type-options"] == "nosniff"
    imported = client.post("/api/backends/import", headers=auth, content=download.content)
    assert imported.status_code == 200
    assert imported.json()["intent"] == intent(backend)
    assert imported.json()["inputs"] == contract.json()["inputs"]
    assert imported.json()["backend_configured"] is False
    assert imported.json()["identity_verified"] is False
    assert imported.json()["approval_granted"] is False


@pytest.mark.parametrize("route", ["input-contract", "check", "download", "import"])
def test_backend_routes_require_session_and_reject_cross_origin(client, route):
    body = {"backend": "s3"} if route == "input-contract" else intent("s3")
    path = f"/api/backends/{route}"
    assert client.post(path, json=body).status_code == 403
    assert (
        client.post(
            path, json=body, headers={**headers(client), "Origin": "https://other.example"}
        ).status_code
        == 403
    )


@pytest.mark.parametrize("route", ["check", "download", "import"])
@pytest.mark.parametrize(
    "changes",
    [
        {"token": "private-token"},
        {"use_lockfile": False},
        {"key": "../private-key"},
        {"bucket": "<script>private-value</script>"},
        {"account_id": True},
        {"schema_version": 9},
    ],
)
def test_invalid_backend_input_is_rejected_without_values(client, route, changes):
    response = client.post(
        f"/api/backends/{route}", headers=headers(client), json={**intent("s3"), **changes}
    )
    assert response.status_code == 422
    assert "private-" not in response.text
    assert "<script>" not in response.text
    assert "content-disposition" not in response.headers


@pytest.mark.parametrize("route", ["check", "download", "import"])
def test_backend_bytes_are_limited_and_streamed_overflow_rejected(client, route):
    auth = headers(client)
    raw = json.dumps(intent("gcs")).encode()
    bounded = raw + b" " * (MAX_BACKEND_BYTES - len(raw))
    response = client.post(f"/api/backends/{route}", headers=auth, content=bounded)
    assert response.status_code == 200
    if route == "check":
        assert response.json()["artifact_sha256"] == hashlib.sha256(bounded).hexdigest()
    overflow = client.post(f"/api/backends/{route}", headers=auth, content=iter([bounded, b" "]))
    assert overflow.status_code == 413
    assert "16 KiB" in overflow.text


@pytest.mark.parametrize("route", ["check", "download", "import"])
def test_duplicate_backend_fields_are_rejected(client, route):
    raw = b'{"backend":"s3","backend":"gcs","token":"private-token"}'
    response = client.post(f"/api/backends/{route}", headers=headers(client), content=raw)
    assert response.status_code == 422
    assert "private-token" not in response.text


def test_unsupported_contract_is_redacted_and_ui_assets_are_served(client):
    response = client.post(
        "/api/backends/input-contract",
        headers=headers(client),
        json={"backend": "private-unsupported"},
    )
    assert response.status_code == 422
    assert "private-unsupported" not in response.text
    assert client.get("/static/backend.js").status_code == 200
    assert "State storage inputs" in client.get("/").text


@pytest.mark.parametrize(
    "data",
    [
        {"version": 4, "resources": [], "outputs": {"password": "private-secret"}},
        {"schema_version": 1, "recipe": {"project_name": "private-project"}},
        {"client_email": "private@example.com", "private_key": "private-key"},
    ],
)
def test_import_rejects_state_project_and_credential_files(client, data):
    response = client.post("/api/backends/import", headers=headers(client), json=data)
    assert response.status_code == 422
    assert "private" not in response.text


def test_import_normalizes_supported_references_and_returns_no_execution_claim(client):
    data = intent("azurerm")
    data["tenant_id"] = "AAAAAAAA-AAAA-4AAA-8AAA-AAAAAAAAAAAA"
    response = client.post("/api/backends/import", headers=headers(client), json=data)
    assert response.status_code == 200
    assert response.json()["intent"]["tenant_id"] == data["tenant_id"].lower()
    assert response.json()["approval_granted"] is False
