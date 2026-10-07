import json

import pytest
from click.testing import CliRunner
from fastapi.testclient import TestClient

from terraforma.cli import main
from terraforma.web import create_app


def specification(inputs):
    return {
        "recipe": {
            "provider": "aws",
            "project_name": "error-test",
            "architecture_type": "secure_database",
        },
        "inputs": {"aws_account_id": "123456789012", **inputs},
    }


@pytest.mark.parametrize(
    "route",
    [
        "/api/generate",
        "/api/download",
        "/api/projects/compile",
        "/api/projects/import",
        "/api/validate",
    ],
)
def test_field_errors_help_without_disclosing_submitted_values(route, monkeypatch):
    def forbidden(*args, **kwargs):
        raise AssertionError("Invalid inputs must not start native validation")

    monkeypatch.setattr("terraforma.web.ValidationSandbox", forbidden)
    payload = specification({"allowed_cidr": "private-client-marker"})
    with TestClient(create_app(), base_url="http://127.0.0.1") as client:
        headers = {"X-TerraForma-Token": client.get("/api/session").json()["token"]}
        if route == "/api/projects/import":
            response = client.post(route, headers=headers, content=json.dumps(payload))
        else:
            response = client.post(
                route,
                headers=headers,
                json={"config": payload} if route == "/api/validate" else payload,
            )
        assert response.status_code == 422
        assert response.json()["field"] == "allowed_cidr"
        assert "RFC1918" in response.json()["detail"]
        assert "private-client-marker" not in response.text


@pytest.mark.parametrize(
    "inputs",
    [
        {"private-key-name-marker": "private-value-marker"},
        {"database_password": "private-value-marker"},
    ],
)
def test_unknown_or_secret_field_names_are_not_reflected(inputs):
    with TestClient(create_app(), base_url="http://127.0.0.1") as client:
        headers = {"X-TerraForma-Token": client.get("/api/session").json()["token"]}
        response = client.post("/api/generate", headers=headers, json=specification(inputs))
        assert response.status_code == 422
        assert "field" not in response.json()
        assert "private-" not in response.text


def test_missing_known_input_identifies_required_field():
    payload = specification({})
    payload["inputs"].clear()
    with TestClient(create_app(), base_url="http://127.0.0.1") as client:
        headers = {"X-TerraForma-Token": client.get("/api/session").json()["token"]}
        response = client.post("/api/generate", headers=headers, json=payload)
        assert response.status_code == 422
        assert response.json()["field"] == "aws_account_id"
        assert "missing" in response.json()["detail"]


def test_cli_reports_safe_field_feedback_and_creates_no_output(tmp_path):
    path = tmp_path / "input.json"
    path.write_text(json.dumps(specification({"allowed_cidr": "private-client-marker"})))
    destination = tmp_path / "output"
    result = CliRunner().invoke(main, ["generate", "--spec", str(path), "--dir", str(destination)])
    assert result.exit_code == 1
    assert "allowed_cidr" in result.output and "RFC1918" in result.output
    assert "private-client-marker" not in result.output
    assert not destination.exists()
