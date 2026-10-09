import io
import json
import zipfile
from unittest.mock import Mock

import pytest
from fastapi.testclient import TestClient

from terraforma.cli import collect_recipe_inputs
from terraforma.generator import WizardConfig
from terraforma.project import (
    ProjectInputError,
    ProjectSpecification,
    compile_project,
    input_contract,
)
from terraforma.web import create_app
from tests.hcl_text import unaligned

KEY = "ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAIAEBAQEBAQEBAQEBAQEBAQEBAQEBAQEBAQEBAQEBAQEB"
REFERENCES = {
    "aws": "vm-workload-profile",
    "gcp": "vm-workload@example-project.iam.gserviceaccount.com",
}


def identity_spec(provider, enabled, **answers):
    inputs = {
        "aws": {"aws_account_id": "123456789012", "ssh_public_key": KEY},
        "azure": {"subscription_id": "12345678-1234-1234-1234-123456789abc", "ssh_public_key": KEY},
        "gcp": {"gcp_project_id": "example-project"},
    }[provider]
    if enabled and provider in REFERENCES:
        inputs["workload_identity"] = REFERENCES[provider]
    return ProjectSpecification(
        recipe=WizardConfig(
            provider=provider, project_name="identity-test", architecture_type="virtual_machine"
        ),
        inputs={**inputs, "enable_workload_identity": enabled, **answers},
    )


@pytest.mark.parametrize("provider", ["aws", "azure", "gcp"])
@pytest.mark.parametrize("enabled", [True, False])
def test_identity_output_export_import_and_guide(provider, enabled):
    spec = identity_spec(provider, enabled)
    compiled = compile_project(spec)
    main = compiled["files"]["main.tf"]
    assert "var.enable_workload_identity" in main
    assert not any(
        f'resource "{kind}"' in main
        for kind in (
            "aws_iam_role",
            "aws_iam_policy",
            "azurerm_role_assignment",
            "google_service_account_key",
            "google_project_iam_member",
            "google_service_account",
        )
    )
    if provider == "gcp":
        assert 'scopes = ["cloud-platform"]' in unaligned(main)
        assert "allow_stopping_for_update = false" in unaligned(main)
    if provider == "azure":
        assert (
            'type = var.workload_identity_type == "existing_user_assigned" ? "UserAssigned" : "SystemAssigned"'
            in unaligned(main)
        )
        assert 'output "managed_identity_principal_id"' in compiled["files"]["outputs.tf"]
    summary = {item["name"] for item in compiled["choice_summary"]}
    assert ("workload_identity" in summary) is (enabled and provider != "azure")
    with TestClient(create_app(), base_url="http://127.0.0.1") as client:
        headers = {"X-TerraForma-Token": client.get("/api/session").json()["token"]}
        generated = client.post("/api/generate", headers=headers, json=spec.model_dump())
        assert generated.status_code == 200
        assert (
            any(
                item["name"] == "Workload identity"
                for item in generated.json()["guide"]["components"]
            )
            is enabled
        )
        exported = client.post("/api/download", headers=headers, json=spec.model_dump())
        assert exported.status_code == 200
        with zipfile.ZipFile(io.BytesIO(exported.content)) as archive:
            manifest = archive.read("terraforma.project.json")
            assert json.loads(manifest)["inputs"] == spec.inputs
        imported = client.post("/api/projects/import", headers=headers, content=manifest)
        assert imported.status_code == 200
        assert imported.json()["files"] == compiled["files"]


@pytest.mark.parametrize("provider", ["aws", "gcp"])
def test_enabled_identity_requires_existing_reference(provider):
    spec = identity_spec(provider, True)
    del spec.inputs["workload_identity"]
    with pytest.raises(ProjectInputError) as error:
        compile_project(spec)
    assert error.value.field == "workload_identity"


@pytest.mark.parametrize(
    "provider,value",
    [
        ("aws", "arn:aws:iam::123456789012:role/private-role"),
        ("aws", "a" * 129),
        ("aws", "private profile"),
        ("aws", "-----BEGIN PRIVATE KEY-----"),
        ("gcp", "123456789012-compute@developer.gserviceaccount.com"),
        ("gcp", "vm-workload@example-project.example.com"),
        ("gcp", "default"),
        ("gcp", "not-a-credential-private-value"),
        ("aws", ""),
        ("gcp", ""),
    ],
)
def test_invalid_references_fail_without_echoing_values(provider, value):
    with pytest.raises(ProjectInputError) as error:
        compile_project(identity_spec(provider, True, workload_identity=value))
    if value:
        assert value not in str(error.value)


@pytest.mark.parametrize("provider", ["aws", "azure", "gcp"])
@pytest.mark.parametrize("enabled", [True, False])
def test_terminal_collects_only_active_identity_reference(provider, enabled, monkeypatch):
    spec = identity_spec(provider, enabled)
    definitions = input_contract(spec.recipe)
    prompted = []

    def prompt(message, **kwargs):
        definition = next(
            item for item in definitions if message in {item["label"] + ":", item["label"] + "?"}
        )
        name = definition["name"]
        prompted.append(name)
        value = spec.inputs.get(name, definition["default"])
        if definition["kind"] == "integer":
            value = str(value)
        return Mock(ask=lambda: value)

    for name in ("text", "confirm", "select"):
        monkeypatch.setattr(f"terraforma.cli.questionary.{name}", prompt)
    result = collect_recipe_inputs(spec.recipe)
    assert ("workload_identity" in prompted) is (enabled and provider != "azure")
    assert result.inputs["enable_workload_identity"] is enabled
    compile_project(result)


@pytest.mark.parametrize("provider", ["aws", "azure", "gcp"])
def test_web_tier_does_not_offer_identity_control(provider):
    config = WizardConfig(
        provider=provider, project_name="identity-test", architecture_type="single_web_server"
    )
    assert "enable_workload_identity" not in {item["name"] for item in input_contract(config)}
