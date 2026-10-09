import itertools
import shutil
import subprocess
from unittest.mock import Mock

import pytest
from fastapi.testclient import TestClient

from terraforma.cli import collect_recipe_inputs
from terraforma.generator import TerraformGenerator, WizardConfig
from terraforma.project import ProjectInputError, compile_project, input_contract
from terraforma.web import create_app
from tests.test_aws_placement import specification
from tests.test_generator import assert_native_files

pytest_plugins = ["tests.test_generator"]


@pytest.mark.parametrize("windows", [False, True])
@pytest.mark.parametrize("mode", ["standard", "unlimited"])
def test_terminal_collects_t8i_explicit_credits(windows, mode, monkeypatch):
    project = specification(windows, instance_type="t8i.small", cpu_credit_mode=mode)
    fields = {field["label"]: field for field in input_contract(project.recipe)}

    def prompt(message, **options):
        field = fields[message.rstrip("?:")]
        answer = project.inputs.get(field["name"], field["default"])
        return Mock(ask=lambda: str(answer) if field["kind"] == "integer" else answer)

    for kind in ("text", "confirm", "select"):
        monkeypatch.setattr(f"terraforma.cli.questionary.{kind}", prompt)
    collected = collect_recipe_inputs(project.recipe)
    assert collected.inputs["instance_type"] == "t8i.small"
    assert collected.inputs["cpu_credit_mode"] == mode
    assert compile_project(collected)["files"]["main.tf"]


@pytest.mark.parametrize(
    "windows,mode",
    list(itertools.product([False, True], ["provider_default", "standard", "unlimited"])),
)
def test_credit_choice_survives_generation_and_summary(windows, mode):
    project = specification(windows, cpu_credit_mode=mode)
    output = compile_project(project)
    definition = next(
        field for field in input_contract(project.recipe) if field["name"] == "cpu_credit_mode"
    )
    assert definition["label"] == "CPU credit mode"
    assert definition["choices"] == ["provider_default", "standard", "unlimited"]
    assert output["specification"]["inputs"]["cpu_credit_mode"] == mode
    assert f'default = "{mode}"' in output["files"]["variables.tf"]
    assert 'dynamic "credit_specification"' in output["files"]["main.tf"]
    assert (
        'var.cpu_credit_mode == "provider_default" ? [] : [var.cpu_credit_mode]'
        in output["files"]["main.tf"]
    )
    assert "cpu_credits = credit_specification.value" in output["files"]["main.tf"]
    assert "Explicit CPU credit modes are supported only" in output["files"]["main.tf"]


@pytest.mark.parametrize(
    "family,mode",
    list(
        itertools.product(
            ["t2.micro", "t3.micro", "t3a.small", "t8i.small"], ["standard", "unlimited"]
        )
    ),
)
def test_supported_burstable_families_accept_explicit_modes(family, mode):
    compile_project(specification(False, instance_type=family, cpu_credit_mode=mode))


@pytest.mark.parametrize(
    "family,mode",
    list(
        itertools.product(
            ["m5.large", "t4g.small", "t3ax.large", "t8ix.small"], ["standard", "unlimited"]
        )
    ),
)
def test_other_families_reject_explicit_modes_before_generation(family, mode):
    with pytest.raises(ProjectInputError) as error:
        compile_project(specification(False, instance_type=family, cpu_credit_mode=mode))
    assert error.value.field == ("instance_type" if family == "t4g.small" else "cpu_credit_mode")


def test_default_keeps_credit_setting_unmanaged_for_non_burstable_instances():
    output = compile_project(specification(False, instance_type="m5.large"))
    choice = next(row for row in output["choice_summary"] if row["name"] == "cpu_credit_mode")
    assert choice["value"] == "Provider default (credit setting unmanaged)"
    assert choice["source"] == "default"


@pytest.mark.parametrize(
    "provider,workload",
    list(
        itertools.product(
            ["aws", "azure", "gcp"],
            ["single_web_server", "load_balanced_tier", "secure_database", "static_site"],
        )
    ),
)
def test_unrelated_recipes_have_no_credit_question_or_block(provider, workload):
    recipe = WizardConfig(provider=provider, project_name="credit-test", architecture_type=workload)
    assert all(field["name"] != "cpu_credit_mode" for field in input_contract(recipe))
    assert "credit_specification" not in TerraformGenerator(recipe).generate()["main.tf"]


def test_api_import_preserves_credit_answer_and_rejects_incompatible_size():
    project = specification(True, cpu_credit_mode="standard").model_dump()
    with TestClient(create_app(), base_url="http://127.0.0.1") as client:
        headers = {"X-TerraForma-Token": client.get("/api/session").json()["token"]}
        response = client.post("/api/projects/import", headers=headers, json=project)
        assert response.status_code == 200
        assert response.json()["specification"]["inputs"]["cpu_credit_mode"] == "standard"
        project["inputs"]["instance_type"] = "m5.large"
        response = client.post("/api/projects/compile", headers=headers, json=project)
        assert response.status_code == 422


@pytest.mark.parametrize("windows", [False, True])
@pytest.mark.parametrize("tenancy", ["provider_default", "dedicated"])
@pytest.mark.parametrize("mode", ["provider_default", "standard", "unlimited"])
def test_native_t8i_credit_configuration(native_directories, windows, tenancy, mode):
    project = specification(
        windows, instance_type="t8i.small", instance_tenancy=tenancy, cpu_credit_mode=mode
    )
    assert_native_files(native_directories["aws"], compile_project(project)["files"])


@pytest.mark.parametrize("windows", [False, True])
def test_mocked_t8i_credit_modes_and_non_burstable_guard(native_directories, windows):
    directory = native_directories["aws"]
    project = specification(
        windows, instance_type="t8i.small", instance_tenancy="dedicated", cpu_credit_mode="standard"
    )
    assert_native_files(directory, compile_project(project)["files"])
    tests = directory / "credit-tests"
    tests.mkdir(exist_ok=True)
    (tests / "credits.tftest.hcl").write_text(
        """
mock_provider "aws" {
  alias = "offline"
  override_during = plan
  mock_data "aws_availability_zones" { defaults = { names = ["us-east-1a", "us-east-1b"] } }
  mock_data "aws_ami" { defaults = { id = "ami-0123456789abcdef0" } }
}
run "explicit_standard" {
  command = plan
  providers = { aws = aws.offline }
  assert {
    condition = aws_instance.web[0].instance_type == "t8i.small" && aws_instance.web[0].tenancy == "dedicated" && length(aws_instance.web[0].credit_specification) == 1 && aws_instance.web[0].credit_specification[0].cpu_credits == "standard"
    error_message = "The T8i instance must preserve explicitly selected standard credits."
  }
}
run "explicit_unlimited" {
  command = plan
  providers = { aws = aws.offline }
  variables { cpu_credit_mode = "unlimited" }
  assert {
    condition = length(aws_instance.web[0].credit_specification) == 1 && aws_instance.web[0].credit_specification[0].cpu_credits == "unlimited"
    error_message = "The T8i instance must preserve explicitly selected unlimited credits."
  }
}
run "reject_non_burstable_override" {
  command = plan
  providers = { aws = aws.offline }
  variables { instance_type = "m5.large" }
  expect_failures = [aws_instance.web]
}
""",
        encoding="utf-8",
    )
    result = subprocess.run(
        [shutil.which("terraform"), "test", "-test-directory=credit-tests", "-no-color"],
        cwd=directory,
        capture_output=True,
        text=True,
        timeout=60,
        check=False,
    )
    assert result.returncode == 0, result.stdout + result.stderr
