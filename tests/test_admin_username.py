import os
import shutil
import subprocess

import pytest

from terraforma.generator import AZURE_RESERVED_USERNAMES, TerraformGenerator, WizardConfig
from terraforma.project import (
    ProjectSpecification,
    compile_project,
    input_contract,
    validate_answer,
)

KEY = "ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAIAEBAQEBAQEBAQEBAQEBAQEBAQEBAQEBAQEBAQEBAQEB"
BAD_FORMATS = [
    "Admin",
    "name with spaces",
    "-operator",
    "operator-",
    "op",
    "x" * 33,
    "name$",
    "operator\n",
]
GOOD_NAMES = ["terraforma", "cloud-operator", "ops_team", "operator42"]


def config(workload="virtual_machine"):
    return WizardConfig(provider="azure", project_name="admin-test", architecture_type=workload)


@pytest.mark.parametrize("value", [*AZURE_RESERVED_USERNAMES, *BAD_FORMATS])
def test_reserved_or_unsupported_username_is_rejected_without_echo(value):
    field = next(item for item in input_contract(config()) if item["name"] == "admin_username")
    with pytest.raises(ValueError, match="non-reserved username"):
        validate_answer(field, value)


@pytest.mark.parametrize("workload", ["virtual_machine", "single_web_server", "load_balanced_tier"])
def test_selected_username_is_used_for_vm_key_and_output(workload):
    project = compile_project(
        ProjectSpecification(
            recipe=config(workload),
            inputs={
                "subscription_id": "12345678-1234-1234-1234-123456789abc",
                "ssh_public_key": KEY,
                "admin_username": "cloud-operator",
            },
        )
    )
    main = project["files"]["main.tf"]
    assert "admin_username = var.admin_username" in main
    assert "username = var.admin_username" in main
    assert 'default = "cloud-operator"' in project["files"]["variables.tf"]
    if workload == "virtual_machine":
        assert "value = var.admin_username" in project["files"]["outputs.tf"]


def test_native_username_conditions_match_questionnaire(tmp_path):
    if os.environ.get("TERRAFORMA_NATIVE_TESTS") != "1":
        pytest.skip("Set TERRAFORMA_NATIVE_TESTS=1 to check native username conditions.")
    terraform = shutil.which("terraform")
    assert terraform
    generator = TerraformGenerator(config())
    generator.generate()
    variable = next(item for item in generator.variables if item.labels[0] == "admin_username")
    (tmp_path / "variables.tf").write_text(variable.render(), encoding="utf-8")
    conditions = [item.attributes["condition"].value for item in variable.children]
    expression = "alltrue([" + ", ".join(conditions) + "])\n"
    environment = {
        key: value
        for key, value in os.environ.items()
        if not key.upper().startswith(("TF_CLI_ARGS", "TF_VAR_", "TF_DATA_DIR", "TF_WORKSPACE"))
    }
    for value in [*AZURE_RESERVED_USERNAMES, *BAD_FORMATS, *GOOD_NAMES]:
        result = subprocess.run(
            [terraform, "console", "-no-color", f"-var=admin_username={value}"],
            cwd=tmp_path,
            env=environment,
            input=expression,
            capture_output=True,
            text=True,
            timeout=30,
            check=False,
        )
        assert result.returncode == 0, result.stderr
        assert result.stdout.strip().splitlines()[-1] == str(value in GOOD_NAMES).lower()
