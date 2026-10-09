import itertools

import hcl2
import pytest
from fastapi.testclient import TestClient

from terraforma.project import ProjectInputError, compile_project, input_contract
from terraforma.web import create_app
from tests.hcl_text import unaligned
from tests.test_gcp_windows_vm import specification


@pytest.mark.parametrize(
    "public,access,version",
    list(
        itertools.product(
            [False, True],
            ["administrator_network", "iap_tunnel"],
            ["latest", "windows-server-2022-dc-core-v20261001"],
        )
    ),
)
def test_core_selection_preserves_access_boot_and_publisher(public, access, version):
    result = compile_project(
        specification(
            public=public,
            os_image="windows-server-2022-core",
            admin_access_method=access,
            image_version=version,
        )
    )
    main = hcl2.loads(result["files"]["main.tf"])
    vm = next(
        item['"google_compute_instance"']['"this"']
        for item in main["resource"]
        if '"google_compute_instance"' in item
    )
    image = vm["boot_disk"][0]["initialize_params"][0]["image"]
    assert '"windows-cloud/windows-2022-core"' in image
    assert '"windows-cloud/${var.image_version}"' in image
    assert 'default = "windows-server-2022-core"' in unaligned(result["files"]["variables.tf"])
    assert f'default = "{version}"' in unaligned(result["files"]["variables.tf"])
    assert vm["shielded_instance_config"][0]["enable_vtpm"] is True
    assert '"serial-port-enable" = "FALSE"' in unaligned(vm["metadata"])
    assert "windows_activation" in result["files"]["main.tf"]


@pytest.mark.parametrize(
    "os_image,version",
    [
        ("windows-server-2022-core", "windows-server-2022-dc-v20261001"),
        ("windows-server-2022", "windows-server-2022-dc-core-v20261001"),
    ],
)
def test_full_and_core_pins_cannot_be_mixed(os_image, version):
    with pytest.raises(ProjectInputError) as error:
        compile_project(specification(os_image=os_image, image_version=version))
    assert error.value.field == "image_version"


@pytest.mark.parametrize("os_image", ["windows-server-2019-core", "windows-server-2025-core"])
def test_other_core_versions_remain_unsupported(os_image):
    with pytest.raises(ProjectInputError) as error:
        compile_project(specification(os_image=os_image))
    assert error.value.field == "os_image"


def test_core_api_import_preserves_choice_and_reports_guest_limits():
    spec = specification(os_image="windows-server-2022-core", admin_access_method="iap_tunnel")
    contract = {item["name"]: item for item in input_contract(spec.recipe)}
    assert contract["os_image"]["default"] == "windows-server-2022"
    with TestClient(create_app(), base_url="http://127.0.0.1") as client:
        headers = {"X-TerraForma-Token": client.get("/api/session").json()["token"]}
        imported = client.post("/api/projects/import", json=spec.model_dump(), headers=headers)
        generated = client.post("/api/generate", json=spec.model_dump(), headers=headers)
    assert imported.status_code == generated.status_code == 200
    assert imported.json()["files"] == generated.json()["files"]
    assert any("Core omits the standard desktop" in note for note in generated.json()["notes"])
    assert generated.json()["guide"]["route"][0] == "Authorized Google IAP tunnel"
