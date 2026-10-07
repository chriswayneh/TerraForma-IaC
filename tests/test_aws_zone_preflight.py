import json

import pytest
from click.testing import CliRunner
from fastapi.testclient import TestClient

from terraforma.cli import main
from terraforma.preflight import target_preflight
from terraforma.process import CommandResult
from terraforma.web import create_app
from tests.test_aws_placement import specification

OFFERING = {
    "InstanceType": "t3.micro",
    "LocationType": "availability-zone",
    "Location": "us-east-1b",
}


def mock_reads(
    monkeypatch, offering, *, architecture="x86_64", account="123456789012", machine=None
):
    responses = [
        {"Account": account},
        {
            "InstanceTypes": [
                {
                    "InstanceType": "t3.micro",
                    "ProcessorInfo": {"SupportedArchitectures": [architecture]},
                    "EbsInfo": {"EncryptionSupport": "supported"},
                }
            ]
        },
        offering,
    ]
    if machine is not None:
        responses[1] = machine
    calls = []

    def run(arguments, **kwargs):
        data = responses[len(calls)]
        calls.append((arguments, kwargs))
        if isinstance(data, Exception):
            raise data
        if isinstance(data, CommandResult):
            return data
        return CommandResult(0, json.dumps(data).encode(), b"private-marker")

    monkeypatch.setattr("terraforma.preflight.shutil.which", lambda name: "fake-cloud-cli")
    monkeypatch.setattr("terraforma.preflight.run_bounded", run)
    return calls


@pytest.mark.parametrize("windows", [False, True])
@pytest.mark.parametrize(
    "payload,status,offered",
    [
        ({"InstanceTypeOfferings": [OFFERING]}, "metadata_confirmed", True),
        (
            {"InstanceTypeOfferings": [OFFERING], "NextToken": "private-token"},
            "metadata_confirmed",
            True,
        ),
        ({"InstanceTypeOfferings": []}, "zone_not_offered", False),
        ({"InstanceTypeOfferings": [], "NextToken": None}, "zone_not_offered", False),
        (
            {"InstanceTypeOfferings": [], "NextToken": "private-token"},
            "zone_offering_unknown",
            None,
        ),
        ({}, "invalid_response", None),
        ({"InstanceTypeOfferings": None}, "invalid_response", None),
        ({"InstanceTypeOfferings": [OFFERING, OFFERING]}, "invalid_response", None),
        (
            {"InstanceTypeOfferings": [{**OFFERING, "Location": "private-marker"}]},
            "invalid_response",
            None,
        ),
        (
            {"InstanceTypeOfferings": [{**OFFERING, "InstanceType": "private-marker"}]},
            "invalid_response",
            None,
        ),
        (
            {"InstanceTypeOfferings": [{**OFFERING, "LocationType": "region"}]},
            "invalid_response",
            None,
        ),
        ({"InstanceTypeOfferings": [None]}, "invalid_response", None),
        ({"InstanceTypeOfferings": [], "NextToken": ""}, "invalid_response", None),
        ({"InstanceTypeOfferings": [], "NextToken": 1}, "invalid_response", None),
        ([], "invalid_response", None),
        (OSError("private-marker"), "zone_offering_failed", None),
        (CommandResult(1, b"private-marker", b"private-marker"), "zone_offering_failed", None),
        (CommandResult(0, b"private-marker", b"", "timeout"), "zone_offering_failed", None),
        (CommandResult(0, b"private-marker", b"", "output_limit"), "zone_offering_failed", None),
        (CommandResult(0, b"not-json-private-marker", b""), "invalid_response", None),
    ],
)
def test_offering_results_are_bounded_redacted_and_not_approval(
    windows, payload, status, offered, monkeypatch
):
    calls = mock_reads(monkeypatch, payload)
    project = specification(windows, availability_zone="us-east-1b", instance_type="t3.micro")
    report = target_preflight(project, verify_target=True, verify_machine=True, timeout=12)
    assert report["machine_check"] == {
        "status": status,
        "architecture_compatible": True,
        "availability_zone_offered": offered,
        "ebs_encryption_compatible": True,
    }
    assert report["approval_granted"] is False
    assert report["deployment_readiness_verified"] is False
    assert "private-" not in json.dumps(report)
    assert len(calls) == 3
    arguments, options = calls[2]
    assert arguments == [
        "fake-cloud-cli",
        "ec2",
        "describe-instance-type-offerings",
        "--location-type",
        "availability-zone",
        "--filters",
        "Name=instance-type,Values=t3.micro",
        "Name=location,Values=us-east-1b",
        "--region",
        "us-east-1",
        "--output",
        "json",
        "--no-cli-pager",
        "--no-paginate",
    ]
    assert options["timeout"] == 12 and options["stream_limit"] == 128 * 1024
    assert options["env"] == calls[1][1]["env"]


