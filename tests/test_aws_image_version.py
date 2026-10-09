import io
import zipfile

import pytest
from fastapi.testclient import TestClient

from terraforma.project import compile_project, input_contract
from terraforma.web import create_app
from tests.hcl_text import unaligned
from tests.test_vm_protection import specification


@pytest.mark.parametrize("version", ["latest", "ami-12345678", "ami-0123456789abcdef0"])
def test_aws_pin_retains_owner_os_architecture_filters_and_export(version):
    spec = specification("aws", image_version=version)
    result = compile_project(spec)
    main = result["files"]["main.tf"]
    assert (
        'owners = var.os_image == "amazon-linux-2023" ? ["amazon"] : ["099720109477"]'
        in unaligned(main)
    )
    assert 'name = "architecture"' in unaligned(main) and 'values = ["x86_64"]' in unaligned(main)
    assert 'name = "image-id"' in unaligned(main) and "values = [filter.value]" in unaligned(main)
    assert 'for_each = var.image_version == "latest" ? [] : [var.image_version]' in unaligned(main)
    assert "al2023-ami-2023.*-x86_64" in main and "ubuntu-noble-24.04-amd64-server-*" in main
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
    "value",
    [
        "",
        "LATEST",
        "ami-123",
        "ami-0123456789abcdef00",
        "ami-ABCDEF12",
        "other-account/ami-12345678",
        "ami-12345678\n",
        123,
        True,
    ],
)
def test_aws_pin_rejects_invalid_ids_and_arbitrary_references(value):
    with pytest.raises(ValueError):
        compile_project(specification("aws", image_version=value))


def test_aws_pin_question_explains_replacement_and_constraints():
    recipe = specification("aws").recipe
    question = next(item for item in input_contract(recipe) if item["name"] == "image_version")
    assert question["default"] == "latest"
    assert "trusted owner" in question["description"] and "replace" in question["description"]
