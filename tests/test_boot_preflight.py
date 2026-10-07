import copy
import json

import pytest
from click.testing import CliRunner
from fastapi.testclient import TestClient

from terraforma.cli import main
from terraforma.preflight import target_preflight
from terraforma.web import create_app
from tests.test_machine_preflight import MACHINES, commands, spec


@pytest.mark.parametrize(
    "extra,status,compatible",
    [
        ([], "boot_features_unknown", None),
        ([{"name": "HyperVGenerations", "value": "V1,V2"}], "metadata_confirmed", True),
        ([{"name": "HyperVGenerations", "value": "V2"}], "metadata_confirmed", True),
        ([{"name": "HyperVGenerations", "value": "V1"}], "boot_features_incompatible", False),
        ([{"name": "TrustedLaunchDisabled", "value": "True"}], "boot_features_incompatible", False),
        ([{"name": "TrustedLaunchDisabled", "value": "False"}], "boot_features_unknown", None),
        (
            [
                {"name": "hypervgenerations", "value": "V1, V2"},
                {"name": "trustedlaunchdisabled", "value": "false"},
            ],
            "metadata_confirmed",
            True,
        ),
    ],
)
@pytest.mark.parametrize("secure_boot", [False, True])
def test_azure_vm_reports_gen2_and_trusted_launch_support(
    extra, status, compatible, secure_boot, monkeypatch
):
    metadata = copy.deepcopy(MACHINES["azure"])
    metadata[0]["capabilities"].extend(extra)
    calls = commands(monkeypatch, "azure", metadata)
    specification = spec("azure", "virtual_machine")
    specification.inputs["ssh_public_key"] = (
        "ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAIAEBAQEBAQEBAQEBAQEBAQEBAQEBAQEBAQEBAQEBAQEB"
    )
    specification.inputs["enable_secure_boot"] = secure_boot
    report = target_preflight(specification, verify_target=True, verify_machine=True)
    assert report["machine_check"]["status"] == status
    assert report["machine_check"]["boot_features_compatible"] is compatible
    assert len(calls) == 2
    assert report["deployment_readiness_verified"] is report["approval_granted"] is False


@pytest.mark.parametrize(
    "extra",
    [
        [{"name": "HyperVGenerations", "value": "private-invalid-value"}],
        [{"name": "HyperVGenerations", "value": []}],
        [
            {"name": "HyperVGenerations", "value": "V2"},
            {"name": "hypervgenerations", "value": "V1"},
        ],
        [{"name": "TrustedLaunchDisabled", "value": True}],
        [{"name": "TrustedLaunchDisabled", "value": "private-invalid-value"}],
    ],
)
def test_malformed_boot_metadata_never_confirms_compatibility(extra, monkeypatch):
    metadata = copy.deepcopy(MACHINES["azure"])
    metadata[0]["capabilities"].extend(extra)
    commands(monkeypatch, "azure", metadata)
    specification = spec("azure", "virtual_machine")
    specification.inputs["ssh_public_key"] = (
        "ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAIAEBAQEBAQEBAQEBAQEBAQEBAQEBAQEBAQEBAQEBAQEB"
    )
    report = target_preflight(specification, verify_target=True, verify_machine=True)
    assert report["machine_check"]["status"] == "invalid_response"
    assert "private-invalid-value" not in json.dumps(report)


def test_unsupported_boot_size_is_reported_through_api_and_cli(tmp_path, monkeypatch):
    metadata = copy.deepcopy(MACHINES["azure"])
    metadata[0]["capabilities"].append({"name": "HyperVGenerations", "value": "V1"})
    specification = spec("azure", "virtual_machine")
    specification.inputs["ssh_public_key"] = (
        "ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAIAEBAQEBAQEBAQEBAQEBAQEBAQEBAQEBAQEBAQEBAQEB"
    )
    commands(monkeypatch, "azure", metadata)
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
        assert response.json()["machine_check"]["status"] == "boot_features_incompatible"
    commands(monkeypatch, "azure", metadata)
    path = tmp_path / "project.json"
    path.write_text(specification.model_dump_json(), encoding="utf-8")
    result = CliRunner().invoke(
        main,
        ["preflight", "--spec", str(path), "--verify-target", "--verify-machine", "--json-output"],
    )
    assert result.exit_code == 1, result.output
    assert json.loads(result.output)["machine_check"]["status"] == "boot_features_incompatible"
