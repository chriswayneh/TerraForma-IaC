import io
import zipfile

import pytest
from fastapi.testclient import TestClient

from terraforma.generator import TerraformGenerator, WizardConfig
from terraforma.project import (
    ProjectInputError,
    ProjectSpecification,
    compile_project,
    input_contract,
)
from terraforma.web import create_app


def specification(enabled=True, image="debian-12", public=False):
    return ProjectSpecification(
        recipe=WizardConfig(
            provider="gcp",
            project_name="shielded-test",
            architecture_type="virtual_machine",
            is_public=public,
        ),
        inputs={
            "gcp_project_id": "example-project",
            "allowed_cidr": "10.1.0.0/24",
            "os_image": image,
            "enable_secure_boot": enabled,
        },
    )


@pytest.mark.parametrize("enabled", [False, True])
def test_secure_boot_answer_changes_output_and_survives_browser_export_import(enabled):
    spec = specification(enabled)
    result = compile_project(spec)
    assert "enable_secure_boot = var.enable_secure_boot" in result["files"]["main.tf"]
    assert "enable_vtpm = true" in result["files"]["main.tf"]
    assert "enable_integrity_monitoring = true" in result["files"]["main.tf"]
    assert "allow_stopping_for_update = false" in result["files"]["main.tf"]
    choice = next(item for item in result["choice_summary"] if item["name"] == "enable_secure_boot")
    assert choice["value"] == ("Enabled" if enabled else "Disabled")
    with TestClient(create_app(), base_url="http://127.0.0.1") as client:
        headers = {"X-TerraForma-Token": client.get("/api/session").json()["token"]}
        exported = client.post("/api/download", json=spec.model_dump(), headers=headers)
        assert exported.status_code == 200
        with zipfile.ZipFile(io.BytesIO(exported.content)) as archive:
            imported = client.post(
                "/api/projects/import",
                content=archive.read("terraforma.project.json"),
                headers=headers,
            )
            assert imported.status_code == 200
            assert imported.json()["specification"]["inputs"]["enable_secure_boot"] is enabled
            assert imported.json()["files"]["variables.tf"] == archive.read("variables.tf").decode()


def test_secure_boot_default_and_contract_describe_compatibility_and_stopping():
    contract = input_contract(specification().recipe)
    question = next(item for item in contract if item["name"] == "enable_secure_boot")
    assert question["kind"] == "boolean" and question["default"] is True
    assert "Unsigned" in question["description"] and "stopped VM" in question["description"]
    spec = specification()
    del spec.inputs["enable_secure_boot"]
    result = compile_project(spec)
    choice = next(item for item in result["choice_summary"] if item["name"] == "enable_secure_boot")
    assert choice["value"] == "Enabled"


@pytest.mark.parametrize("value", ["true", "false", 0, 1])
def test_secure_boot_rejects_nonboolean_questionnaire_answers(value):
    spec = specification()
    spec.inputs["enable_secure_boot"] = value
    with pytest.raises(ProjectInputError, match="enable_secure_boot"):
        compile_project(spec)


@pytest.mark.parametrize(
    "provider,workload",
    [
        ("aws", "virtual_machine"),
        ("azure", "virtual_machine"),
        ("gcp", "single_web_server"),
        ("gcp", "load_balanced_tier"),
    ],
)
def test_shielded_choice_is_not_exposed_by_other_recipes(provider, workload):
    config = WizardConfig(provider=provider, project_name="example", architecture_type=workload)
    assert not any(item["name"] == "enable_secure_boot" for item in input_contract(config))
    assert "shielded_instance_config" not in TerraformGenerator(config).generate()["main.tf"]
