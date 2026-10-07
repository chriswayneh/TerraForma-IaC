import copy
import json

import pytest
from click.testing import CliRunner
from fastapi.testclient import TestClient

from terraforma.cli import main
from terraforma.generator import WizardConfig
from terraforma.preflight import target_preflight
from terraforma.process import CommandResult
from terraforma.project import ProjectSpecification
from terraforma.web import create_app

TARGETS = {
    "aws": {"Account": "123456789012"},
    "azure": {"subscriptionId": "12345678-1234-1234-1234-123456789abc", "state": "Enabled"},
    "gcp": {"projectId": "example-project", "lifecycleState": "ACTIVE"},
}
MACHINES = {
    "aws": {
        "InstanceTypes": [
            {"InstanceType": "t3.micro", "ProcessorInfo": {"SupportedArchitectures": ["x86_64"]}}
        ]
    },
    "azure": [
        {
            "name": "Standard_B1s",
            "resourceType": "virtualMachines",
            "locations": ["eastus"],
            "capabilities": [
                {"name": "CpuArchitectureType", "value": "x64"},
                {"name": "EncryptionAtHostSupported", "value": "True"},
            ],
            "restrictions": [],
        }
    ],
    "gcp": {"name": "e2-micro", "zone": "us-central1-a", "architecture": "X86_64"},
}


def spec(provider="aws", workload="single_web_server"):
    inputs = {
        "aws": {"aws_account_id": "123456789012"},
        "azure": {"subscription_id": "12345678-1234-1234-1234-123456789abc"},
        "gcp": {"gcp_project_id": "example-project"},
    }[provider]
    if provider == "azure" and workload == "single_web_server":
        inputs["ssh_public_key"] = (
            "ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAIAEBAQEBAQEBAQEBAQEBAQEBAQEBAQEBAQEBAQEBAQEB"
        )
    return ProjectSpecification(
        recipe=WizardConfig(
            provider=provider, project_name="machine-test", architecture_type=workload
        ),
        inputs=inputs,
    )


def commands(monkeypatch, provider, machine=None, target=None):
    calls = []
    responses = [
        TARGETS[provider] if target is None else target,
        MACHINES[provider] if machine is None else machine,
    ]

    def run(arguments, **kwargs):
        calls.append((arguments, kwargs))
        data = responses[len(calls) - 1]
        return CommandResult(0, json.dumps(data).encode(), b"private-marker")

    monkeypatch.setattr("terraforma.preflight.shutil.which", lambda name: "fake-cloud-cli")
    monkeypatch.setattr("terraforma.preflight.run_bounded", run)
    return calls


@pytest.mark.parametrize("provider", TARGETS)
def test_machine_metadata_requires_opt_in_and_a_matching_target(provider, monkeypatch):
    calls = commands(monkeypatch, provider)
    offline = target_preflight(spec(provider))
    assert not calls and offline["machine_check"]["status"] == "not_checked"
    report = target_preflight(spec(provider), verify_target=True, verify_machine=True, timeout=12)
    assert report["machine_check"] == {
        "status": "metadata_confirmed",
        "architecture_compatible": True,
        **({"host_encryption_compatible": True} if provider == "azure" else {}),
    }
    assert len(calls) == 2
    args, options = calls[1]
    assert options["timeout"] == 12 and options["stream_limit"] == 128 * 1024
    if provider == "aws":
        assert args[1:3] == ["ec2", "describe-instance-types"]
        assert args[args.index("--region") + 1] == "us-east-1"
    elif provider == "azure":
        assert args[1:3] == ["vm", "list-skus"]
        assert args[args.index("--subscription") + 1] == TARGETS[provider]["subscriptionId"]
    else:
        assert args[1:4] == ["compute", "machine-types", "describe"]
        assert args[args.index("--project") + 1] == "example-project"
        assert args[args.index("--zone") + 1] == "us-central1-a"
    assert "private-marker" not in json.dumps(report)
    assert report["deployment_readiness_verified"] is report["approval_granted"] is False


