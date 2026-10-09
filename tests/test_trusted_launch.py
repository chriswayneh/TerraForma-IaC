import io
import zipfile

import pytest
from fastapi.testclient import TestClient

from terraforma.generator import WizardConfig
from terraforma.project import ProjectSpecification, compile_project, input_contract
from terraforma.web import create_app
from tests.hcl_text import unaligned

KEY = "ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAIAEBAQEBAQEBAQEBAQEBAQEBAQEBAQEBAQEBAQEBAQEB"


def specification(enabled=True, image="ubuntu-22.04", public=False):
    return ProjectSpecification(
        recipe=WizardConfig(
            provider="azure",
            project_name="trusted-test",
            architecture_type="virtual_machine",
            is_public=public,
        ),
        inputs={
            "subscription_id": "12345678-1234-1234-1234-123456789abc",
            "ssh_public_key": KEY,
            "allowed_cidr": "10.1.0.0/24",
            "os_image": image,
            "enable_secure_boot": enabled,
        },
    )


@pytest.mark.parametrize("enabled", [False, True])
def test_trusted_launch_choice_survives_export_import(enabled):
    spec = specification(enabled)
    result = compile_project(spec)
    assert "secure_boot_enabled = var.enable_secure_boot" in unaligned(result["files"]["main.tf"])
    assert "vtpm_enabled = true" in unaligned(result["files"]["main.tf"])
    choice = next(item for item in result["choice_summary"] if item["name"] == "enable_secure_boot")
    assert choice["value"] == ("Enabled" if enabled else "Disabled")
    with TestClient(create_app(), base_url="http://127.0.0.1") as client:
        headers = {"X-TerraForma-Token": client.get("/api/session").json()["token"]}
        exported = client.post("/api/download", headers=headers, json=spec.model_dump())
        assert exported.status_code == 200
        with zipfile.ZipFile(io.BytesIO(exported.content)) as archive:
            imported = client.post(
                "/api/projects/import",
                headers=headers,
                content=archive.read("terraforma.project.json"),
            )
            assert imported.status_code == 200
            assert imported.json()["specification"]["inputs"]["enable_secure_boot"] is enabled
            assert imported.json()["files"]["main.tf"] == archive.read("main.tf").decode()


def test_trusted_launch_default_and_compatibility_guidance():
    spec = specification()
    del spec.inputs["enable_secure_boot"]
    result = compile_project(spec)
    choice = next(item for item in result["choice_summary"] if item["name"] == "enable_secure_boot")
    assert choice["value"] == "Enabled"
    question = next(
        item for item in input_contract(spec.recipe) if item["name"] == "enable_secure_boot"
    )
    assert question["default"] is True and question["kind"] == "boolean"
    assert "Unsigned" in question["description"] and "VM-size" in question["description"]
    assert "attestation" in question["description"]


@pytest.mark.parametrize("value", ["true", "false", 0, 1, None])
def test_trusted_launch_rejects_nonboolean_answers(value):
    with pytest.raises(ValueError):
        compile_project(specification(value))


@pytest.mark.parametrize(
    "workload", ["single_web_server", "load_balanced_tier", "secure_database", "static_site"]
)
def test_trusted_launch_is_not_silently_added_to_other_recipes(workload):
    recipe = WizardConfig(provider="azure", project_name="trusted-test", architecture_type=workload)
    assert not any(item["name"] == "enable_secure_boot" for item in input_contract(recipe))
