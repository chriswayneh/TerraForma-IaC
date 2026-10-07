import copy
import io
import json
import zipfile

import pytest
from click.testing import CliRunner
from fastapi.testclient import TestClient

from terraforma.cli import main
from terraforma.generator import WizardConfig
from terraforma.preflight import target_preflight
from terraforma.project import compile_project, input_contract
from terraforma.web import create_app
from tests.test_machine_preflight import MACHINES, commands
from tests.test_trusted_launch import specification


@pytest.mark.parametrize("enabled", [False, True])
def test_accelerated_networking_round_trip(enabled):
    spec = specification()
    spec.inputs["enable_accelerated_networking"] = enabled
    compiled = compile_project(spec)
    assert (
        "accelerated_networking_enabled = var.enable_accelerated_networking"
        in compiled["files"]["main.tf"]
    )
    with TestClient(create_app(), base_url="http://127.0.0.1") as client:
        headers = {"X-TerraForma-Token": client.get("/api/session").json()["token"]}
        response = client.post("/api/download", headers=headers, json=spec.model_dump())
        assert response.status_code == 200
        with zipfile.ZipFile(io.BytesIO(response.content)) as archive:
            imported = client.post(
                "/api/projects/import",
                headers=headers,
                content=archive.read("terraforma.project.json"),
            )
            assert imported.status_code == 200
            assert (
                imported.json()["specification"]["inputs"]["enable_accelerated_networking"]
                is enabled
            )
            assert imported.json()["files"]["variables.tf"] == archive.read("variables.tf").decode()


def test_accelerated_networking_default_and_scope():
    question = next(
        item
        for item in input_contract(specification().recipe)
        if item["name"] == "enable_accelerated_networking"
    )
    assert question["default"] is False and question["kind"] == "boolean"
    assert "deallocating" in question["description"] and "guest-driver" in question["description"]
    for provider, workload in [
        ("aws", "virtual_machine"),
        ("gcp", "virtual_machine"),
        ("azure", "single_web_server"),
        ("azure", "load_balanced_tier"),
    ]:
        recipe = WizardConfig(
            provider=provider, project_name="scope-test", architecture_type=workload
        )
        assert not any(
            item["name"] == "enable_accelerated_networking" for item in input_contract(recipe)
        )


@pytest.mark.parametrize("value", ["true", "false", 0, 1, None])
def test_accelerated_networking_rejects_coercion(value):
    spec = specification()
    spec.inputs["enable_accelerated_networking"] = value
    with pytest.raises(ValueError):
        compile_project(spec)


@pytest.mark.parametrize(
    "value,status,compatible",
    [
        ("True", "metadata_confirmed", True),
        ("false", "network_features_incompatible", False),
        (None, "network_features_unknown", None),
    ],
)
def test_networking_metadata_check_uses_existing_opt_in_read(
    monkeypatch, value, status, compatible
):
    metadata = copy.deepcopy(MACHINES["azure"])
    metadata[0]["capabilities"].append({"name": "HyperVGenerations", "value": "V2"})
    if value is not None:
        metadata[0]["capabilities"].append({"name": "AcceleratedNetworkingEnabled", "value": value})
    calls = commands(monkeypatch, "azure", metadata)
    spec = specification()
    spec.inputs["enable_accelerated_networking"] = True
    report = target_preflight(spec, verify_target=True, verify_machine=True)
    assert report["machine_check"]["status"] == status
    assert report["machine_check"]["accelerated_networking_compatible"] is compatible
    assert len(calls) == 2
    assert report["approval_granted"] is report["deployment_readiness_verified"] is False


@pytest.mark.parametrize("values", [[True], ["private-invalid-value"], ["True", "False"]])
def test_malformed_networking_metadata_is_not_exposed(monkeypatch, values):
    metadata = copy.deepcopy(MACHINES["azure"])
    metadata[0]["capabilities"].append({"name": "HyperVGenerations", "value": "V2"})
    metadata[0]["capabilities"].extend(
        {"name": "AcceleratedNetworkingEnabled", "value": value} for value in values
    )
    commands(monkeypatch, "azure", metadata)
    spec = specification()
    spec.inputs["enable_accelerated_networking"] = True
    report = target_preflight(spec, verify_target=True, verify_machine=True)
    assert report["machine_check"]["status"] == "invalid_response"
    assert "private-invalid-value" not in str(report)


def test_unrequested_networking_metadata_does_not_change_status(monkeypatch):
    metadata = copy.deepcopy(MACHINES["azure"])
    metadata[0]["capabilities"].extend(
        [
            {"name": "HyperVGenerations", "value": "V2"},
            {"name": "AcceleratedNetworkingEnabled", "value": "False"},
        ]
    )
    commands(monkeypatch, "azure", metadata)
    report = target_preflight(specification(), verify_target=True, verify_machine=True)
    assert report["machine_check"]["status"] == "metadata_confirmed"
    assert "accelerated_networking_compatible" not in report["machine_check"]


def test_networking_incompatibility_reaches_api_and_cli(monkeypatch, tmp_path):
    metadata = copy.deepcopy(MACHINES["azure"])
    metadata[0]["capabilities"].extend(
        [
            {"name": "HyperVGenerations", "value": "V2"},
            {"name": "AcceleratedNetworkingEnabled", "value": "False"},
        ]
    )
    spec = specification()
    spec.inputs["enable_accelerated_networking"] = True
    commands(monkeypatch, "azure", metadata)
    with TestClient(create_app(), base_url="http://127.0.0.1") as client:
        headers = {"X-TerraForma-Token": client.get("/api/session").json()["token"]}
        response = client.post(
            "/api/projects/preflight",
            headers=headers,
            json={
                "specification": spec.model_dump(),
                "verify_target": True,
                "verify_machine": True,
            },
        )
        assert response.status_code == 200
        assert response.json()["machine_check"]["status"] == "network_features_incompatible"
    commands(monkeypatch, "azure", metadata)
    path = tmp_path / "project.json"
    path.write_text(spec.model_dump_json(), encoding="utf-8")
    result = CliRunner().invoke(
        main,
        ["preflight", "--spec", str(path), "--verify-target", "--verify-machine", "--json-output"],
    )
    assert result.exit_code == 1
    assert json.loads(result.output)["machine_check"]["status"] == "network_features_incompatible"
