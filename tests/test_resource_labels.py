import json
import os
import shutil
import subprocess
from unittest.mock import Mock

import pytest
from fastapi.testclient import TestClient

from terraforma.cli import collect_recipe_inputs
from terraforma.generator import TerraformGenerator, WizardConfig
from terraforma.hcl import ref
from terraforma.project import ProjectInputError, compile_project, input_contract
from terraforma.resource_labels import LABEL_FIELDS, resource_labels
from terraforma.web import create_app
from tests.test_custom_images import specification
from tests.test_generator import assert_native_files

pytest_plugins = ["tests.test_generator"]

LABELS = {
    "owner_label": "platform-team",
    "application_label": "inventory-api",
    "cost_center_label": "cc-100",
}


def test_browser_contract_keeps_blank_labels_optional():
    fields = {
        field["name"]: field for field in input_contract(specification("aws", custom=False).recipe)
    }
    assert all(fields[name]["kind"] == "optional_label" for name in LABEL_FIELDS)


@pytest.mark.parametrize("provider", ["aws", "azure", "gcp"])
@pytest.mark.parametrize("windows", [False, True])
def test_label_inputs_roundtrip_without_cloud_operations(provider, windows, monkeypatch):
    monkeypatch.setattr(
        "subprocess.run", lambda *a, **k: pytest.fail("Label import must not execute tools.")
    )
    spec = specification(provider, windows, custom=False, **LABELS)
    result = compile_project(spec)
    assert all(name in result["files"]["main.tf"] for name in LABELS)
    assert {
        field["name"]: field["value"] for field in result["choice_summary"]
    }.items() >= LABELS.items()
    with TestClient(create_app(), base_url="http://127.0.0.1") as client:
        headers = {"X-TerraForma-Token": client.get("/api/session").json()["token"]}
        response = client.post(
            "/api/projects/import", headers=headers, content=spec.model_dump_json()
        )
    assert response.status_code == 200, response.text
    assert response.json()["specification"]["inputs"] == spec.inputs


@pytest.mark.parametrize("name", list(LABEL_FIELDS))
@pytest.mark.parametrize(
    "value",
    [
        "Uppercase",
        " space",
        "a" * 64,
        "${secret-marker}",
        "secret\nmarker",
        "-----BEGIN PRIVATE KEY-----",
    ],
)
def test_labels_reject_unsupported_and_unsafe_values_without_echo(name, value):
    with pytest.raises(ProjectInputError) as error:
        compile_project(specification("gcp", custom=False, **{name: value}))
    assert error.value.field == name
    assert value not in str(error.value)
    assert "secret-marker" not in str(error.value)


@pytest.mark.parametrize("provider", ["aws", "azure", "gcp"])
@pytest.mark.parametrize(
    "workload", ["single_web_server", "load_balanced_tier", "secure_database", "static_site"]
)
def test_label_inputs_do_not_expand_recipe_scope(provider, workload):
    recipe = WizardConfig(provider=provider, project_name="example", architecture_type=workload)
    assert not set(LABEL_FIELDS) & {field["name"] for field in input_contract(recipe)}


@pytest.mark.parametrize("provider", ["aws", "azure", "gcp"])
@pytest.mark.parametrize("windows", [False, True])
def test_terminal_collects_optional_labels(provider, windows, monkeypatch):
    spec = specification(provider, windows, custom=False, **LABELS)
    fields = {field["label"]: field for field in input_contract(spec.recipe)}
    asked = []

    def prompt(message, **options):
        field = fields[message.rstrip("?:")]
        asked.append(field["name"])
        answer = spec.inputs.get(field["name"], field["default"])
        return Mock(ask=lambda: str(answer) if field["kind"] == "integer" else answer)

    for kind in ("text", "confirm", "select"):
        monkeypatch.setattr(f"terraforma.cli.questionary.{kind}", prompt)
    result = compile_project(collect_recipe_inputs(spec.recipe))
    assert set(LABEL_FIELDS) <= set(asked)
    assert result["specification"]["inputs"].items() >= LABELS.items()


@pytest.mark.parametrize("provider", ["aws", "azure", "gcp"])
@pytest.mark.parametrize("windows", [False, True])
@pytest.mark.parametrize("public", [False, True])
def test_native_label_combinations(native_directories, provider, windows, public):
    assert_native_files(
        native_directories[provider],
        compile_project(
            specification(
                provider, windows, custom=False, public=public, enable_data_disk=True, **LABELS
            )
        )["files"],
    )


@pytest.mark.parametrize(
    "values",
    [
        LABELS,
        {name: "" for name in LABEL_FIELDS},
        {"owner_label": "platform-team", "application_label": "", "cost_center_label": ""},
    ],
)
def test_native_label_map_omits_blank_values_and_preserves_environment(tmp_path, values):
    if os.environ.get("TERRAFORMA_NATIVE_TESTS") != "1":
        pytest.skip("Set TERRAFORMA_NATIVE_TESTS=1 to run native checks.")
    executable = shutil.which("terraform")
    assert executable, "Native tests require Terraform on PATH."
    generator = TerraformGenerator(
        WizardConfig(provider="gcp", project_name="example", architecture_type="virtual_machine")
    )
    generator.generate()
    variables = [
        item.render()
        for item in generator.variables
        if item.labels[0] in {*LABEL_FIELDS, "environment"}
    ]
    expression = resource_labels(
        {"environment": ref("var.environment"), "managed_by": "terraforma"}
    ).value
    (tmp_path / "main.tf").write_text(
        "\n".join(variables) + f"\nlocals {{ labels = {expression} }}\n", encoding="utf-8"
    )
    (tmp_path / "terraform.tfvars.json").write_text(json.dumps(values), encoding="utf-8")
    environment = {
        key: value
        for key, value in os.environ.items()
        if not key.startswith(("TF_VAR_", "TF_CLI_ARGS"))
    }
    result = subprocess.run(
        [executable, "console", "-no-color"],
        cwd=tmp_path,
        env=environment,
        input="jsonencode(local.labels)\n",
        capture_output=True,
        text=True,
        timeout=15,
        check=False,
    )
    assert result.returncode == 0, result.stderr
    expected = {LABEL_FIELDS[name][0]: value for name, value in values.items() if value}
    assert json.loads(json.loads(result.stdout)) == {
        "environment": "development",
        "managed_by": "terraforma",
        **expected,
    }
