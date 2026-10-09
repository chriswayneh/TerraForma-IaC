import copy
import json

import pytest

from terraforma.preflight import target_preflight
from tests.test_aws_placement import specification
from tests.test_machine_preflight import MACHINES, commands


@pytest.mark.parametrize("windows", [False, True])
@pytest.mark.parametrize(
    "ebs,status,compatible",
    [
        ({"EncryptionSupport": "supported"}, "metadata_confirmed", True),
        ({"EncryptionSupport": "unsupported"}, "ebs_encryption_incompatible", False),
        ({}, "ebs_encryption_unknown", None),
        (None, "ebs_encryption_unknown", None),
        ({"EncryptionSupport": None}, "ebs_encryption_unknown", None),
        ({"EncryptionSupport": "private-marker"}, "invalid_response", None),
        ({"EncryptionSupport": True}, "invalid_response", None),
        ({"EncryptionSupport": {}}, "invalid_response", None),
        ([], "invalid_response", None),
    ],
)
def test_aws_encrypted_vm_disks_require_reported_ebs_support(
    windows, ebs, status, compatible, monkeypatch
):
    data = copy.deepcopy(MACHINES["aws"])
    data["InstanceTypes"][0]["EbsInfo"] = ebs
    calls = commands(monkeypatch, "aws", machine=data)
    report = target_preflight(
        specification(windows, instance_type="t3.micro"), verify_target=True, verify_machine=True
    )
    machine = report["machine_check"]
    assert machine["status"] == status
    if status != "invalid_response":
        assert machine["ebs_encryption_compatible"] is compatible
        assert machine["architecture_compatible"] is True
    assert len(calls) == 2
    assert report["approval_granted"] is False and report["deployment_readiness_verified"] is False
    assert "private-marker" not in json.dumps(report)


@pytest.mark.parametrize(
    "encryption,data_disk,required",
    [
        (True, False, True),
        (True, True, True),
        # Boot disks are always encrypted; the choice only selects the KMS key.
        (False, False, True),
        (False, True, True),
    ],
)
def test_required_encryption_matches_root_and_data_disk_configuration(
    encryption, data_disk, required, monkeypatch
):
    project = specification(False, enable_data_disk=data_disk)
    project.recipe.enable_encryption = encryption
    data = copy.deepcopy(MACHINES["aws"])
    del data["InstanceTypes"][0]["EbsInfo"]
    calls = commands(monkeypatch, "aws", machine=data)
    report = target_preflight(project, verify_target=True, verify_machine=True)
    assert report["machine_check"]["status"] == (
        "ebs_encryption_unknown" if required else "metadata_confirmed"
    )
    assert ("ebs_encryption_compatible" in report["machine_check"]) is required
    assert len(calls) == 2


@pytest.mark.parametrize("support", [None, "unsupported"])
def test_unresolved_disk_capability_prevents_the_zone_offering_read(support, monkeypatch):
    project = specification(False, availability_zone="us-east-1b")
    data = copy.deepcopy(MACHINES["aws"])
    data["InstanceTypes"][0]["EbsInfo"]["EncryptionSupport"] = support
    calls = commands(monkeypatch, "aws", machine=data)
    report = target_preflight(project, verify_target=True, verify_machine=True)
    assert report["machine_check"]["status"] in {
        "ebs_encryption_unknown",
        "ebs_encryption_incompatible",
    }
    assert "availability_zone_offered" not in report["machine_check"]
    assert len(calls) == 2


def test_incompatible_cpu_keeps_priority_over_unsupported_encryption(monkeypatch):
    data = copy.deepcopy(MACHINES["aws"])
    data["InstanceTypes"][0]["ProcessorInfo"]["SupportedArchitectures"] = ["arm64"]
    data["InstanceTypes"][0]["EbsInfo"]["EncryptionSupport"] = "unsupported"
    commands(monkeypatch, "aws", machine=data)
    report = target_preflight(specification(False), verify_target=True, verify_machine=True)
    assert report["machine_check"]["status"] == "architecture_incompatible"
    assert report["machine_check"]["ebs_encryption_compatible"] is False