@pytest.mark.parametrize("provider", TARGETS)
def test_omitting_machine_opt_in_runs_only_the_target_read(provider, monkeypatch):
    calls = commands(monkeypatch, provider)
    report = target_preflight(spec(provider), verify_target=True)
    assert len(calls) == 1 and report["machine_check"]["status"] == "not_checked"


def test_mismatched_target_never_runs_machine_read(monkeypatch):
    calls = commands(monkeypatch, "aws", target={"Account": "999999999999"})
    report = target_preflight(spec(), verify_target=True, verify_machine=True)
    assert len(calls) == 1 and report["status"] == "target_mismatch"
    assert report["machine_check"]["status"] == "not_checked"


@pytest.mark.parametrize("provider", TARGETS)
def test_noncompute_recipes_do_not_run_machine_read(provider, monkeypatch):
    calls = commands(monkeypatch, provider)
    report = target_preflight(
        spec(provider, "static_site"), verify_target=True, verify_machine=True
    )
    assert len(calls) == 1 and report["machine_check"]["status"] == "not_applicable"


@pytest.mark.parametrize("provider", TARGETS)
def test_arm_metadata_is_incompatible_with_current_x86_templates(provider, monkeypatch):
    data = copy.deepcopy(MACHINES[provider])
    if provider == "aws":
        data["InstanceTypes"][0]["ProcessorInfo"]["SupportedArchitectures"] = ["arm64"]
    elif provider == "azure":
        data[0]["capabilities"][0]["value"] = "Arm64"
    else:
        data["architecture"] = "ARM64"
    commands(monkeypatch, provider, machine=data)
    report = target_preflight(spec(provider), verify_target=True, verify_machine=True)
    assert report["machine_check"] == {
        "status": "architecture_incompatible",
        "architecture_compatible": False,
        **({"host_encryption_compatible": True} if provider == "azure" else {}),
    }


@pytest.mark.parametrize("provider", TARGETS)
def test_missing_architecture_is_not_silently_certified(provider, monkeypatch):
    data = copy.deepcopy(MACHINES[provider])
    if provider == "aws":
        del data["InstanceTypes"][0]["ProcessorInfo"]
    elif provider == "azure":
        data[0]["capabilities"] = []
    else:
        del data["architecture"]
    commands(monkeypatch, provider, machine=data)
    report = target_preflight(spec(provider), verify_target=True, verify_machine=True)
    assert report["machine_check"]["status"] == "architecture_unknown"


@pytest.mark.parametrize("provider", ["azure", "gcp"])
def test_reported_restrictions_and_deprecation_require_review(provider, monkeypatch):
    data = copy.deepcopy(MACHINES[provider])
    if provider == "azure":
        data[0]["restrictions"] = [{"type": "Zone", "reasonCode": "private-marker"}]
    else:
        data["deprecated"] = {"state": "DEPRECATED", "replacement": "private-marker"}
    commands(monkeypatch, provider, machine=data)
    report = target_preflight(spec(provider), verify_target=True, verify_machine=True)
    assert report["machine_check"]["status"] == "restricted"
    assert "private-marker" not in json.dumps(report)


@pytest.mark.parametrize(
    "provider,data",
    [
        ("aws", {"InstanceTypes": "private-marker"}),
        (
            "aws",
            {
                "InstanceTypes": [
                    {"InstanceType": "t3.micro", "ProcessorInfo": {"SupportedArchitectures": [[]]}}
                ]
            },
        ),
        ("azure", [{**MACHINES["azure"][0], "restrictions": "private-marker"}]),
        ("azure", [{**MACHINES["azure"][0], "locations": False}]),
        ("gcp", {**MACHINES["gcp"], "architecture": []}),
        ("gcp", {**MACHINES["gcp"], "zone": "wrong-zone"}),
    ],
)
def test_malformed_machine_metadata_fails_without_disclosure(provider, data, monkeypatch):
    commands(monkeypatch, provider, machine=data)
    report = target_preflight(spec(provider), verify_target=True, verify_machine=True)
    assert report["machine_check"]["status"] == "invalid_response"
    assert "private-marker" not in json.dumps(report)


