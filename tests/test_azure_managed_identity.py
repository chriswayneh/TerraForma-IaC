import json
from unittest.mock import Mock

import pytest
from fastapi.testclient import TestClient

from terraforma.cli import collect_recipe_inputs
from terraforma.project import ProjectInputError, compile_project, input_contract
from terraforma.web import create_app
from tests.test_custom_images import specification
from tests.test_generator import assert_native_files

pytest_plugins = ["tests.test_generator"]

IDENTITY = "/subscriptions/00000000-0000-0000-0000-000000000001/resourceGroups/workload-identities/providers/Microsoft.ManagedIdentity/userAssignedIdentities/vm-operator"


def identity_spec(windows=False, public=False, mode="existing_user_assigned", **changes):
    return specification(
        "azure",
        windows=windows,
        custom=False,
        public=public,
        enable_workload_identity=mode != "disabled",
        workload_identity_type="system_assigned" if mode == "disabled" else mode,
        workload_identity_resource_id=IDENTITY if mode == "existing_user_assigned" else "",
        **changes,
    )


@pytest.mark.parametrize("windows", [False, True])
@pytest.mark.parametrize("mode", ["disabled", "system_assigned", "existing_user_assigned"])
def test_identity_mode_contract_preserves_lifecycle_and_no_grants(windows, mode):
    spec = identity_spec(windows, mode=mode)
    result = compile_project(spec)
    main = result["files"]["main.tf"]
    assert (
        'identity_ids = var.workload_identity_type == "existing_user_assigned" ? [var.workload_identity_resource_id] : null'
        in main
    )
    assert (
        'try(lower(split("/", var.workload_identity_resource_id)[2]), "") == lower(var.subscription_id)'
        in main
    )
    assert 'resource "azurerm_user_assigned_identity"' not in main
    assert 'resource "azurerm_role_assignment"' not in main
    assert 'data "azurerm_user_assigned_identity"' not in main
    assert 'var.workload_identity_type == "system_assigned"' in result["files"]["outputs.tf"]
    fields = {field["name"]: field for field in input_contract(spec.recipe)}
    assert fields["workload_identity_resource_id"]["required_when"] == {
        "enable_workload_identity": True,
        "workload_identity_type": "existing_user_assigned",
    }


@pytest.mark.parametrize(
    "changes,field",
    [
        ({"workload_identity_resource_id": ""}, "workload_identity_resource_id"),
        ({"workload_identity_resource_id": "secret-marker"}, "workload_identity_resource_id"),
        (
            {"workload_identity_resource_id": IDENTITY.replace("000000000001", "000000000002")},
            "workload_identity_resource_id",
        ),
        ({"enable_workload_identity": False}, "enable_workload_identity"),
        ({"workload_identity_type": "system_assigned"}, "workload_identity_resource_id"),
        ({"workload_identity_type": "SystemAssigned, UserAssigned"}, "workload_identity_type"),
    ],
)
def test_invalid_inactive_and_cross_subscription_references_fail_closed(changes, field):
    spec = identity_spec()
    spec.inputs.update(changes)
    with pytest.raises(ProjectInputError) as error:
        compile_project(spec)
    assert error.value.field == field
    assert "secret-marker" not in str(error.value)
    assert IDENTITY not in str(error.value)


@pytest.mark.parametrize("windows", [False, True])
def test_api_import_explains_existing_identity_without_execution(windows, monkeypatch):
    monkeypatch.setattr(
        "subprocess.run", lambda *a, **k: pytest.fail("Offline import must not run tools.")
    )
    spec = identity_spec(windows)
    with TestClient(create_app(), base_url="http://127.0.0.1") as client:
        headers = {"X-TerraForma-Token": client.get("/api/session").json()["token"]}
        response = client.post("/api/projects/import", headers=headers, json=spec.model_dump())
    assert response.status_code == 200, response.text
    result = response.json()
    assert result["specification"]["inputs"]["workload_identity_resource_id"] == IDENTITY
    assert result["target"]["identity_verified"] is False
    assert "existing user-assigned" in json.dumps(result["guide"])


@pytest.mark.parametrize("windows", [False, True])
def test_terminal_collects_existing_identity_reference(windows, monkeypatch):
    spec = identity_spec(windows)
    fields = {field["label"]: field for field in input_contract(spec.recipe)}
    asked = []

    def prompt(message, **options):
        field = fields[message.rstrip("?:")]
        asked.append(field["name"])
        answer = spec.inputs.get(field["name"], field["default"])
        return Mock(ask=lambda: str(answer) if field["kind"] == "integer" else answer)

    for kind in ("confirm", "select", "text"):
        monkeypatch.setattr(f"terraforma.cli.questionary.{kind}", prompt)
    result = compile_project(collect_recipe_inputs(spec.recipe))
    assert "workload_identity_resource_id" in asked
    assert result["specification"]["inputs"]["workload_identity_resource_id"] == IDENTITY


@pytest.mark.parametrize("windows", [False, True])
@pytest.mark.parametrize("public", [False, True])
@pytest.mark.parametrize("mode", ["disabled", "system_assigned", "existing_user_assigned"])
def test_native_azure_identity_modes(native_directories, windows, public, mode):
    assert_native_files(
        native_directories["azure"], compile_project(identity_spec(windows, public, mode))["files"]
    )
