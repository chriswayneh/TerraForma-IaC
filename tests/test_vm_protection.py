import io
import json
import zipfile

import pytest
from fastapi.testclient import TestClient

from terraforma.generator import WizardConfig
from terraforma.project import ProjectSpecification, compile_project, input_contract
from terraforma.web import create_app
from tests.hcl_text import unaligned

KEY = "ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAIAEBAQEBAQEBAQEBAQEBAQEBAQEBAQEBAQEBAQEBAQEB"


def specification(provider, **answers):
    inputs = (
        {"aws_account_id": "123456789012", "ssh_public_key": KEY}
        if provider == "aws"
        else {"gcp_project_id": "example-project"}
    )
    return ProjectSpecification(
        recipe=WizardConfig(
            provider=provider, project_name="protected-vm", architecture_type="virtual_machine"
        ),
        inputs={**inputs, **answers},
    )


@pytest.mark.parametrize(
    "provider,attribute", [("aws", "disable_api_termination"), ("gcp", "deletion_protection")]
)
@pytest.mark.parametrize("enabled", [True, False])
def test_vm_protection_preserves_choice_and_explains_lifecycle(provider, attribute, enabled):
    spec = specification(provider, protect_vm=enabled)
    project = compile_project(spec)
    assert f"{attribute} = var.protect_vm" in unaligned(project["files"]["main.tf"])
    field = next(item for item in input_contract(spec.recipe) if item["name"] == "protect_vm")
    assert field["kind"] == "boolean" and field["default"] is True
    with TestClient(create_app(), base_url="http://127.0.0.1") as client:
        headers = {"X-TerraForma-Token": client.get("/api/session").json()["token"]}
        generated = client.post("/api/generate", headers=headers, json=spec.model_dump())
        assert generated.status_code == 200
        notes = "\n".join(generated.json()["notes"])
        assert f"protection is {'enabled' if enabled else 'disabled'}" in notes
        exported = client.post("/api/download", headers=headers, json=spec.model_dump())
        assert exported.status_code == 200
        with zipfile.ZipFile(io.BytesIO(exported.content)) as archive:
            manifest = archive.read("terraforma.project.json")
            assert json.loads(manifest)["inputs"]["protect_vm"] is enabled
            assert "first disable protection" in archive.read("README.md").decode()
        imported = client.post("/api/projects/import", headers=headers, content=manifest)
        assert imported.status_code == 200
        assert imported.json()["specification"]["inputs"]["protect_vm"] is enabled


@pytest.mark.parametrize("provider", ["aws", "gcp"])
def test_vm_protection_defaults_on(provider):
    project = compile_project(specification(provider))
    assert 'variable "protect_vm"' in project["files"]["variables.tf"]
    assert "default = true" in unaligned(
        project["files"]["variables.tf"].split('variable "protect_vm"')[1]
    )


@pytest.mark.parametrize("provider", ["aws", "gcp"])
@pytest.mark.parametrize("value", ["false", 0, 1])
def test_vm_protection_rejects_coercion(provider, value):
    with pytest.raises(ValueError):
        compile_project(specification(provider, protect_vm=value))


@pytest.mark.parametrize("provider", ["aws", "azure", "gcp"])
def test_unavailable_protection_input_is_not_silently_accepted(provider):
    config = WizardConfig(
        provider=provider, project_name="protected-vm", architecture_type="single_web_server"
    )
    assert "protect_vm" not in {field["name"] for field in input_contract(config)}
    with pytest.raises(ValueError):
        compile_project(ProjectSpecification(recipe=config, inputs={"protect_vm": True}))
