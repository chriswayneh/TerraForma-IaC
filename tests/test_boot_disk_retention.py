import itertools

import hcl2
import pytest
from fastapi.testclient import TestClient

from terraforma.generator import WizardConfig
from terraforma.project import ProjectInputError, compile_project, input_contract
from terraforma.web import create_app
from tests.hcl_text import unaligned
from tests.test_cpu_credit_mode import specification as aws_specification
from tests.test_gcp_scheduling import specification as gcp_specification


def specification(provider, windows=False, **inputs):
    return (aws_specification if provider == "aws" else gcp_specification)(windows, **inputs)


@pytest.mark.parametrize(
    "provider,windows,delete",
    list(itertools.product(["aws", "gcp"], [False, True], [False, True])),
)
def test_retention_binds_only_the_standalone_boot_disk(provider, windows, delete):
    spec = specification(provider, windows, delete_boot_disk_with_vm=delete, enable_data_disk=True)
    result = compile_project(spec)
    main = hcl2.loads(result["files"]["main.tf"])
    resource_type = '"aws_instance"' if provider == "aws" else '"google_compute_instance"'
    name = '"web"' if provider == "aws" else '"this"'
    vm = next(item[resource_type][name] for item in main["resource"] if resource_type in item)
    boot = vm["root_block_device" if provider == "aws" else "boot_disk"][0]
    assert (
        boot["delete_on_termination" if provider == "aws" else "auto_delete"]
        == "${var.delete_boot_disk_with_vm}"
    )
    assert f"default = {str(delete).lower()}" in unaligned(result["files"]["variables.tf"])
    assert result["files"]["main.tf"].count("var.delete_boot_disk_with_vm") == 1
    assert any(
        '"aws_ebs_volume"' in item or '"google_compute_disk"' in item for item in main["resource"]
    )


@pytest.mark.parametrize("provider,windows", list(itertools.product(["aws", "gcp"], [False, True])))
def test_old_projects_keep_deletion_default_and_explain_retention_boundaries(provider, windows):
    spec = specification(provider, windows)
    definition = next(
        item for item in input_contract(spec.recipe) if item["name"] == "delete_boot_disk_with_vm"
    )
    assert definition["default"] is True
    assert "not a backup" in definition["description"]
    assert "does not retain separately managed data disks" in definition["description"]
    assert compile_project(spec)["files"]["main.tf"]


@pytest.mark.parametrize(
    "provider,value", list(itertools.product(["aws", "gcp"], ["false", 0, "retain"]))
)
def test_retention_requires_boolean(provider, value):
    with pytest.raises(ProjectInputError) as error:
        compile_project(specification(provider, delete_boot_disk_with_vm=value))
    assert error.value.field == "delete_boot_disk_with_vm"


@pytest.mark.parametrize("provider", ["aws", "gcp"])
@pytest.mark.parametrize("encryption", [False, True])
def test_retention_api_import_preserves_false_and_does_not_provision(provider, encryption):
    spec = specification(provider, True, delete_boot_disk_with_vm=False)
    spec.recipe.enable_encryption = encryption
    with TestClient(create_app(), base_url="http://127.0.0.1") as client:
        headers = {"X-TerraForma-Token": client.get("/api/session").json()["token"]}
        imported = client.post("/api/projects/import", json=spec.model_dump(), headers=headers)
        generated = client.post("/api/generate", json=spec.model_dump(), headers=headers)
    assert imported.status_code == generated.status_code == 200
    assert imported.json()["files"] == generated.json()["files"]
    assert generated.json()["specification"]["inputs"]["delete_boot_disk_with_vm"] is False
    notes = " ".join(generated.json()["notes"])
    assert "Boot disk retention is requested" in notes
    assert ("Preserve the AWS KMS key separately" in notes) is (provider == "aws" and encryption)
    assert ("replacement disk naming" in notes) is (provider == "gcp")


@pytest.mark.parametrize(
    "provider,workload",
    [
        ("azure", "virtual_machine"),
        ("azure", "windows_virtual_machine"),
        ("aws", "single_web_server"),
        ("gcp", "load_balanced_tier"),
    ],
)
def test_unrelated_recipes_do_not_offer_retention(provider, workload):
    recipe = WizardConfig(provider=provider, architecture_type=workload, project_name="demo")
    assert "delete_boot_disk_with_vm" not in {item["name"] for item in input_contract(recipe)}