@pytest.mark.parametrize(
    "scenario,reads,status",
    [
        ("offline", 0, "not_checked"),
        ("target_only", 1, "not_checked"),
        ("mismatch", 1, "not_checked"),
        ("automatic", 2, "metadata_confirmed"),
        ("incompatible", 2, "architecture_incompatible"),
    ],
)
def test_offering_read_requires_consent_target_placement_and_compatible_metadata(
    scenario, reads, status, monkeypatch
):
    calls = mock_reads(
        monkeypatch,
        {"InstanceTypeOfferings": [OFFERING]},
        architecture="arm64" if scenario == "incompatible" else "x86_64",
        account="999999999999" if scenario == "mismatch" else "123456789012",
    )
    project = specification(
        False, availability_zone="" if scenario == "automatic" else "us-east-1b"
    )
    report = target_preflight(
        project,
        verify_target=scenario != "offline",
        verify_machine=scenario not in {"offline", "target_only"},
    )
    assert len(calls) == reads
    assert report["machine_check"]["status"] == status


@pytest.mark.parametrize(
    "machine,status",
    [
        ({"InstanceTypes": [{"InstanceType": "t3.micro"}]}, "architecture_unknown"),
        ({"InstanceTypes": None}, "invalid_response"),
        (CommandResult(1, b"private-marker", b""), "failed"),
    ],
)
def test_unresolved_machine_metadata_does_not_trigger_an_offering_read(
    machine, status, monkeypatch
):
    calls = mock_reads(monkeypatch, {"InstanceTypeOfferings": [OFFERING]}, machine=machine)
    report = target_preflight(
        specification(False, availability_zone="us-east-1b"),
        verify_target=True,
        verify_machine=True,
    )
    assert len(calls) == 2
    assert report["machine_check"]["status"] == status
    assert "availability_zone_offered" not in report["machine_check"]


@pytest.mark.parametrize("offered", [False, True])
def test_cli_and_api_preserve_offering_result_without_raw_logs(offered, monkeypatch, tmp_path):
    project = specification(False, availability_zone="us-east-1b")
    payload = {"InstanceTypeOfferings": [OFFERING] if offered else []}
    mock_reads(monkeypatch, payload)
    path = tmp_path / "project.json"
    path.write_text(json.dumps(project.model_dump()), encoding="utf-8")
    result = CliRunner().invoke(
        main,
        ["preflight", "--spec", str(path), "--verify-target", "--verify-machine", "--json-output"],
    )
    assert result.exit_code == (0 if offered else 1)
    cli_report = json.loads(result.output)
    mock_reads(monkeypatch, payload)
    with TestClient(create_app(), base_url="http://127.0.0.1") as client:
        token = client.get("/api/session").json()["token"]
        response = client.post(
            "/api/projects/preflight",
            headers={"X-TerraForma-Token": token},
            json={
                "specification": project.model_dump(),
                "verify_target": True,
                "verify_machine": True,
            },
        )
    assert response.status_code == 200
    assert response.json() == cli_report
    assert "private-marker" not in response.text
