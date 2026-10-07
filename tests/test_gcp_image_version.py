import io
import zipfile

import pytest
from fastapi.testclient import TestClient

from terraforma.project import compile_project
from terraforma.web import create_app
from tests.test_shielded_vm import specification


@pytest.mark.parametrize(
    "image,version",
    [
        ("debian-12", "debian-12-bookworm-v20240213"),
        ("ubuntu-24.04", "ubuntu-2404-noble-amd64-v20261001"),
        ("ubuntu-24.04", "ubuntu-2404-noble-v20261001"),
    ],
)
def test_gcp_named_image_pins_publisher_and_survives_export_import(image, version):
    spec = specification(image=image)
    spec.inputs["image_version"] = version
    result = compile_project(spec)
    assert "debian-cloud/${var.image_version}" in result["files"]["main.tf"]
    assert "ubuntu-os-cloud/${var.image_version}" in result["files"]["main.tf"]
    assert "startswith(var.image_version" in result["files"]["main.tf"]
    choice = next(item for item in result["choice_summary"] if item["name"] == "image_version")
    assert choice["value"] == version
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
            assert imported.json()["specification"]["inputs"]["image_version"] == version


@pytest.mark.parametrize(
    "image,version",
    [
        ("debian-12", "ubuntu-2404-noble-v20261001"),
        ("ubuntu-24.04", "debian-12-bookworm-v20240213"),
    ],
)
def test_gcp_image_name_must_match_selected_os(image, version):
    spec = specification(image=image)
    spec.inputs["image_version"] = version
    with pytest.raises(ValueError, match="image_version"):
        compile_project(spec)


@pytest.mark.parametrize(
    "version",
    [
        "",
        "debian-12",
        "ubuntu-2404-noble-arm64-v20261001",
        "other-project/image",
        "https://example.com/image",
        "debian-12-bookworm-v20240213\n",
        123,
        True,
    ],
)
def test_gcp_image_pins_reject_families_arm_and_arbitrary_references(version):
    spec = specification()
    spec.inputs["image_version"] = version
    with pytest.raises(ValueError):
        compile_project(spec)
