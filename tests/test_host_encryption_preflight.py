import copy
import json

import pytest
from click.testing import CliRunner
from fastapi.testclient import TestClient

from terraforma.cli import main
from terraforma.preflight import target_preflight
from terraforma.web import create_app
from tests.test_machine_preflight import MACHINES, commands, spec
from tests.test_trusted_launch import KEY


def metadata(values):
    result = copy.deepcopy(MACHINES["azure"])
    result[0]["capabilities"] = [
        {"name": "CpuArchitectureType", "value": "x64"},
        {"name": "HyperVGenerations", "value": "V2"},
        *({"name": "EncryptionAtHostSupported", "value": value} for value in values),
    ]
    return result


def azure_spec(workload):
    result = spec("azure", workload)
    result.inputs["ssh_public_key"] = KEY
    return result


@pytest.mark.parametrize("workload", ["virtual_machine", "single_web_server", "load_balanced_tier"])
@pytest.mark.parametrize(
    "values,status,compatible",
    [
        (["True"], "metadata_confirmed", True),
        (["FALSE"], "encryption_features_incompatible", False),
        ([], "encryption_features_unknown", None),
    ],
)
def test_requested_host_encryption_requires_reported_support(
    monkeypatch, workload, values, status, compatible
):
    calls = commands(monkeypatch, "azure", metadata(values))
    report = target_preflight(azure_spec(workload), verify_target=True, verify_machine=True)
    assert report["machine_check"]["status"] == status
    assert report["machine_check"]["host_encryption_compatible"] is compatible
    assert len(calls) == 2
    assert report["approval_granted"] is report["deployment_readiness_verified"] is False


@pytest.mark.parametrize("values", [[True], [None], ["private-invalid-value"], ["True", "False"]])
def test_host_encryption_metadata_rejects_ambiguous_or_malformed_values(monkeypatch, values):
    commands(monkeypatch, "azure", metadata(values))
    report = target_preflight(
        azure_spec("virtual_machine"), verify_target=True, verify_machine=True
    )
    assert report["machine_check"]["status"] == "invalid_response"
    assert "private-invalid-value" not in str(report)


@pytest.mark.parametrize("workload", ["virtual_machine", "single_web_server", "load_balanced_tier"])
def test_host_encryption_not_requested_does_not_require_capability(monkeypatch, workload):
    commands(monkeypatch, "azure", metadata(["False"]))
    specification = azure_spec(workload)
    specification.recipe.enable_encryption = False
    report = target_preflight(specification, verify_target=True, verify_machine=True)
    assert report["machine_check"]["status"] == "metadata_confirmed"
    assert "host_encryption_compatible" not in report["machine_check"]


def test_unsupported_encryption_visible_despite_missing_boot_evidence(monkeypatch):
    data = metadata(["False"])
    data[0]["capabilities"] = [
        item for item in data[0]["capabilities"] if item["name"] != "HyperVGenerations"
    ]
    commands(monkeypatch, "azure", data)
    report = target_preflight(
        azure_spec("virtual_machine"), verify_target=True, verify_machine=True
    )
    assert report["machine_check"]["status"] == "encryption_features_incompatible"
    assert report["machine_check"]["boot_features_compatible"] is None


def test_host_encryption_failure_reaches_api_and_cli(monkeypatch, tmp_path):
    specification = azure_spec("virtual_machine")
    commands(monkeypatch, "azure", metadata(["False"]))
    with TestClient(create_app(), base_url="http://127.0.0.1") as client:
        headers = {"X-TerraForma-Token": client.get("/api/session").json()["token"]}
        response = client.post(
            "/api/projects/preflight",
            headers=headers,
            json={
                "specification": specification.model_dump(),
                "verify_target": True,
                "verify_machine": True,
            },
        )
        assert response.status_code == 200
        assert response.json()["machine_check"]["status"] == "encryption_features_incompatible"
    commands(monkeypatch, "azure", metadata(["False"]))
    path = tmp_path / "project.json"
    path.write_text(specification.model_dump_json(), encoding="utf-8")
    result = CliRunner().invoke(
        main,
        ["preflight", "--spec", str(path), "--verify-target", "--verify-machine", "--json-output"],
    )
    assert result.exit_code == 1
    assert (
        json.loads(result.output)["machine_check"]["status"] == "encryption_features_incompatible"
    )
