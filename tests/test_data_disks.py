import io
import json
import zipfile
from unittest.mock import Mock

import pytest
from fastapi.testclient import TestClient

from terraforma.cli import collect_recipe_inputs
from terraforma.generator import WizardConfig
from terraforma.project import ProjectSpecification, compile_project, input_contract
from terraforma.web import create_app

KEY = "ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAIAEBAQEBAQEBAQEBAQEBAQEBAQEBAQEBAQEBAQEBAQEB"


def vm_spec(provider, **answers):
    target = {
        "aws": {"aws_account_id": "123456789012", "ssh_public_key": KEY},
        "azure": {"subscription_id": "12345678-1234-1234-1234-123456789abc", "ssh_public_key": KEY},
        "gcp": {"gcp_project_id": "example-project"},
    }[provider]
    return ProjectSpecification(
        recipe=WizardConfig(
            provider=provider, project_name="disk-test", architecture_type="virtual_machine"
        ),
        inputs={**target, **answers},
    )


@pytest.mark.parametrize(
    "provider,disk_type", [("aws", "gp2"), ("azure", "Standard_LRS"), ("gcp", "pd-ssd")]
)
@pytest.mark.parametrize("enabled", [True, False])
def test_data_disk_export_import_and_active_summary(provider, disk_type, enabled):
    specification = vm_spec(
        provider, enable_data_disk=enabled, data_disk_size_gb=256, data_disk_type=disk_type
    )
    compiled = compile_project(specification)
    assert 'output "data_disk_id"' in compiled["files"]["outputs.tf"]
    assert "var.enable_data_disk ? 1 : 0" in compiled["files"]["main.tf"]
    choices = {item["name"]: item for item in compiled["choice_summary"]}
    assert ("data_disk_size_gb" in choices) is enabled
    assert ("data_disk_type" in choices) is enabled
    if enabled:
        assert choices["data_disk_size_gb"]["value"] == "256"
        assert choices["data_disk_type"]["value"] == disk_type
    with TestClient(create_app(), base_url="http://127.0.0.1") as client:
        headers = {"X-TerraForma-Token": client.get("/api/session").json()["token"]}
        generated = client.post("/api/generate", headers=headers, json=specification.model_dump())
        assert generated.status_code == 200
        data_components = [
            item for item in generated.json()["guide"]["components"] if "data disk" in item["name"]
        ]
        assert bool(data_components) is enabled
        response = client.post("/api/download", headers=headers, json=specification.model_dump())
        assert response.status_code == 200
        with zipfile.ZipFile(io.BytesIO(response.content)) as archive:
            manifest = archive.read("terraforma.project.json")
            assert json.loads(manifest)["inputs"] == specification.inputs
            if enabled:
                assert "teardown can delete the disk" in archive.read("README.md").decode()
        imported = client.post("/api/projects/import", headers=headers, content=manifest)
        assert imported.status_code == 200
        assert imported.json()["files"] == compiled["files"]


@pytest.mark.parametrize("provider", ["aws", "azure", "gcp"])
@pytest.mark.parametrize("value", [31, 2049, True, "100"])
def test_data_disk_size_rejects_invalid_types_and_bounds(provider, value):
    with pytest.raises(ValueError):
        compile_project(vm_spec(provider, enable_data_disk=True, data_disk_size_gb=value))


@pytest.mark.parametrize("provider", ["aws", "azure", "gcp"])
def test_data_disk_type_cannot_silently_fall_back(provider):
    with pytest.raises(ValueError):
        compile_project(
            vm_spec(provider, enable_data_disk=True, data_disk_type="unsupported-class")
        )


@pytest.mark.parametrize("provider", ["aws", "azure", "gcp"])
@pytest.mark.parametrize("enabled", [True, False])
def test_terminal_only_asks_active_data_disk_questions(provider, enabled, monkeypatch):
    answers = {"enable_data_disk": enabled, "data_disk_size_gb": 256}
    template = vm_spec(provider, **answers)
    definitions = input_contract(template.recipe)
    prompts = []

    def prompt(message, **kwargs):
        definition = next(
            item
            for item in definitions
            if message.startswith(item["label"] + ":") or message == item["label"] + "?"
        )
        prompts.append(definition["name"])
        value = template.inputs.get(definition["name"], definition["default"])
        if definition["kind"] == "integer":
            value = str(value)
        return Mock(ask=lambda: value)

    for name in ("text", "select", "confirm"):
        monkeypatch.setattr(f"terraforma.cli.questionary.{name}", prompt)
    result = collect_recipe_inputs(template.recipe)
    assert ("data_disk_size_gb" in prompts) is enabled
    assert ("data_disk_type" in prompts) is enabled
    assert result.inputs["enable_data_disk"] is enabled
    if enabled:
        assert result.inputs["data_disk_size_gb"] == 256


def test_aws_data_disk_is_encrypted_and_never_forces_detach():
    specification = vm_spec("aws", enable_data_disk=True)
    specification.recipe.enable_encryption = False
    main = compile_project(specification)["files"]["main.tf"]
    disk = main.split('resource "aws_ebs_volume" "data"')[1].split(
        'resource "aws_volume_attachment"'
    )[0]
    assert "encrypted = true" in disk
    assert "force_detach = false" in main and "stop_instance_before_detaching = true" in main


@pytest.mark.parametrize("provider", ["aws", "azure", "gcp"])
def test_web_tier_does_not_accept_standalone_disk_inputs(provider):
    config = WizardConfig(
        provider=provider, project_name="disk-test", architecture_type="single_web_server"
    )
    assert "enable_data_disk" not in {field["name"] for field in input_contract(config)}
    with pytest.raises(ValueError):
        compile_project(ProjectSpecification(recipe=config, inputs={"enable_data_disk": True}))
