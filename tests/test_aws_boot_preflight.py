import copy
import json

import pytest

from terraforma.preflight import target_preflight
from tests.test_aws_placement import specification
from tests.test_machine_preflight import MACHINES, commands


@pytest.mark.parametrize("windows", [False, True])
@pytest.mark.parametrize(
    "roots,virtualization,status,compatible",
    [
        (["ebs"], ["hvm"], "metadata_confirmed", True),
        (["instance-store", "ebs"], ["paravirtual", "hvm"], "metadata_confirmed", True),
        (["instance-store"], ["hvm"], "aws_boot_incompatible", False),
        (["ebs"], ["paravirtual"], "aws_boot_incompatible", False),
        (["instance-store"], None, "aws_boot_incompatible", False),
        (None, ["paravirtual"], "aws_boot_incompatible", False),
        (None, ["hvm"], "aws_boot_unknown", None),
        (["ebs"], None, "aws_boot_unknown", None),
        ([], ["hvm"], "aws_boot_unknown", None),
        (["ebs"], [], "aws_boot_unknown", None),
        (None, None, "aws_boot_unknown", None),
        (["ebs", "ebs"], ["hvm"], "invalid_response", None),
        (["ebs"], ["hvm", "hvm"], "invalid_response", None),
        (["private-marker"], ["hvm"], "invalid_response", None),
        (["ebs"], ["private-marker"], "invalid_response", None),
        ("ebs", ["hvm"], "invalid_response", None),
        (["ebs"], True, "invalid_response", None),
        ([{}], ["hvm"], "invalid_response", None),
        (["ebs"], [None], "invalid_response", None),
    ],
)
def test_standalone_vm_boot_metadata_is_strict_redacted_and_not_approval(
    windows, roots, virtualization, status, compatible, monkeypatch
):
    machine = copy.deepcopy(MACHINES["aws"])
    machine["InstanceTypes"][0].update(
        SupportedRootDeviceTypes=roots, SupportedVirtualizationTypes=virtualization
    )
    calls = commands(monkeypatch, "aws", machine=machine)
    report = target_preflight(
        specification(windows, instance_type="t3.micro"), verify_target=True, verify_machine=True
    )
    assert report["machine_check"]["status"] == status
    if status != "invalid_response":
        assert report["machine_check"]["ebs_hvm_boot_compatible"] is compatible
    assert report["approval_granted"] is False and report["deployment_readiness_verified"] is False
    assert "private-marker" not in json.dumps(report)
    assert len(calls) == 2


@pytest.mark.parametrize("roots", [None, ["instance-store"]])
def test_unresolved_boot_support_skips_the_zone_read_even_with_root_encryption_off(
    roots, monkeypatch
):
    project = specification(False, availability_zone="us-east-1b")
    project.recipe.enable_encryption = False
    machine = copy.deepcopy(MACHINES["aws"])
    machine["InstanceTypes"][0]["SupportedRootDeviceTypes"] = roots
    calls = commands(monkeypatch, "aws", machine=machine)
    report = target_preflight(project, verify_target=True, verify_machine=True)
    assert report["machine_check"]["status"] in {"aws_boot_unknown", "aws_boot_incompatible"}
    assert "availability_zone_offered" not in report["machine_check"]
    assert len(calls) == 2


def test_cpu_incompatibility_keeps_priority_over_boot_incompatibility(monkeypatch):
    machine = copy.deepcopy(MACHINES["aws"])
    machine["InstanceTypes"][0]["ProcessorInfo"]["SupportedArchitectures"] = ["arm64"]
    machine["InstanceTypes"][0]["SupportedVirtualizationTypes"] = ["paravirtual"]
    commands(monkeypatch, "aws", machine=machine)
    report = target_preflight(specification(False), verify_target=True, verify_machine=True)
    assert report["machine_check"]["status"] == "architecture_incompatible"
    assert report["machine_check"]["ebs_hvm_boot_compatible"] is False
