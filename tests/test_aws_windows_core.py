import itertools

import hcl2
import pytest
from fastapi.testclient import TestClient

from terraforma.project import ProjectInputError, compile_project, input_contract
from terraforma.web import create_app
from tests.test_azure_windows_vm import specification as azure_specification
from tests.test_gcp_windows_vm import specification as gcp_specification
from tests.test_windows_vm import specification


@pytest.mark.parametrize(
    "public,version,delete",
    list(itertools.product([False, True], ["latest", "ami-0123456789abcdef0"], [False, True])),
)
def test_core_preserves_owner_architecture_hvm_and_boot_lifecycle(public, version, delete):
    result = compile_project(
        specification(
            public=public,
            os_image="windows-server-2022-core",
            image_version=version,
            delete_boot_disk_with_vm=delete,
        )
    )
    main = hcl2.loads(result["files"]["main.tf"])
    ami = next(item['"aws_ami"']['"windows"'] for item in main["data"] if '"aws_ami"' in item)
    assert ami["owners"] == ['"amazon"']
    filters = {item["name"]: item["values"] for item in ami["filter"]}
    assert "Windows_Server-2022-English-Core-Base-*" in str(filters['"name"'])
    assert "Windows_Server-2022-English-Full-Base-*" in str(filters['"name"'])
    assert filters['"architecture"'] == ['"x86_64"']
    assert filters['"virtualization-type"'] == ['"hvm"']
    assert f'default = "{version}"' in result["files"]["variables.tf"]
    assert 'default = "windows-server-2022-core"' in result["files"]["variables.tf"]
    assert "var.delete_boot_disk_with_vm" in result["files"]["main.tf"]


@pytest.mark.parametrize(
    "value",
    [
        "windows-server-2025-core",
        "TPM-Windows_Server-2022-English-Core-Base",
        "custom-windows",
        True,
    ],
)
def test_other_windows_images_are_rejected(value):
    with pytest.raises(ProjectInputError) as error:
        compile_project(specification(os_image=value))
    assert error.value.field == "os_image"


@pytest.mark.parametrize("factory", [azure_specification, gcp_specification])
def test_other_providers_do_not_offer_aws_core(factory):
    contract = {item["name"]: item for item in input_contract(factory().recipe)}
    assert "windows-server-2022-core" not in contract["os_image"]["choices"]


def test_core_api_round_trip_and_full_base_default():
    contract = {item["name"]: item for item in input_contract(specification().recipe)}
    assert contract["os_image"]["default"] == "windows-server-2022"
    spec = specification(os_image="windows-server-2022-core")
    with TestClient(create_app(), base_url="http://127.0.0.1") as client:
        headers = {"X-TerraForma-Token": client.get("/api/session").json()["token"]}
        imported = client.post("/api/projects/import", json=spec.model_dump(), headers=headers)
        generated = client.post("/api/generate", json=spec.model_dump(), headers=headers)
    assert imported.status_code == generated.status_code == 200
    assert imported.json()["files"] == generated.json()["files"]
    assert generated.json()["specification"]["inputs"]["os_image"] == "windows-server-2022-core"
    assert any("Core omits the standard desktop" in note for note in generated.json()["notes"])
