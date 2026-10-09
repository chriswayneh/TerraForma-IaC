import pytest
from fastapi.testclient import TestClient

from terraforma.generator import WizardConfig
from terraforma.project import ProjectSpecification, compile_project, input_contract
from terraforma.web import create_app
from tests.hcl_text import unaligned


@pytest.mark.parametrize(
    "provider,reference",
    [
        ("aws", "count = var.instance_count"),
        ("azure", "instances = var.instance_count"),
        ("gcp", "target_size = var.instance_count"),
    ],
)
def test_capacity_question_flows_through_compilation_and_browser(provider, reference):
    config = WizardConfig(
        provider=provider, project_name="capacity-test", architecture_type="load_balanced_tier"
    )
    fields = input_contract(config)
    count = next(item for item in fields if item["name"] == "instance_count")
    assert (count["default"], count["minimum"], count["maximum"]) == (2, 2, 20)
    inputs = {
        "aws": {"aws_account_id": "123456789012"},
        "azure": {
            "subscription_id": "12345678-1234-1234-1234-123456789abc",
            "ssh_public_key": "ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAIAEBAQEBAQEBAQEBAQEBAQEBAQEBAQEBAQEBAQEBAQEB",
        },
        "gcp": {"gcp_project_id": "example-project"},
    }[provider]
    specification = ProjectSpecification(recipe=config, inputs={**inputs, "instance_count": 4})
    result = compile_project(specification)
    assert reference in unaligned(result["files"]["main.tf"])
    assert "default = 4" in unaligned(result["files"]["variables.tf"])
    if provider == "aws":
        assert unaligned(result["files"]["main.tf"]).count(reference) == 2
    with TestClient(create_app(), base_url="http://127.0.0.1") as client:
        token = client.get("/api/session").json()["token"]
        response = client.post(
            "/api/generate",
            headers={"X-TerraForma-Token": token},
            json=specification.model_dump(),
        )
        assert response.status_code == 200, response.text
        assert response.json()["files"] == result["files"]
        assert "two web servers" not in str(response.json().get("guide", {})).lower()


@pytest.mark.parametrize("value", [0, 1, 21, "4", True, 2.5])
def test_capacity_rejects_unsupported_counts(value):
    with pytest.raises((ValueError, TypeError)):
        compile_project(
            ProjectSpecification(
                recipe=WizardConfig(
                    provider="aws",
                    project_name="capacity-test",
                    architecture_type="load_balanced_tier",
                ),
                inputs={"aws_account_id": "123456789012", "instance_count": value},
            )
        )


@pytest.mark.parametrize("provider", ["aws", "azure", "gcp"])
def test_single_server_has_no_capacity_question(provider):
    config = WizardConfig(
        provider=provider, project_name="capacity-test", architecture_type="single_web_server"
    )
    assert "instance_count" not in {field["name"] for field in input_contract(config)}
