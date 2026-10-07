import json

import pytest
from click.testing import CliRunner
from fastapi.testclient import TestClient

from terraforma.catalog import recipe_capabilities, recipe_catalog
from terraforma.cli import main
from terraforma.generator import TerraformGenerator, WizardConfig
from terraforma.web import create_app


def test_catalog_lists_all_recipes_without_claiming_deployment():
    recipes = recipe_catalog()
    assert len(recipes) == 17
    assert len({recipe["id"] for recipe in recipes}) == 17
    windows = [item for item in recipes if "windows_virtual_machine" in item["id"]]
    assert len(windows) == 2
    assert {item["provider"] for item in windows} == {"aws", "gcp"}
    for recipe in recipes:
        assert recipe["workflow"] == "offline_generation"
        assert recipe["account_checks"] == recipe["deployment_checks"] == "unverified"
        assert "Automatic provisioning" in recipe["unsupported"]
        assert recipe["fixed_choices"] and recipe["preflight_required"]


@pytest.mark.parametrize(
    ("provider", "image", "description"),
    [
        ("aws", "al2023-ami-2023.*-x86_64", "Amazon Linux 2023"),
        ("azure", "22_04-lts-gen2", "Ubuntu 22.04"),
        ("gcp", "debian-cloud/debian-12", "Debian 12"),
    ],
)
def test_compute_capabilities_describe_actual_fixed_image(provider, image, description):
    for workload in ("single_web_server", "load_balanced_tier"):
        config = WizardConfig(provider=provider, project_name="example", architecture_type=workload)
        metadata = recipe_capabilities(config)
        assert image in TerraformGenerator(config).generate()["main.tf"]
        assert description in metadata["fixed_choices"][0]
        assert "Windows VMs" in metadata["unsupported"]
        assert "Data disks" in metadata["unsupported"]


def test_catalog_cli_and_api_match_and_do_not_read_credentials(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "catalog-secret-marker")
    result = CliRunner().invoke(main, ["catalog", "--json-output"])
    assert result.exit_code == 0
    with TestClient(create_app(), base_url="http://127.0.0.1") as client:
        response = client.get("/api/catalog")
        assert response.status_code == 200
        assert json.loads(result.output) == response.json()
        token = client.get("/api/session").json()["token"]
        contract = client.post(
            "/api/input-contract",
            headers={"X-TerraForma-Token": token},
            json={
                "provider": "aws",
                "project_name": "example",
                "architecture_type": "single_web_server",
            },
        )
        assert contract.json()["capabilities"]["id"] == "aws/single_web_server"
        assert "catalog-secret-marker" not in response.text + contract.text + result.output
