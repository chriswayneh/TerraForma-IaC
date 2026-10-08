import io
import json
import zipfile
from unittest.mock import Mock

import pytest
from fastapi.testclient import TestClient

from terraforma.catalog import recipe_capabilities
from terraforma.generator import WizardConfig
from terraforma.project import (
    ProjectInputError,
    ProjectSpecification,
    compile_project,
    input_contract,
)
from terraforma.web import create_app
from tests.test_generator import assert_native_files
from tests.test_virtual_machine import KEY
from tests.test_windows_vm import RSA_KEY

pytest_plugins = ["tests.test_generator"]

IMAGES = {
    "aws": "ami-0123456789abcdef0",
    "azure": "/subscriptions/00000000-0000-0000-0000-000000000001/resourceGroups/image-library/providers/Microsoft.Compute/images/approved-image",
    "gcp": "projects/image-library/global/images/approved-image",
}


def specification(provider, windows=False, custom=True, public=False, **changes):
    inputs = {
        "aws": {"aws_account_id": "123456789012", "ssh_public_key": RSA_KEY if windows else KEY},
        "azure": {
            "subscription_id": "00000000-0000-0000-0000-000000000001",
            **({} if windows else {"ssh_public_key": KEY}),
        },
        "gcp": {"gcp_project_id": "example-project"},
    }[provider]
    if public:
        inputs["allowed_cidr"] = "203.0.113.8/32"
    if custom:
        inputs.update(
            use_custom_image=True,
            custom_image=IMAGES[provider],
            confirm_custom_image_compatibility=True,
        )
        if provider == "aws":
            inputs["custom_image_owner_account_id"] = "123456789012"
            if not windows:
                inputs["custom_image_admin_username"] = "image-operator"
    return ProjectSpecification(
        recipe=WizardConfig(
            provider=provider,
            project_name="custom-vm",
            architecture_type="windows_virtual_machine" if windows else "virtual_machine",
            is_public=public,
        ),
        inputs={**inputs, **changes},
    )


@pytest.mark.parametrize("provider", list(IMAGES))
@pytest.mark.parametrize("windows", [False, True])
def test_custom_image_contract_and_provider_selection(provider, windows):
    spec = specification(provider, windows)
    result = compile_project(spec)
    fields = {item["name"]: item for item in input_contract(spec.recipe)}
    assert fields["custom_image"]["required_when"] == {"use_custom_image": True}
    assert fields["os_image"]["visible_when"] == {"use_custom_image": False}
    assert fields["image_version"]["visible_when"] == {"use_custom_image": False}
    assert result["specification"]["inputs"]["custom_image"] == IMAGES[provider]
    assert recipe_capabilities(spec.recipe)["custom_image_generation"] == "supported_unverified"
    main = result["files"]["main.tf"]
    assert "var.confirm_custom_image_compatibility" in main
    if provider == "aws":
        assert "data.aws_ami.custom[0].id" in main
        assert "owners = [var.custom_image_owner_account_id]" in main
        assert 'name = "is-public"' in main and 'values = ["false"]' in main
        assert "length(self.product_codes) == 0" in main
    elif provider == "azure":
        assert "source_image_id = var.use_custom_image ? var.custom_image : null" in main
        assert 'dynamic "source_image_reference"' in main
        assert "for_each = var.use_custom_image ? [] : [1]" in main
    else:
        assert "image = var.use_custom_image ? var.custom_image :" in main


@pytest.mark.parametrize("provider", list(IMAGES))
@pytest.mark.parametrize(
    "changes,field",
    [
        ({"custom_image": ""}, "custom_image"),
        ({"custom_image": "https://private-token/image"}, "custom_image"),
        ({"confirm_custom_image_compatibility": False}, "confirm_custom_image_compatibility"),
        ({"use_custom_image": False}, "custom_image"),
        ({"image_version": "ami-0123456789abcdef0"}, "use_custom_image"),
    ],
)
def test_invalid_or_stale_custom_image_choices_fail_closed(provider, changes, field):
    if "image_version" in changes and provider != "aws":
        changes = {"os_image": "ubuntu-24.04"}
    with pytest.raises(ProjectInputError) as error:
        compile_project(specification(provider, **changes))
    assert error.value.field == field
    assert "private-token" not in str(error.value)


@pytest.mark.parametrize(
    "field,value",
    [
        ("custom_image_owner_account_id", ""),
        ("custom_image_owner_account_id", "private-owner"),
        ("custom_image_admin_username", ""),
        ("custom_image_admin_username", "root"),
    ],
)
def test_aws_requires_exact_owner_and_nonroot_connection_reference(field, value):
    with pytest.raises(ProjectInputError) as error:
        compile_project(specification("aws", **{field: value}))
    assert error.value.field == field
    assert "private-owner" not in str(error.value)


@pytest.mark.parametrize("provider", list(IMAGES))
def test_browser_export_import_preserves_custom_image_without_execution(provider, monkeypatch):
    monkeypatch.setattr(
        "subprocess.run", lambda *a, **k: pytest.fail("Offline workflow must not execute tools.")
    )
    spec = specification(provider)
    with TestClient(create_app(), base_url="http://127.0.0.1") as client:
        headers = {"X-TerraForma-Token": client.get("/api/session").json()["token"]}
        exported = client.post("/api/download", headers=headers, json=spec.model_dump())
        assert exported.status_code == 200, exported.text
        with zipfile.ZipFile(io.BytesIO(exported.content)) as archive:
            manifest = archive.read("terraforma.project.json")
        assert json.loads(manifest)["inputs"]["custom_image"] == IMAGES[provider]
        imported = client.post("/api/projects/import", headers=headers, content=manifest)
        assert imported.status_code == 200
        assert imported.json()["specification"] == spec.model_dump()
        assert imported.json()["target"]["identity_verified"] is False


@pytest.mark.parametrize("provider", list(IMAGES))
@pytest.mark.parametrize("windows", [False, True])
def test_terminal_custom_image_questions_match_generated_inputs(provider, windows, monkeypatch):
    from terraforma.cli import collect_recipe_inputs

    spec = specification(provider, windows)
    definitions = {item["label"]: item for item in input_contract(spec.recipe)}
    asked = []

    def prompt(message, **options):
        definition = definitions[message.rstrip("?:")]
        asked.append(definition["name"])
        answer = spec.inputs.get(definition["name"], definition["default"])
        return Mock(ask=lambda: str(answer) if definition["kind"] == "integer" else answer)

    for kind in ("text", "select", "confirm"):
        monkeypatch.setattr(f"terraforma.cli.questionary.{kind}", prompt)
    collected = collect_recipe_inputs(spec.recipe)
    assert "os_image" not in asked and "image_version" not in asked
    result = compile_project(collected)
    assert result["specification"]["inputs"]["custom_image"] == IMAGES[provider]
    assert "var.confirm_custom_image_compatibility" in result["files"]["main.tf"]


@pytest.mark.parametrize("provider", list(IMAGES))
@pytest.mark.parametrize("windows", [False, True])
@pytest.mark.parametrize("custom", [False, True])
@pytest.mark.parametrize("public", [False, True])
def test_native_custom_and_catalog_images(native_directories, provider, windows, custom, public):
    assert_native_files(
        native_directories[provider],
        compile_project(specification(provider, windows, custom, public))["files"],
    )
