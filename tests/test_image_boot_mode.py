import copy
import json

import pytest
from click.testing import CliRunner
from fastapi.testclient import TestClient

from terraforma.cli import main
from terraforma.image_metadata import image_values
from terraforma.image_preflight import image_machine_boot_check
from terraforma.preflight import aws_boot_mode_metadata, target_preflight
from terraforma.process import CommandResult
from terraforma.web import create_app
from tests.test_custom_images import specification
from tests.test_image_preflight import image_records, mocks
from tests.test_machine_preflight import MACHINES
from tests.test_preflight_web import headers


def setup(monkeypatch, mode, supported, windows=False):
    spec = specification("aws", windows=windows)
    records = image_records(spec)
    if mode is not None:
        records[0]["Images"][0]["BootMode"] = mode
    calls = mocks(monkeypatch, spec, records)
    machine = copy.deepcopy(MACHINES["aws"])
    machine["InstanceTypes"][0]["InstanceType"] = image_values(spec)["instance_type"]
    if supported is not None:
        machine["InstanceTypes"][0]["SupportedBootModes"] = supported
    responses = [{"Account": "123456789012"}, machine]

    def run(arguments, **kwargs):
        calls.append((arguments, kwargs))
        return CommandResult(0, json.dumps(responses.pop(0)).encode(), b"private-marker")

    monkeypatch.setattr("terraforma.preflight.run_bounded", run)
    return spec, calls


@pytest.mark.parametrize("windows", [False, True])
@pytest.mark.parametrize(
    "mode,supported,status,fallback",
    [
        ("uefi", ["uefi"], "metadata_confirmed", False),
        ("uefi", ["legacy-bios"], "incompatible", False),
        ("legacy-bios", ["uefi"], "incompatible", False),
        ("legacy-bios", ["legacy-bios", "uefi"], "metadata_confirmed", False),
        ("uefi-preferred", ["legacy-bios"], "metadata_confirmed", True),
        ("uefi-preferred", ["uefi"], "metadata_confirmed", False),
        ("uefi-preferred", ["legacy-bios", "uefi"], "metadata_confirmed", False),
        (None, ["legacy-bios"], "metadata_confirmed", False),
        (None, ["uefi"], "incompatible", False),
        ("uefi", None, "metadata_unknown", False),
        ("legacy-bios", [], "metadata_unknown", False),
    ],
)
def test_aws_image_and_size_boot_modes_are_compared_without_extra_reads(
    windows, mode, supported, status, fallback, monkeypatch
):
    spec, calls = setup(monkeypatch, mode, supported, windows)
    report = target_preflight(spec, verify_target=True, verify_machine=True, verify_image=True)
    check = report["image_machine_check"]
    assert check["status"] == status
    assert check["legacy_bios_fallback"] is fallback
    assert len(calls) == 3
    assert report["approval_granted"] is False
    assert report["deployment_readiness_verified"] is False
    assert "private-marker" not in json.dumps(report)


@pytest.mark.parametrize("supported", ["uefi", ["uefi", "uefi"], ["private-marker"], [1], {}])
def test_malformed_machine_boot_metadata_is_never_accepted(supported, monkeypatch):
    spec, _ = setup(monkeypatch, "uefi", supported)
    report = target_preflight(spec, verify_target=True, verify_machine=True, verify_image=True)
    assert report["machine_check"]["status"] == "invalid_response"
    assert report["image_machine_check"]["status"] == "metadata_unknown"
    assert "private-marker" not in json.dumps(report)


@pytest.mark.parametrize("mode", ["private-marker", "", [], True])
def test_malformed_image_boot_metadata_is_never_accepted(mode, monkeypatch):
    spec, _ = setup(monkeypatch, mode, ["uefi"])
    report = target_preflight(spec, verify_target=True, verify_machine=True, verify_image=True)
    assert report["image_check"]["status"] == "invalid_response"
    assert report["image_machine_check"]["status"] == "metadata_unknown"
    assert "private-marker" not in json.dumps(report)


@pytest.mark.parametrize("machine,image", [(True, False), (False, True), (False, False)])
def test_cross_check_requires_both_metadata_consents(machine, image, monkeypatch):
    spec, calls = setup(monkeypatch, "uefi", ["legacy-bios"])
    report = target_preflight(spec, verify_target=True, verify_machine=machine, verify_image=image)
    assert report["image_machine_check"] == {"status": "not_checked"}
    assert len(calls) == 1 + int(machine) + int(image)
    if not image:
        assert "uefi_boot_supported" not in report["machine_check"]


def test_boot_check_unknowns_do_not_turn_into_compatible_defaults():
    assert image_machine_boot_check({}, {})["status"] == "metadata_unknown"
    assert aws_boot_mode_metadata({}) == {
        "legacy_bios_boot_supported": None,
        "uefi_boot_supported": None,
    }
    assert image_machine_boot_check({"uefi_boot_supported": "private-marker"}, {}) == {
        "status": "invalid_response"
    }


def test_cli_fails_known_boot_mismatch_and_api_reports_it_privately(tmp_path, monkeypatch):
    spec, calls = setup(monkeypatch, "uefi", ["legacy-bios"])
    path = tmp_path / "project.json"
    path.write_text(spec.model_dump_json(), encoding="utf-8")
    result = CliRunner().invoke(
        main,
        [
            "preflight",
            "--spec",
            str(path),
            "--verify-target",
            "--verify-machine",
            "--verify-image",
            "--json-output",
        ],
    )
    assert result.exit_code == 1
    assert json.loads(result.output)["image_machine_check"]["status"] == "incompatible"
    assert len(calls) == 3
    spec, calls = setup(monkeypatch, "uefi", ["legacy-bios"])
    with TestClient(create_app(), base_url="http://127.0.0.1") as client:
        response = client.post(
            "/api/projects/preflight",
            headers=headers(client),
            json={
                "specification": spec.model_dump(),
                "verify_target": True,
                "verify_machine": True,
                "verify_image": True,
            },
        )
    assert response.status_code == 200
    assert response.json()["image_machine_check"]["status"] == "incompatible"
    assert "private-marker" not in response.text
    assert len(calls) == 3
