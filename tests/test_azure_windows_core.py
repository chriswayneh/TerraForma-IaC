import itertools

import hcl2
import pytest
from fastapi.testclient import TestClient

from terraforma.project import ProjectInputError, compile_project, input_contract
from terraforma.web import create_app
from tests.hcl_text import unaligned
from tests.test_azure_windows_vm import specification


@pytest.mark.parametrize(
    "public,version,secure_boot",
    list(itertools.product([False, True], ["latest", "20348.1.1"], [False, True])),
)
def test_core_selection_preserves_credentials_patch_and_boot_controls(public, version, secure_boot):
    result = compile_project(
        specification(
            public=public,
            os_image="windows-server-2022-core",
            image_version=version,
            enable_secure_boot=secure_boot,
            enable_data_disk=True,
        )
    )
    main = hcl2.loads(result["files"]["main.tf"])
    vm = next(
        item['"azurerm_windows_virtual_machine"']['"this"']
        for item in main["resource"]
        if '"azurerm_windows_virtual_machine"' in item
    )
    image_block = vm["dynamic"][0]['"source_image_reference"']
    assert image_block["for_each"] == "${var.use_custom_image ? [] : [1]}"
    assert vm["source_image_id"] == "${var.use_custom_image ? var.custom_image : null}"
    image = image_block["content"][0]
    assert image["publisher"] == '"MicrosoftWindowsServer"'
    assert image["offer"] == '"windowsserver2022"'
    assert '"2022-datacenter-core-g2"' in image["sku"]
    assert image["version"] == "${var.image_version}"
    assert vm["admin_password"] == "${var.admin_password}"
    assert vm["vtpm_enabled"] is True
    assert vm["secure_boot_enabled"] == "${var.enable_secure_boot}"
    assert vm["patch_mode"] == '"AutomaticByOS"'
    assert vm["automatic_updates_enabled"] is True
    assert vm["provision_vm_agent"] is True
    assert 'default = "windows-server-2022-core"' in unaligned(result["files"]["variables.tf"])
    assert f'default = "{version}"' in unaligned(result["files"]["variables.tf"])
    assert "admin_password" not in result["files"]["outputs.tf"]


@pytest.mark.parametrize("value", ["windows-server-2019-core", "windows-server-2025-core"])
def test_other_core_versions_remain_unsupported(value):
    with pytest.raises(ProjectInputError) as error:
        compile_project(specification(os_image=value))
    assert error.value.field == "os_image"


def test_core_api_import_preserves_choice_and_reports_guest_limits():
    spec = specification(os_image="windows-server-2022-core")
    contract = {item["name"]: item for item in input_contract(spec.recipe)}
    assert contract["os_image"]["default"] == "windows-server-2022"
    assert (
        contract["os_image"]["choice_labels"]["windows-server-2022-core"]
        == "Windows Server 2022 Core"
    )
    with TestClient(create_app(), base_url="http://127.0.0.1") as client:
        headers = {"X-TerraForma-Token": client.get("/api/session").json()["token"]}
        imported = client.post("/api/projects/import", json=spec.model_dump(), headers=headers)
        generated = client.post("/api/generate", json=spec.model_dump(), headers=headers)
    assert imported.status_code == generated.status_code == 200
    assert imported.json()["files"] == generated.json()["files"]
    assert any("Core omits the standard desktop" in note for note in generated.json()["notes"])
    assert generated.json()["specification"]["secret_references"] == spec.secret_references
