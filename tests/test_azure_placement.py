import itertools

import hcl2
import pytest
from fastapi.testclient import TestClient

from terraforma.generator import WizardConfig
from terraforma.project import ProjectSpecification, compile_project, input_contract
from terraforma.web import create_app
from tests.hcl_text import unaligned
from tests.test_azure_disk_caching import specification


@pytest.mark.parametrize(
    "windows,zone", list(itertools.product([False, True], ["regional", "1", "2", "3"]))
)
def test_placement_binds_vm_disk_nat_and_addresses_and_survives_import(windows, zone):
    spec = specification(windows, availability_zone=zone, enable_data_disk=True)
    spec.recipe.is_public = True
    spec.inputs["allowed_cidr"] = "10.20.0.0/24"
    with TestClient(create_app(), base_url="http://127.0.0.1") as client:
        headers = {"X-TerraForma-Token": client.get("/api/session").json()["token"]}
        response = client.post("/api/generate", json=spec.model_dump(), headers=headers)
        assert response.status_code == 200, response.text
        result = response.json()
    restored = ProjectSpecification.model_validate(result["specification"])
    assert restored.inputs["availability_zone"] == zone
    assert compile_project(restored)["files"] == result["files"]
    resources = {}
    for entry in hcl2.loads(result["files"]["main.tf"])["resource"]:
        for kind, instances in entry.items():
            resources.setdefault(kind, {}).update(instances)
    vm_kind = '"azurerm_windows_virtual_machine"' if windows else '"azurerm_linux_virtual_machine"'
    single_zone = '${var.availability_zone == "regional" ? null : var.availability_zone}'
    zone_list = '${var.availability_zone == "regional" ? null : [var.availability_zone]}'
    assert resources[vm_kind]['"this"']["zone"] == single_zone
    assert resources['"azurerm_managed_disk"']['"data"']["zone"] == single_zone
    assert resources['"azurerm_nat_gateway"']['"this"']["zones"] == zone_list
    assert resources['"azurerm_public_ip"']['"egress"']["zones"] == zone_list
    assert resources['"azurerm_public_ip"']['"web"']["zones"] == zone_list
    assert f'default = "{zone}"' in unaligned(result["files"]["variables.tf"])


@pytest.mark.parametrize("windows", [False, True])
def test_old_project_keeps_no_specific_zone_default_and_replacement_guidance(windows):
    field = next(
        item
        for item in input_contract(specification(windows).recipe)
        if item["name"] == "availability_zone"
    )
    assert field["default"] == "regional"
    assert field["choices"] == ["regional", "1", "2", "3"]
    assert "replaces resources" in field["description"]
    assert "does not establish disk/network zone support or capacity" in field["description"]
    assert compile_project(specification(windows))["files"]["main.tf"]


@pytest.mark.parametrize("zone", ["", "4", "eastus-1", 1, True])
def test_invalid_zone_choices_fail_closed(zone):
    with pytest.raises(ValueError):
        compile_project(specification(True, availability_zone=zone))


@pytest.mark.parametrize("workload", ["single_web_server", "load_balanced_tier", "secure_database"])
def test_other_azure_recipes_do_not_claim_standalone_zone_selection(workload):
    config = WizardConfig(provider="azure", project_name="example", architecture_type=workload)
    assert "availability_zone" not in {item["name"] for item in input_contract(config)}
