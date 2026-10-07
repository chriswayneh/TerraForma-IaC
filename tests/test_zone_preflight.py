import copy
import json

import pytest
from click.testing import CliRunner

from terraforma.cli import main
from terraforma.preflight import target_preflight
from tests.test_machine_preflight import MACHINES, commands, spec
from tests.test_virtual_machine import KEY


def zone_specification(windows=False, zone="2"):
    result = spec("azure", "windows_virtual_machine" if windows else "virtual_machine")
    result.inputs["availability_zone"] = zone
    if not windows:
        result.inputs["ssh_public_key"] = KEY
    return result


def zone_machine(windows=False):
    result = copy.deepcopy(MACHINES["azure"])
    result[0]["name"] = "Standard_D2s_v5" if windows else "Standard_B1s"
    result[0]["capabilities"].append({"name": "HyperVGenerations", "value": "V2"})
    return result


@pytest.mark.parametrize("windows", [False, True])
@pytest.mark.parametrize(
    "information,status,compatible",
    [
        ([{"location": "eastus", "zones": ["1", "2", "3"]}], "metadata_confirmed", True),
        ([{"location": "EASTUS", "zones": ["2"]}], "metadata_confirmed", True),
        ([{"location": "eastus", "zones": ["1"]}], "zone_incompatible", False),
        ([{"location": "eastus", "zones": []}], "zone_incompatible", False),
        ([{"location": "westus", "zones": ["2"]}], "zone_unknown", None),
        ([{"location": "eastus"}], "zone_unknown", None),
        ([], "zone_unknown", None),
        (None, "zone_unknown", None),
    ],
)
def test_zone_results_use_existing_read_without_granting_approval(
    windows, information, status, compatible, monkeypatch
):
    machine = zone_machine(windows)
    machine[0]["locationInfo"] = information
    calls = commands(monkeypatch, "azure", machine=machine)
    report = target_preflight(zone_specification(windows), verify_target=True, verify_machine=True)
    assert report["machine_check"]["status"] == status
    assert report["machine_check"]["availability_zone_compatible"] is compatible
    assert len(calls) == 2
    assert report["approval_granted"] is report["deployment_readiness_verified"] is False
    assert "private-marker" not in json.dumps(report)
    assert "locationInfo" not in json.dumps(report)


@pytest.mark.parametrize(
    "information",
    [
        "private-marker",
        [{}],
        [{"location": True, "zones": ["2"]}],
        [{"location": "eastus", "zones": "2"}],
        [{"location": "eastus", "zones": [2]}],
        [{"location": "eastus", "zones": ["2", "2"]}],
        [{"location": "eastus", "zones": [["2"]]}],
        [{"location": "eastus", "zones": ["2"]}, {"location": "EASTUS", "zones": ["2"]}],
    ],
)
def test_malformed_zone_metadata_fails_closed_and_omits_raw_values(information, monkeypatch):
    machine = zone_machine()
    machine[0]["locationInfo"] = information
    commands(monkeypatch, "azure", machine=machine)
    report = target_preflight(zone_specification(), verify_target=True, verify_machine=True)
    assert report["machine_check"]["status"] == "invalid_response"
    assert "private-marker" not in json.dumps(report)


def test_regional_placement_does_not_require_zone_metadata(monkeypatch):
    commands(monkeypatch, "azure", machine=zone_machine())
    report = target_preflight(
        zone_specification(zone="regional"), verify_target=True, verify_machine=True
    )
    assert report["machine_check"]["status"] == "metadata_confirmed"
    assert "availability_zone_compatible" not in report["machine_check"]


def test_reported_zone_does_not_override_existing_restrictions(monkeypatch):
    machine = zone_machine()
    machine[0]["locationInfo"] = [{"location": "eastus", "zones": ["2"]}]
    machine[0]["restrictions"] = [{"type": "Zone"}]
    commands(monkeypatch, "azure", machine=machine)
    report = target_preflight(zone_specification(), verify_target=True, verify_machine=True)
    assert report["machine_check"]["status"] == "restricted"
    assert report["machine_check"]["availability_zone_compatible"] is True
    assert report["approval_granted"] is False


@pytest.mark.parametrize("zones,exit_code", [(["2"], 0), (["1"], 1), (None, 1)])
def test_cli_zone_unknown_and_incompatible_checks_return_failure(
    tmp_path, monkeypatch, zones, exit_code
):
    machine = zone_machine()
    machine[0]["locationInfo"] = [{"location": "eastus", "zones": zones}]
    commands(monkeypatch, "azure", machine=machine)
    path = tmp_path / "project.json"
    path.write_text(zone_specification().model_dump_json())
    result = CliRunner().invoke(
        main,
        ["preflight", "--spec", str(path), "--verify-target", "--verify-machine", "--json-output"],
    )
    assert result.exit_code == exit_code, result.output
    assert json.loads(result.output)["approval_granted"] is False
