import io
import zipfile

import pytest
from fastapi.testclient import TestClient

from terraforma.generator import WizardConfig
from terraforma.project import compile_project, input_contract
from terraforma.web import create_app
from tests.test_trusted_launch import specification


@pytest.mark.parametrize("enabled", [False, True])
def test_managed_boot_diagnostics_survive_export_and_import(enabled):
    spec = specification()
    spec.inputs["enable_boot_diagnostics"] = enabled
    result = compile_project(spec)
    main = result["files"]["main.tf"]
    assert 'dynamic "boot_diagnostics"' in main
    assert "for_each = var.enable_boot_diagnostics ? [1] : []" in main
    assert "storage_account_uri = null" in main
    assert "azurerm_storage_account" not in main
    assert "diagnostic" not in result["files"]["outputs.tf"]
    choice = next(
        item for item in result["choice_summary"] if item["name"] == "enable_boot_diagnostics"
    )
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
            assert imported.json()["specification"]["inputs"]["enable_boot_diagnostics"] is enabled
            assert imported.json()["files"]["variables.tf"] == archive.read("variables.tf").decode()


def test_boot_diagnostics_default_off_and_limits_are_explained():
    spec = specification()
    question = next(
        item for item in input_contract(spec.recipe) if item["name"] == "enable_boot_diagnostics"
    )
    assert question["kind"] == "boolean" and question["default"] is False
    assert "sensitive data" in question["description"] and "1 GB" in question["description"]
    assert "not billed" in question["description"] and "not configurable" in question["description"]


@pytest.mark.parametrize("value", ["true", "false", 0, 1, None])
def test_boot_diagnostics_reject_coerced_answers(value):
    spec = specification()
    spec.inputs["enable_boot_diagnostics"] = value
    with pytest.raises(ValueError):
        compile_project(spec)


@pytest.mark.parametrize(
    "provider,workload",
    [
        ("aws", "virtual_machine"),
        ("gcp", "virtual_machine"),
        ("azure", "single_web_server"),
        ("azure", "load_balanced_tier"),
    ],
)
def test_boot_diagnostics_option_is_scoped_to_azure_standalone_vm(provider, workload):
    recipe = WizardConfig(provider=provider, project_name="boot-test", architecture_type=workload)
    assert not any(item["name"] == "enable_boot_diagnostics" for item in input_contract(recipe))
