import hcl2
import pytest
from fastapi.testclient import TestClient

from terraforma.project import ProjectInputError, compile_project, input_contract
from terraforma.web import create_app
from tests.hcl_text import unaligned
from tests.test_gcp_windows_vm import specification


@pytest.mark.parametrize("public", [False, True])
@pytest.mark.parametrize("access", ["administrator_network", "iap_tunnel"])
@pytest.mark.parametrize("version", ["latest", "windows-server-2022-dc-v20261001"])
def test_exact_windows_image_preserves_publisher_and_access_options(public, access, version):
    spec = specification(public=public, image_version=version, admin_access_method=access)
    result = compile_project(spec)
    main = hcl2.loads(result["files"]["main.tf"])
    vm = next(
        item['"google_compute_instance"']['"this"']
        for item in main["resource"]
        if '"google_compute_instance"' in item
    )
    image = vm["boot_disk"][0]["initialize_params"][0]["image"]
    assert '"windows-cloud/${var.image_version}"' in image
    assert '"windows-cloud/windows-2022"' in image
    assert 'startswith(var.image_version, "windows-server-2022-dc-v")' in result["files"]["main.tf"]
    assert f'default = "{version}"' in unaligned(result["files"]["variables.tf"])
    assert (
        next(item for item in result["choice_summary"] if item["name"] == "image_version")["value"]
        == version
    )


@pytest.mark.parametrize(
    "version",
    [
        "windows-server-2019-dc-v20261001",
        "windows-server-2022-dc-core-v20261001",
        "windows-server-2022-dc-v1",
        "windows-server-2022-dc-v12345678901",
        "windows-server-2022-dc-v20261001-extra",
        "windows-cloud/windows-server-2022-dc-v20261001",
        "projects/other/global/images/windows-server-2022-dc-v20261001",
        "https://example.com/image",
        "ubuntu-2404-noble-v20261001",
        "${var.external_image}",
        True,
    ],
)
def test_image_pin_rejects_other_publishers_os_variants_and_expressions(version):
    with pytest.raises(ProjectInputError) as error:
        compile_project(specification(image_version=version))
    assert error.value.field == "image_version"


def test_api_round_trip_and_contract_keep_exact_name_without_availability_claim():
    version = "windows-server-2022-dc-v20261001"
    spec = specification(image_version=version)
    contract = {item["name"]: item for item in input_contract(spec.recipe)}
    assert contract["image_version"]["default"] == "latest"
    assert "Verify image availability" in contract["image_version"]["description"]
    with TestClient(create_app(), base_url="http://127.0.0.1") as client:
        headers = {"X-TerraForma-Token": client.get("/api/session").json()["token"]}
        imported = client.post("/api/projects/import", json=spec.model_dump(), headers=headers)
        generated = client.post("/api/generate", json=spec.model_dump(), headers=headers)
    assert imported.status_code == generated.status_code == 200
    assert imported.json()["files"] == generated.json()["files"]
    assert generated.json()["specification"]["inputs"]["image_version"] == version
    assert any(
        "availability" in note and "unverified" in note for note in generated.json()["notes"]
    )
