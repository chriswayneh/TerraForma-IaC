import shutil
import subprocess
from unittest.mock import Mock

import hcl2
import pytest
from fastapi.testclient import TestClient

from terraforma.aws_tenancy import aws_tenancy_guidance
from terraforma.cli import collect_recipe_inputs
from terraforma.generator import WizardConfig
from terraforma.preflight import target_preflight
from terraforma.project import ProjectInputError, compile_project, input_contract
from terraforma.web import create_app
from tests.test_aws_existing_subnet import subnet_spec
from tests.test_aws_placement import specification
from tests.test_generator import assert_native_files
from tests.test_preflight_web import headers

pytest_plugins = ["tests.test_generator"]


@pytest.mark.parametrize("windows", [False, True])
@pytest.mark.parametrize("existing", [False, True])
def test_terminal_collects_tenancy_and_offline_report_preserves_unknown(
    windows, existing, monkeypatch
):
    spec = subnet_spec(windows=windows) if existing else specification(windows)
    spec.inputs["instance_tenancy"] = "dedicated"
    fields = {f["label"]: f for f in input_contract(spec.recipe)}
    asked = []

    def prompt(message, **options):
        field = fields[message.rstrip("?:")]
        asked.append(field["name"])
        answer = spec.inputs.get(field["name"], field["default"])
        return Mock(ask=lambda: str(answer) if field["kind"] == "integer" else answer)

    for kind in ("text", "confirm", "select"):
        monkeypatch.setattr(f"terraforma.cli.questionary.{kind}", prompt)
    collected = collect_recipe_inputs(spec.recipe)
    assert "instance_tenancy" in asked
    assert collected.inputs["instance_tenancy"] == "dedicated"
    monkeypatch.setattr(
        "subprocess.run",
        lambda *args, **kwargs: pytest.fail("Offline generation must not invoke cloud commands."),
    )
    report = target_preflight(collected)
    assert "tenancy are not checked" in report["limitations"]
    assert report["approval_granted"] is False
    assert report["deployment_readiness_verified"] is False


@pytest.mark.parametrize("windows", [False, True])
@pytest.mark.parametrize("existing", [False, True])
@pytest.mark.parametrize("tenancy", ["provider_default", "dedicated"])
def test_tenancy_roundtrip_preserves_requested_choice_and_limits(windows, existing, tenancy):
    spec = subnet_spec(windows=windows) if existing else specification(windows)
    spec.inputs["instance_tenancy"] = tenancy
    project = compile_project(spec)
    resources = hcl2.loads(project["files"]["main.tf"])["resource"]
    vm = next(r['"aws_instance"']['"web"'] for r in resources if '"aws_instance"' in r)
    assert "host_id" not in vm and "host_resource_group_arn" not in vm
    assert all('"aws_ec2_host"' not in resource for resource in resources)
    assert (
        vm["tenancy"]
        == '${var.instance_tenancy == "provider_default" ? null : var.instance_tenancy}'
    )
    assert 'default = "' + tenancy + '"' in project["files"]["variables.tf"]
    contract = next(f for f in input_contract(spec.recipe) if f["name"] == "instance_tenancy")
    assert contract["default"] == "provider_default"
    assert contract["choices"] == ["provider_default", "dedicated"]
    with TestClient(create_app(), base_url="http://127.0.0.1") as client:
        imported = client.post(
            "/api/projects/import", headers=headers(client), json=spec.model_dump()
        )
    assert imported.status_code == 200, imported.text
    restored = imported.json()
    assert restored["files"] == project["files"]
    component = next(
        c for c in restored["guide"]["components"] if c["name"] == "EC2 hardware tenancy"
    )
    assert component["explanation"] == aws_tenancy_guidance(spec.inputs)
    assert "unverified" in component["explanation"]
    assert restored["target"]["identity_verified"] is False


@pytest.mark.parametrize("value", ["host", "default", "DEDICATED", True, 1, "private-marker"])
def test_unsupported_tenancy_rejected(value):
    with pytest.raises(ProjectInputError) as error:
        compile_project(specification(False, instance_tenancy=value))
    assert error.value.field == "instance_tenancy"
    assert "private-marker" not in str(error.value)


@pytest.mark.parametrize(
    "provider,workload",
    [
        ("azure", "virtual_machine"),
        ("gcp", "windows_virtual_machine"),
        ("aws", "single_web_server"),
        ("aws", "load_balanced_tier"),
        ("aws", "static_site"),
        ("aws", "secure_database"),
    ],
)
def test_tenancy_not_advertised_outside_aws_standalone(provider, workload):
    config = WizardConfig(provider=provider, architecture_type=workload, project_name="scope-test")
    assert "instance_tenancy" not in {f["name"] for f in input_contract(config)}


@pytest.mark.parametrize("windows", [False, True])
@pytest.mark.parametrize("existing", [False, True])
@pytest.mark.parametrize("tenancy", ["provider_default", "dedicated"])
def test_native_tenancy_configuration(native_directories, windows, existing, tenancy):
    spec = subnet_spec(windows=windows) if existing else specification(windows)
    spec.inputs["instance_tenancy"] = tenancy
    assert_native_files(native_directories["aws"], compile_project(spec)["files"])


@pytest.mark.parametrize("windows", [False, True])
def test_mocked_plan_retains_requested_dedicated_tenancy(native_directories, windows):
    directory = native_directories["aws"]
    assert_native_files(
        directory, compile_project(specification(windows, instance_tenancy="dedicated"))["files"]
    )
    tests = directory / "tenancy-tests"
    tests.mkdir(exist_ok=True)
    (tests / "tenancy.tftest.hcl").write_text(
        """
mock_provider "aws" {
  alias = "offline"
  override_during = plan
  mock_data "aws_availability_zones" { defaults = { names = ["us-east-1a", "us-east-1b"] } }
  mock_data "aws_ami" { defaults = { id = "ami-0123456789abcdef0" } }
}
run "request_dedicated_without_host_allocation" {
  command = plan
  providers = { aws = aws.offline }
  assert {
    condition = length(aws_instance.web) == 1 && aws_instance.web[0].tenancy == "dedicated"
    error_message = "Dedicated Instance tenancy must not allocate or select a Dedicated Host."
  }
}
""",
        encoding="utf-8",
    )
    result = subprocess.run(
        [shutil.which("terraform"), "test", "-test-directory=tenancy-tests", "-no-color"],
        cwd=directory,
        capture_output=True,
        text=True,
        timeout=60,
        check=False,
    )
    assert result.returncode == 0, result.stdout + result.stderr
