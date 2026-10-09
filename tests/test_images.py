import json
import os
import shutil
import subprocess

import pytest

from terraforma.catalog import recipe_capabilities
from terraforma.generator import LINUX_IMAGE_CHOICES, TerraformGenerator, WizardConfig
from terraforma.project import ProjectSpecification, compile_project, input_contract
from tests.hcl_text import unaligned


@pytest.mark.parametrize("provider", ["aws", "azure", "gcp"])
@pytest.mark.parametrize("workload", ["single_web_server", "load_balanced_tier"])
def test_supported_image_selection_and_contract(provider, workload):
    config = WizardConfig(provider=provider, project_name="image-test", architecture_type=workload)
    field = next(item for item in input_contract(config) if item["name"] == "os_image")
    assert field["choices"] == list(LINUX_IMAGE_CHOICES[provider])
    assert field["default"] == LINUX_IMAGE_CHOICES[provider][0]
    assert recipe_capabilities(config)["image_choices"] == field["choices"]
    for choice in field["choices"]:
        inputs = {
            "aws": {"aws_account_id": "123456789012"},
            "azure": {
                "subscription_id": "12345678-1234-1234-1234-123456789abc",
                "ssh_public_key": "ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAIAEBAQEBAQEBAQEBAQEBAQEBAQEBAQEBAQEBAQEBAQEB",
            },
            "gcp": {"gcp_project_id": "example-project"},
        }[provider]
        result = compile_project(
            ProjectSpecification(recipe=config, inputs={**inputs, "os_image": choice})
        )
        assert f'default = "{choice}"' in unaligned(result["files"]["variables.tf"])
        assert "var.os_image" in result["files"]["main.tf"]
        assert result["specification"]["inputs"]["os_image"] == choice


@pytest.mark.parametrize("value", ["windows-2022", "custom-image", "ubuntu-arm64", True, 42])
def test_unsupported_image_is_rejected(value):
    with pytest.raises((ValueError, TypeError)):
        compile_project(
            ProjectSpecification(
                recipe=WizardConfig(
                    provider="aws", project_name="image-test", architecture_type="single_web_server"
                ),
                inputs={"aws_account_id": "123456789012", "os_image": value},
            )
        )


def test_native_image_resolution_and_startup_match_selected_os(tmp_path):
    if os.environ.get("TERRAFORMA_NATIVE_TESTS") != "1":
        pytest.skip("Set TERRAFORMA_NATIVE_TESTS=1 to check native image selectors.")
    terraform = shutil.which("terraform")
    assert terraform
    environment = {
        key: value
        for key, value in os.environ.items()
        if not key.upper().startswith(("TF_CLI_ARGS", "TF_VAR_", "TF_DATA_DIR", "TF_WORKSPACE"))
    }
    for provider in LINUX_IMAGE_CHOICES:
        generator = TerraformGenerator(
            WizardConfig(
                provider=provider, project_name="image-test", architecture_type="single_web_server"
            )
        )
        generator.generate()
        variable = next(item for item in generator.variables if item.labels[0] == "os_image")
        (tmp_path / "variables.tf").write_text(variable.render(), encoding="utf-8")
        if provider == "aws":
            ami = next(item for item in generator.main if item.labels[:1] == ("aws_ami",))
            vm = next(item for item in generator.main if item.labels[:1] == ("aws_instance",))
            expressions = [
                ami.attributes["owners"].value,
                ami.children[0].attributes["values"].value,
                vm.attributes["user_data"].value,
            ]
            expected = [
                ("amazon", "al2023-ami-2023", "dnf install"),
                ("099720109477", "ubuntu-noble-24.04-amd64", "apt-get install"),
            ]
        elif provider == "azure":
            vm = next(
                item
                for item in generator.main
                if item.labels[:1] == ("azurerm_linux_virtual_machine",)
            )
            image = next(item for item in vm.children if item.kind == "source_image_reference")
            assert image.attributes["publisher"] == "Canonical"
            expressions = [image.attributes["offer"].value, image.attributes["sku"].value]
            expected = [
                ("0001-com-ubuntu-server-jammy", "22_04-lts-gen2"),
                ("ubuntu-24_04-lts", '"server"'),
            ]
        else:
            vm = next(
                item for item in generator.main if item.labels[:1] == ("google_compute_instance",)
            )
            disk = next(item for item in vm.children if item.kind == "boot_disk")
            expressions = [disk.children[0].attributes["image"].value]
            expected = [("debian-cloud/debian-12",), ("ubuntu-os-cloud/ubuntu-2404-lts-amd64",)]
        for choice, tokens in zip(LINUX_IMAGE_CHOICES[provider], expected, strict=True):
            for expression, token in zip(expressions, tokens, strict=True):
                result = subprocess.run(
                    [terraform, "console", "-no-color", f"-var=os_image={choice}"],
                    cwd=tmp_path,
                    env=environment,
                    input=expression.replace("var.image_version", '"latest"') + "\n",
                    capture_output=True,
                    text=True,
                    timeout=30,
                    check=False,
                )
                assert result.returncode == 0, result.stderr
                assert token in result.stdout


@pytest.mark.parametrize(
    "image,version,expected",
    [
        ("debian-12", "latest", "debian-cloud/debian-12"),
        ("debian-12", "debian-12-bookworm-v20240213", "debian-cloud/debian-12-bookworm-v20240213"),
        (
            "ubuntu-24.04",
            "ubuntu-2404-noble-amd64-v20261001",
            "ubuntu-os-cloud/ubuntu-2404-noble-amd64-v20261001",
        ),
    ],
)
def test_native_gcp_exact_pin_resolves_to_fixed_publisher(tmp_path, image, version, expected):
    if os.environ.get("TERRAFORMA_NATIVE_TESTS") != "1":
        pytest.skip("Set TERRAFORMA_NATIVE_TESTS=1 to check native image selectors.")
    terraform = shutil.which("terraform")
    assert terraform
    generator = TerraformGenerator(
        WizardConfig(
            provider="gcp", project_name="image-test", architecture_type="single_web_server"
        )
    )
    generator.generate()
    variables = [
        item.render()
        for item in generator.variables
        if item.labels[0] in {"os_image", "image_version"}
    ]
    (tmp_path / "variables.tf").write_text("\n\n".join(variables), encoding="utf-8")
    vm = next(item for item in generator.main if item.labels[:1] == ("google_compute_instance",))
    disk = next(item for item in vm.children if item.kind == "boot_disk")
    expression = disk.children[0].attributes["image"].value
    environment = {
        key: value
        for key, value in os.environ.items()
        if not key.upper().startswith(("TF_CLI_ARGS", "TF_VAR_", "TF_DATA_DIR", "TF_WORKSPACE"))
    }
    result = subprocess.run(
        [
            terraform,
            "console",
            "-no-color",
            "-var=os_image=" + image,
            "-var=image_version=" + version,
        ],
        cwd=tmp_path,
        env=environment,
        input=expression + "\n",
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    )
    assert result.returncode == 0, result.stderr
    assert json.loads(result.stdout) == expected