@pytest.mark.parametrize("value", ["true", 1, None])
def test_machine_consent_must_be_boolean(value, monkeypatch):
    calls = commands(monkeypatch, "aws")
    with pytest.raises(ValueError):
        target_preflight(spec(), verify_target=True, verify_machine=value)
    assert not calls


def test_machine_check_requires_target_consent_before_any_tools(monkeypatch):
    calls = commands(monkeypatch, "aws")
    with pytest.raises(ValueError, match="target-check consent"):
        target_preflight(spec(), verify_machine=True)
    assert not calls


def test_cli_machine_metadata_exit_and_api_opt_in(tmp_path, monkeypatch):
    data = copy.deepcopy(MACHINES["aws"])
    data["InstanceTypes"][0]["ProcessorInfo"]["SupportedArchitectures"] = ["arm64"]
    commands(monkeypatch, "aws", machine=data)
    source = tmp_path / "project.json"
    source.write_text(spec().model_dump_json(), encoding="utf-8")
    result = CliRunner().invoke(
        main,
        [
            "preflight",
            "--spec",
            str(source),
            "--verify-target",
            "--verify-machine",
            "--json-output",
        ],
    )
    assert result.exit_code == 1
    assert json.loads(result.output)["machine_check"]["status"] == "architecture_incompatible"
    commands(monkeypatch, "aws")
    with TestClient(create_app(), base_url="http://127.0.0.1") as client:
        headers = {"X-TerraForma-Token": client.get("/api/session").json()["token"]}
        report = client.post(
            "/api/projects/preflight",
            headers=headers,
            json={
                "specification": spec().model_dump(),
                "verify_target": True,
                "verify_machine": True,
            },
        )
        assert report.status_code == 200
        assert report.json()["machine_check"]["status"] == "metadata_confirmed"


@pytest.mark.parametrize("provider", TARGETS)
def test_api_vm_metadata_checks_bind_the_selected_provider(provider, monkeypatch):
    calls = commands(monkeypatch, provider)
    with TestClient(create_app(), base_url="http://127.0.0.1") as client:
        headers = {"X-TerraForma-Token": client.get("/api/session").json()["token"]}
        result = client.post(
            "/api/projects/preflight",
            headers=headers,
            json={
                "specification": spec(provider).model_dump(),
                "verify_target": True,
                "verify_machine": True,
            },
        )
    assert result.status_code == 200 and len(calls) == 2
    assert result.json()["machine_check"]["status"] == "metadata_confirmed"


@pytest.mark.parametrize("value", ["true", 1, None])
def test_api_rejects_invalid_machine_consent_before_tools(value, monkeypatch):
    calls = commands(monkeypatch, "aws")
    with TestClient(create_app(), base_url="http://127.0.0.1") as client:
        headers = {"X-TerraForma-Token": client.get("/api/session").json()["token"]}
        result = client.post(
            "/api/projects/preflight",
            headers=headers,
            json={
                "specification": spec().model_dump(),
                "verify_target": True,
                "verify_machine": value,
            },
        )
    assert result.status_code == 422 and not calls


@pytest.mark.parametrize(
    "result",
    [
        CommandResult(2, b"private-marker", b"private-marker"),
        CommandResult(None, b"", b"private-marker", failure="timeout"),
        CommandResult(0, b'{"private-marker":1e999}', b""),
    ],
)
def test_vm_metadata_command_errors_and_invalid_json_do_not_affirm_size(result, monkeypatch):
    calls = []

    def run(*args, **kwargs):
        calls.append(args)
        return (
            CommandResult(0, json.dumps(TARGETS["aws"]).encode(), b"")
            if len(calls) == 1
            else result
        )

    monkeypatch.setattr("terraforma.preflight.shutil.which", lambda name: "fake-cloud-cli")
    monkeypatch.setattr("terraforma.preflight.run_bounded", run)
    report = target_preflight(spec(), verify_target=True, verify_machine=True)
    assert report["status"] == "target_confirmed"
    assert report["machine_check"]["status"] in {"failed", "invalid_response"}
    assert report["machine_check"]["architecture_compatible"] is None
    assert "private-marker" not in json.dumps(report)
