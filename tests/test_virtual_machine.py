import io
import zipfile

import pytest
from fastapi.testclient import TestClient

from terraforma.generator import WizardConfig
from terraforma.project import ProjectSpecification, compile_project
from terraforma.web import create_app
from tests.hcl_text import unaligned

KEY = "ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAIAEBAQEBAQEBAQEBAQEBAQEBAQEBAQEBAQEBAQEBAQEB"


@pytest.mark.parametrize("provider", ["aws", "azure", "gcp"])
@pytest.mark.parametrize("public", [False, True])
def test_standalone_vm_exports_explicit_access_without_web_application(provider, public):
    inputs = {
        "aws": {"aws_account_id": "123456789012", "ssh_public_key": KEY},
        "azure": {"subscription_id": "12345678-1234-1234-1234-123456789abc", "ssh_public_key": KEY},
        "gcp": {"gcp_project_id": "example-project"},
    }[provider]
    config = WizardConfig(
        provider=provider,
        project_name="vm-test",
        architecture_type="virtual_machine",
        is_public=public,
    )
    specification = ProjectSpecification(
        recipe=config,
        inputs={**inputs, "allowed_cidr": "203.0.113.7/32" if public else "10.0.0.0/16"},
    )
    project = compile_project(specification)
    main = project["files"]["main.tf"]
    outputs = project["files"]["outputs.tf"]
    assert "nginx" not in main and "http://" not in outputs
    assert 'output "vm_address"' in outputs
    if provider == "aws":
        assert 'resource "aws_key_pair"' in main
        assert "public_key = var.ssh_public_key" in unaligned(main)
        assert "key_name = aws_key_pair.this.key_name" in unaligned(main)
        assert "from_port = 22" in unaligned(main) and "from_port = 80" not in unaligned(main)
        assert "user_data_base64 = var.enable_initialization ?" in unaligned(main)
        assert "ec2-user" in outputs and "ubuntu" in outputs
    elif provider == "azure":
        assert 'destination_port_range = "22"' in unaligned(main)
        assert "DenyOtherInbound" in main
        assert "disable_password_authentication = true" in unaligned(main)
        assert "custom_data = var.enable_initialization ?" in unaligned(main)
        assert "var.admin_username" in outputs
    else:
        assert 'ports = ["22"]' in unaligned(main) and 'ports = ["80"]' not in unaligned(main)
        assert '"enable-oslogin" = "TRUE"' in unaligned(main)
        assert '"block-project-ssh-keys" = "TRUE"' in unaligned(main)
        assert "35.191.0.0" not in main
        assert "metadata_startup_script = var.enable_initialization ?" in unaligned(main)
        assert "ssh_public_key" not in project["specification"]["inputs"]
    with TestClient(create_app(), base_url="http://127.0.0.1") as client:
        token = client.get("/api/session").json()["token"]
        headers = {"X-TerraForma-Token": token}
        response = client.post("/api/generate", headers=headers, json=specification.model_dump())
        assert response.status_code == 200
        assert "nginx" not in str(response.json()["guide"])
        assert "SSH" in str(response.json()["guide"])
        archive_response = client.post(
            "/api/download", headers=headers, json=specification.model_dump()
        )
        with zipfile.ZipFile(io.BytesIO(archive_response.content)) as archive:
            assert archive.read("main.tf").decode() == main
            assert "SSH" in archive.read("README.md").decode()


@pytest.mark.parametrize("provider", ["aws", "azure"])
def test_key_authenticated_vms_require_a_valid_public_key(provider):
    inputs = (
        {"aws_account_id": "123456789012"}
        if provider == "aws"
        else {"subscription_id": "12345678-1234-1234-1234-123456789abc"}
    )
    config = WizardConfig(
        provider=provider, project_name="vm-test", architecture_type="virtual_machine"
    )
    with pytest.raises(ValueError, match="ssh_public_key"):
        compile_project(ProjectSpecification(recipe=config, inputs=inputs))
    with pytest.raises(ValueError, match="ssh_public_key"):
        compile_project(
            ProjectSpecification(
                recipe=config, inputs={**inputs, "ssh_public_key": "-----BEGIN PRIVATE KEY-----"}
            )
        )


def test_public_vm_requires_explicit_client_network():
    config = WizardConfig(
        provider="gcp", project_name="vm-test", architecture_type="virtual_machine", is_public=True
    )
    with pytest.raises(ValueError, match="allowed_cidr"):
        compile_project(
            ProjectSpecification(recipe=config, inputs={"gcp_project_id": "example-project"})
        )
