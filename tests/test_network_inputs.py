import os
import shutil
import subprocess

import pytest

from terraforma.generator import TerraformGenerator, WizardConfig
from terraforma.project import input_contract, validate_answer


def definition(provider, workload="secure_database"):
    config = WizardConfig(
        provider=provider, project_name="network-test", architecture_type=workload, is_public=True
    )
    name = "database_client_ip" if provider == "azure" else "allowed_cidr"
    return next(item for item in input_contract(config) if item["name"] == name)


CIDR_CASES = [
    ("0.0.0.0/0", False),
    ("128.0.0.0/1", False),
    ("203.0.112.0/23", False),
    ("203.0.113.0/24", True),
    ("203.0.113.7/32", True),
    ("10.0.0.0/8", True),
    ("10.0.0.0/7", False),
    ("172.16.0.0/12", True),
    ("172.16.0.0/11", False),
    ("172.32.0.0/16", False),
    ("192.168.0.0/16", True),
    ("192.168.0.0/15", False),
    ("::/0", False),
    ("not-a-network", False),
]
ADDRESS_CASES = [
    ("0.0.0.0", False),
    ("0.1.2.3", False),
    ("127.0.0.1", False),
    ("224.0.0.1", False),
    ("255.255.255.255", False),
    ("203.0.113.7", True),
    ("10.0.0.1", True),
    ("::1", False),
]


@pytest.mark.parametrize("provider", ["aws", "gcp"])
@pytest.mark.parametrize("value,accepted", CIDR_CASES)
def test_database_network_policy(provider, value, accepted):
    field = definition(provider)
    if accepted:
        validate_answer(field, value)
    else:
        with pytest.raises(ValueError):
            validate_answer(field, value)


@pytest.mark.parametrize("value,accepted", ADDRESS_CASES)
def test_azure_client_address_policy(value, accepted):
    field = definition("azure")
    if accepted:
        validate_answer(field, value)
    else:
        with pytest.raises(ValueError):
            validate_answer(field, value)


@pytest.mark.parametrize("provider", ["aws", "gcp"])
def test_public_http_network_is_not_subject_to_database_policy(provider):
    field = definition(provider, "single_web_server")
    validate_answer(field, "0.0.0.0/0")
    assert field["network_policy"] is None


def test_native_database_conditions_match_questionnaire(tmp_path):
    if os.environ.get("TERRAFORMA_NATIVE_TESTS") != "1":
        pytest.skip("Set TERRAFORMA_NATIVE_TESTS=1 to check native network conditions.")
    terraform = shutil.which("terraform")
    assert terraform
    environment = {
        key: value
        for key, value in os.environ.items()
        if not key.upper().startswith(("TF_CLI_ARGS", "TF_VAR_", "TF_DATA_DIR", "TF_WORKSPACE"))
    }
    for provider, cases in (("aws", CIDR_CASES), ("azure", ADDRESS_CASES)):
        generator = TerraformGenerator(
            WizardConfig(
                provider=provider,
                project_name="network-test",
                architecture_type="secure_database",
                is_public=True,
            )
        )
        generator.generate()
        field = definition(provider)
        variable = next(item for item in generator.variables if item.labels[0] == field["name"])
        (tmp_path / "variables.tf").write_text(variable.render(), encoding="utf-8")
        condition = variable.children[0].attributes["condition"].value
        for value, accepted in cases:
            result = subprocess.run(
                [terraform, "console", "-no-color", f"-var={field['name']}={value}"],
                cwd=tmp_path,
                env=environment,
                input=condition + "\n",
                capture_output=True,
                text=True,
                timeout=30,
                check=False,
            )
            assert result.returncode == 0, result.stderr
            assert result.stdout.strip().splitlines()[-1] == str(accepted).lower(), value
