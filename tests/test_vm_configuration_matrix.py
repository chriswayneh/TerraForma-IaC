import io
import json
import zipfile
from unittest.mock import Mock

import hcl2
import pytest
from fastapi.testclient import TestClient

from terraforma.cli import collect_recipe_inputs
from terraforma.generator import TerraformGenerator
from terraforma.hcl import value_hcl
from terraforma.project import compile_project, input_contract
from terraforma.web import create_app
from tests.test_aws_existing_subnet import subnet_spec as aws_subnet_spec
from tests.test_azure_existing_subnet import subnet_spec as azure_subnet_spec
from tests.test_azure_managed_identity import IDENTITY
from tests.test_custom_images import specification
from tests.test_gcp_existing_subnet import subnet_spec as gcp_subnet_spec
from tests.test_generator import assert_native_files
from tests.test_initialization import POWERSHELL, SHELL
from tests.test_resource_labels import LABELS

pytest_plugins = ["tests.test_generator"]


def combined_spec(provider, windows, public, existing, outbound_profile="unrestricted"):
    spec = (
        {"aws": aws_subnet_spec, "azure": azure_subnet_spec, "gcp": gcp_subnet_spec}[provider](
            windows=windows, public=public, custom=True
        )
        if existing
        else specification(provider, windows, custom=True, public=public)
    )
    spec.inputs.update(
        enable_data_disk=True,
        enable_workload_identity=True,
        enable_initialization=True,
        initialization_script=POWERSHELL if windows else SHELL,
        confirm_initialization_review=True,
        **LABELS,
    )
    if not existing:
        spec.inputs["outbound_access"] = outbound_profile
    if provider == "aws":
        spec.inputs["instance_tenancy"] = "dedicated"
    if provider == "azure":
        spec.inputs.update(
            workload_identity_type="existing_user_assigned",
            workload_identity_resource_id=IDENTITY,
        )
    else:
        spec.inputs["workload_identity"] = (
            "vm-operator"
            if provider == "aws"
            else "vm-operator@example-project.iam.gserviceaccount.com"
        )
    return spec


@pytest.mark.parametrize("provider", ["aws", "azure", "gcp"])
@pytest.mark.parametrize("windows", [False, True])
@pytest.mark.parametrize("public", [False, True])
@pytest.mark.parametrize("network", ["new_unrestricted", "new_restricted", "existing"])
def test_combined_inputs_export_and_import_without_missing_variables(
    provider, windows, public, network, monkeypatch
):
    monkeypatch.setattr(
        "subprocess.run", lambda *a, **k: pytest.fail("Export/import must remain offline.")
    )
    spec = combined_spec(
        provider,
        windows,
        public,
        network == "existing",
        "https_dns" if network == "new_restricted" else "unrestricted",
    )
    compiled = compile_project(spec)
    generator = TerraformGenerator(spec.recipe)
    generator.generate()
    variables = {variable.labels[0]: variable for variable in generator.variables}
    exported_variables = {
        name.strip('"'): attributes
        for entry in hcl2.loads(compiled["files"]["variables.tf"])["variable"]
        for name, attributes in entry.items()
    }
    contract = {field["name"]: field for field in input_contract(spec.recipe)}
    assert set(contract) == set(variables)
    assert len(spec.inputs) <= 48
    for name, value in spec.inputs.items():
        assert name in variables
        expected = value_hcl(value) if isinstance(value, str) else value
        assert exported_variables[name]["default"] == expected
    for name, field in contract.items():
        assert name in spec.inputs or field["default"] is not None or field["sensitive"]
        if field["sensitive"]:
            assert name not in spec.inputs
            assert (
                field["environment_variable"] in compiled["required_secret_environment_variables"]
            )
    with TestClient(create_app(), base_url="http://127.0.0.1") as client:
        headers = {"X-TerraForma-Token": client.get("/api/session").json()["token"]}
        exported = client.post("/api/download", headers=headers, json=spec.model_dump())
        assert exported.status_code == 200, exported.text
        with zipfile.ZipFile(io.BytesIO(exported.content)) as archive:
            manifest = archive.read("terraforma.project.json")
        imported = client.post("/api/projects/import", headers=headers, content=manifest)
    assert imported.status_code == 200, imported.text
    assert imported.json()["specification"]["inputs"] == spec.inputs
    assert imported.json()["files"] == compiled["files"]
    assert imported.json()["target"]["identity_verified"] is False
    assert "review-marker" not in json.dumps(imported.json()["choice_summary"])


@pytest.mark.parametrize("provider", ["aws", "azure", "gcp"])
@pytest.mark.parametrize("windows", [False, True])
@pytest.mark.parametrize("public", [False, True])
@pytest.mark.parametrize("network", ["new_unrestricted", "new_restricted", "existing"])
def test_native_combined_configuration(native_directories, provider, windows, public, network):
    assert_native_files(
        native_directories[provider],
        compile_project(
            combined_spec(
                provider,
                windows,
                public,
                network == "existing",
                "https_dns" if network == "new_restricted" else "unrestricted",
            )
        )["files"],
    )


@pytest.mark.parametrize("provider", ["aws", "azure", "gcp"])
@pytest.mark.parametrize("windows", [False, True])
@pytest.mark.parametrize("network", ["new_unrestricted", "new_restricted", "existing"])
def test_terminal_collects_combined_options_without_editing_hcl(
    provider, windows, network, monkeypatch, tmp_path
):
    spec = combined_spec(
        provider,
        windows,
        False,
        network == "existing",
        "https_dns" if network == "new_restricted" else "unrestricted",
    )
    script = tmp_path / ("reviewed.ps1" if windows else "reviewed.sh")
    script.write_text(spec.inputs["initialization_script"], encoding="utf-8", newline="")
    fields = {field["label"]: field for field in input_contract(spec.recipe)}
    asked = []

    def prompt(message, **options):
        if message == "Trusted initialization file path:":
            return Mock(ask=lambda: str(script))
        field = fields[message.rstrip("?:")]
        asked.append(field["name"])
        answer = spec.inputs.get(field["name"], field["default"])
        return Mock(ask=lambda: str(answer) if field["kind"] == "integer" else answer)

    for kind in ("text", "confirm", "select"):
        monkeypatch.setattr(f"terraforma.cli.questionary.{kind}", prompt)
    monkeypatch.setattr(
        "subprocess.run",
        lambda *a, **k: pytest.fail("Terminal collection must not invoke cloud or guest commands."),
    )
    collected = collect_recipe_inputs(spec.recipe)
    assert len(collected.inputs) <= 48
    for name, value in spec.inputs.items():
        assert collected.inputs[name] == value
    assert "confirm_initialization_review" in asked
    assert ("outbound_access" in asked) is (network != "existing")
    compiled = compile_project(collected)
    assert compiled["required_secret_environment_variables"] == (
        ["TF_VAR_admin_password"] if provider == "azure" and windows else []
    )
