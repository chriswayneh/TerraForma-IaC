import io
import json
import zipfile

import pytest
from fastapi.testclient import TestClient

from terraforma.generator import WizardConfig
from terraforma.project import ProjectInputError, ProjectSpecification, compile_project
from terraforma.web import create_app

KEY = "ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAIAEBAQEBAQEBAQEBAQEBAQEBAQEBAQEBAQEBAQEBAQEB"


def specification(provider, cidr):
    inputs = {
        "aws": {"aws_account_id": "123456789012", "ssh_public_key": KEY},
        "azure": {"subscription_id": "12345678-1234-1234-1234-123456789abc", "ssh_public_key": KEY},
        "gcp": {"gcp_project_id": "example-project"},
    }[provider]
    return ProjectSpecification(
        recipe=WizardConfig(
            provider=provider, project_name="network-test", architecture_type="virtual_machine"
        ),
        inputs={**inputs, "network_cidr": cidr},
    )


@pytest.mark.parametrize("provider", ["aws", "azure", "gcp"])
@pytest.mark.parametrize("cidr", ["10.80.0.0/16", "172.20.0.0/20", "192.168.16.0/20"])
def test_private_vm_network_preserves_selected_range(provider, cidr):
    spec = specification(provider, cidr)
    compiled = compile_project(spec)
    main = compiled["files"]["main.tf"]
    assert "var.network_cidr" in main
    if provider == "azure":
        assert "cidrsubnet(var.network_cidr, 8, 1)" in main
    if provider == "aws":
        assert "cidrsubnet(aws_vpc.this[0].cidr_block, 8, count.index + 10)" in main
    summary = {item["name"]: item["value"] for item in compiled["choice_summary"]}
    assert summary["network_cidr"] == cidr
    with TestClient(create_app(), base_url="http://127.0.0.1") as client:
        headers = {"X-TerraForma-Token": client.get("/api/session").json()["token"]}
        exported = client.post("/api/download", headers=headers, json=spec.model_dump())
        assert exported.status_code == 200
        with zipfile.ZipFile(io.BytesIO(exported.content)) as archive:
            manifest = archive.read("terraforma.project.json")
            assert json.loads(manifest)["inputs"]["network_cidr"] == cidr
        imported = client.post("/api/projects/import", headers=headers, content=manifest)
        assert imported.status_code == 200
        assert imported.json()["files"] == compiled["files"]


@pytest.mark.parametrize("provider", ["aws", "azure", "gcp"])
@pytest.mark.parametrize(
    "cidr",
    [
        "0.0.0.0/0",
        "203.0.113.0/24",
        "100.64.0.0/16",
        "127.0.0.0/16",
        "169.254.0.0/16",
        "fc00::/16",
        "10.0.0.1/16",
        "10.0.0.0/15",
        "10.0.0.0/29",
        "10.0.0.0/255.255.0.0",
        "not-a-network-private-value",
    ],
)
def test_vm_network_rejects_unsupported_ranges_without_echoing_values(provider, cidr):
    with pytest.raises(ProjectInputError) as error:
        compile_project(specification(provider, cidr))
    assert error.value.field == "network_cidr"
    assert cidr not in str(error.value)


@pytest.mark.parametrize("provider", ["aws", "azure"])
def test_derived_subnets_reject_network_too_small(provider):
    with pytest.raises(ProjectInputError):
        compile_project(specification(provider, "10.0.0.0/21"))


def test_gcp_subnet_accepts_supported_smaller_range():
    assert (
        "10.0.0.0/28"
        in compile_project(specification("gcp", "10.0.0.0/28"))["files"]["variables.tf"]
    )
