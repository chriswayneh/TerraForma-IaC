import io
import zipfile

import pytest
from fastapi.testclient import TestClient

from terraforma.generator import WizardConfig
from terraforma.project import compile_project, input_contract
from terraforma.web import create_app
from tests.hcl_text import unaligned
from tests.test_trusted_launch import specification


@pytest.mark.parametrize("version", ["latest", "22.04.20261001"])
def test_azure_image_version_preserves_pin_and_publisher_in_export(version):
    spec = specification()
    spec.inputs["image_version"] = version
    result = compile_project(spec)
    main = result["files"]["main.tf"]
    assert 'publisher = "Canonical"' in unaligned(
        main
    ) and "version = var.image_version" in unaligned(main)
    assert 'variable "image_version"' in result["files"]["variables.tf"]
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
            assert imported.json()["files"]["variables.tf"] == archive.read("variables.tf").decode()


@pytest.mark.parametrize(
    "version",
    [
        "",
        "Latest",
        "1.2",
        "1.2.3.4",
        "1.2.-3",
        "${secret}",
        "1.2.3\n",
        123,
        True,
        "12345678901.1.1",
    ],
)
def test_invalid_image_versions_are_rejected(version):
    spec = specification()
    spec.inputs["image_version"] = version
    with pytest.raises(ValueError):
        compile_project(spec)


@pytest.mark.parametrize("workload", ["virtual_machine", "single_web_server", "load_balanced_tier"])
def test_azure_compute_recipes_expose_version_and_replacement_guidance(workload):
    recipe = WizardConfig(provider="azure", project_name="version-test", architecture_type=workload)
    question = next(item for item in input_contract(recipe) if item["name"] == "image_version")
    assert question["default"] == "latest"
    assert "replace" in question["description"] and "destroy" in question["description"]


@pytest.mark.parametrize(
    "provider,workload",
    [
        ("aws", "static_site"),
        ("gcp", "static_site"),
        ("azure", "static_site"),
        ("azure", "secure_database"),
    ],
)
def test_version_input_is_not_exposed_outside_azure_compute(provider, workload):
    recipe = WizardConfig(
        provider=provider, project_name="version-test", architecture_type=workload
    )
    assert not any(item["name"] == "image_version" for item in input_contract(recipe))
