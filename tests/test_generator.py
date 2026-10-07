import itertools
import json
import os
import shutil
import subprocess

import hcl2
import pytest
from pydantic import ValidationError

from terraforma.generator import TerraformGenerator, WizardConfig, value_hcl, write_configuration

CASES = list(
    itertools.product(
        ["aws", "azure", "gcp"],
        [
            "virtual_machine",
            "single_web_server",
            "load_balanced_tier",
            "secure_database",
            "static_site",
        ],
        [False, True],
        [False, True],
    )
)


@pytest.mark.parametrize("provider,architecture,public,encryption", CASES)
def test_all_templates_parse_and_reference_declared_variables(
    provider, architecture, public, encryption
):
    files = TerraformGenerator(
        WizardConfig(
            provider=provider,
            project_name="example",
            architecture_type=architecture,
            is_public=public,
            enable_encryption=encryption,
        )
    ).generate()
    parsed = {name: hcl2.loads(content) for name, content in files.items()}
    assert set(parsed) == {"main.tf", "variables.tf", "outputs.tf"}
    assert parsed["main.tf"]["resource"]
    assert parsed["outputs.tf"]["output"]
    import re

    variables = {name.strip('"') for item in parsed["variables.tf"]["variable"] for name in item}
    references = set(re.findall(r"\bvar\.([a-z_]+)", "\n".join(files.values())))
    assert variables == references
    assert (
        "database_password" not in "\n".join(files.values())
        or "sensitive = true" in files["variables.tf"]
    )


def test_invalid_project_name_is_rejected():
    with pytest.raises(ValidationError):
        WizardConfig(
            provider="aws", project_name='bad"${file("secret")}', architecture_type="static_site"
        )


def test_literal_hcl_cannot_interpolate():
    assert value_hcl('${file("secret")}') == '"$${file(\\"secret\\")}"'


def test_generation_refuses_existing_terraform(tmp_path):
    existing = tmp_path / "old.tf"
    existing.write_text("original")
    with pytest.raises(ValueError, match="already contains"):
        write_configuration({"main.tf": "new"}, tmp_path)
    assert existing.read_text() == "original"
    assert not (tmp_path / "main.tf").exists()


def test_unexpected_filename_writes_nothing(tmp_path):
    with pytest.raises(ValueError, match="filename"):
        write_configuration({"main.tf": "new", "../escape.tf": "bad"}, tmp_path)
    assert not (tmp_path / "main.tf").exists()
    assert not (tmp_path.parent / "escape.tf").exists()


@pytest.mark.parametrize(
    "name",
    [
        "terraform.tfstate",
        "terraform.tfstate.backup",
        "terraform.tfvars",
        "choices.auto.tfvars.json",
        ".terraform.lock.hcl",
    ],
)
def test_generation_refuses_existing_state_values_and_initialization(tmp_path, name):
    marker = tmp_path / name
    marker.write_text("private-original-value")
    with pytest.raises(ValueError, match="fresh project directory"):
        write_configuration({"main.tf": "new"}, tmp_path)
    assert marker.read_text() == "private-original-value"
    assert not (tmp_path / "main.tf").exists()


def test_generation_refuses_initialized_directory(tmp_path):
    (tmp_path / ".terraform").mkdir()
    with pytest.raises(ValueError, match="initialization"):
        write_configuration({"main.tf": "new"}, tmp_path)
    assert list(tmp_path.iterdir()) == [tmp_path / ".terraform"]


@pytest.fixture(scope="module")
def native_directories(tmp_path_factory):
    if os.environ.get("TERRAFORMA_NATIVE_TESTS") != "1":
        pytest.skip("Set TERRAFORMA_NATIVE_TESTS=1 to run native provider validation.")
    if not shutil.which("terraform") or not shutil.which("tflint"):
        pytest.fail("Native tests require terraform and tflint on PATH.")
    directories = {}
    for provider in ("aws", "azure", "gcp"):
        directory = tmp_path_factory.mktemp(provider)
        files = TerraformGenerator(
            WizardConfig(provider=provider, project_name="example", architecture_type="static_site")
        ).generate()
        for name, text in files.items():
            (directory / name).write_text(text, encoding="utf-8")
        result = subprocess.run(
            [shutil.which("terraform"), "init", "-backend=false", "-input=false", "-no-color"],
            cwd=directory,
            capture_output=True,
            text=True,
            timeout=180,
            check=False,
        )
        assert result.returncode == 0, result.stdout + result.stderr
        directories[provider] = directory
    return directories


@pytest.mark.parametrize("provider,architecture,public,encryption", CASES)
def test_native_provider_validation_and_lint(
    native_directories, provider, architecture, public, encryption
):
    directory = native_directories[provider]
    files = TerraformGenerator(
        WizardConfig(
            provider=provider,
            project_name="example",
            architecture_type=architecture,
            is_public=public,
            enable_encryption=encryption,
        )
    ).generate()
    assert_native_files(directory, files)


def assert_native_files(directory, files):
    for name, text in files.items():
        (directory / name).write_text(text, encoding="utf-8")
    result = subprocess.run(
        [shutil.which("terraform"), "validate", "-json"],
        cwd=directory,
        capture_output=True,
        text=True,
        timeout=60,
        check=False,
    )
    assert result.returncode == 0, result.stdout + result.stderr

    assert json.loads(result.stdout)["valid"]
    config = directory / ".tflint.hcl"
    config.write_text('plugin "terraform" {\n  enabled = true\n  preset = "recommended"\n}\n')
    result = subprocess.run(
        [shutil.which("tflint"), "--format=json", f"--config={config}"],
        cwd=directory,
        capture_output=True,
        text=True,
        timeout=60,
        check=False,
    )
    assert result.returncode == 0, result.stdout + result.stderr


@pytest.mark.parametrize("image", ["ubuntu-22.04", "ubuntu-24.04"])
@pytest.mark.parametrize("workload", ["virtual_machine", "single_web_server", "load_balanced_tier"])
def test_native_azure_pinned_image_versions(native_directories, image, workload):
    from terraforma.project import compile_project
    from tests.test_trusted_launch import specification

    spec = specification(image=image)
    spec.recipe.architecture_type = workload
    spec.inputs.pop("enable_secure_boot")
    spec.inputs["image_version"] = "22.04.20261001"
    assert_native_files(native_directories["azure"], compile_project(spec)["files"])


@pytest.mark.parametrize(
    "image,version",
    [
        ("debian-12", "debian-12-bookworm-v20240213"),
        ("ubuntu-24.04", "ubuntu-2404-noble-amd64-v20261001"),
    ],
)
@pytest.mark.parametrize("workload", ["virtual_machine", "single_web_server", "load_balanced_tier"])
def test_native_gcp_pinned_image_versions(native_directories, image, version, workload):
    from terraforma.project import compile_project
    from tests.test_shielded_vm import specification

    spec = specification(image=image)
    spec.recipe.architecture_type = workload
    spec.inputs.pop("enable_secure_boot")
    spec.inputs["image_version"] = version
    assert_native_files(native_directories["gcp"], compile_project(spec)["files"])


@pytest.mark.parametrize(
    "version,valid",
    [
        ("latest", True),
        ("debian-12-bookworm-v20240213", True),
        ("ubuntu-2404-noble-amd64-v20261001", False),
    ],
)
def test_native_gcp_image_precondition_prevents_manual_os_mismatch(tmp_path, version, valid):
    if os.environ.get("TERRAFORMA_NATIVE_TESTS") != "1":
        pytest.skip("Set TERRAFORMA_NATIVE_TESTS=1 to run native validation.")
    executable = shutil.which("terraform")
    if not executable:
        pytest.fail("Native tests require Terraform on PATH.")
    from terraforma.generator import block

    generator = TerraformGenerator(
        WizardConfig(provider="gcp", project_name="pin-test", architecture_type="virtual_machine")
    )
    generator.generate()
    resource = next(
        item
        for item in generator.main
        if item.kind == "resource" and item.labels[0] == "google_compute_instance"
    )
    lifecycle = next(item for item in resource.children if item.kind == "lifecycle")
    variables = [
        item.render()
        for item in generator.variables
        if item.labels[0] in {"os_image", "image_version"}
    ]
    builtin = block(
        "resource",
        "terraform_data",
        "image_check",
        children=[block("lifecycle", children=[lifecycle.children[0]])],
    )
    (tmp_path / "main.tf").write_text("\n\n".join([*variables, builtin.render()]), encoding="utf-8")
    initialized = subprocess.run(
        [executable, "init", "-backend=false", "-input=false", "-no-color"],
        cwd=tmp_path,
        capture_output=True,
        text=True,
        timeout=60,
        check=False,
    )
    assert initialized.returncode == 0, initialized.stdout + initialized.stderr
    result = subprocess.run(
        [
            executable,
            "plan",
            "-refresh=false",
            "-input=false",
            "-no-color",
            "-var",
            "image_version=" + version,
        ],
        cwd=tmp_path,
        capture_output=True,
        text=True,
        timeout=60,
        check=False,
    )
    assert result.returncode == (0 if valid else 1), result.stdout + result.stderr
    if not valid:
        assert "matching the selected Linux operating system" in result.stderr


@pytest.mark.parametrize("image", ["ubuntu-22.04", "ubuntu-24.04"])
@pytest.mark.parametrize("enabled", [False, True])
@pytest.mark.parametrize("public", [False, True])
@pytest.mark.parametrize("diagnostics", [False, True])
def test_native_trusted_launch_choices(native_directories, image, enabled, public, diagnostics):
    from terraforma.project import compile_project
    from tests.test_trusted_launch import specification

    spec = specification(enabled, image, public)
    spec.inputs["enable_boot_diagnostics"] = diagnostics
    assert_native_files(native_directories["azure"], compile_project(spec)["files"])


@pytest.mark.parametrize("image", ["debian-12", "ubuntu-24.04"])
@pytest.mark.parametrize("enabled", [False, True])
@pytest.mark.parametrize("public", [False, True])
def test_native_shielded_vm_choices(native_directories, image, enabled, public):
    from terraforma.project import ProjectSpecification, compile_project

    specification = ProjectSpecification(
        recipe=WizardConfig(
            provider="gcp",
            project_name="shielded-test",
            architecture_type="virtual_machine",
            is_public=public,
        ),
        inputs={
            "gcp_project_id": "example-project",
            "allowed_cidr": "10.1.0.0/24",
            "os_image": image,
            "enable_secure_boot": enabled,
        },
    )
    assert_native_files(native_directories["gcp"], compile_project(specification)["files"])


@pytest.mark.parametrize(
    "provider,disk_type",
    [
        ("aws", "gp3"),
        ("aws", "gp2"),
        ("azure", "StandardSSD_LRS"),
        ("azure", "Standard_LRS"),
        ("azure", "Premium_LRS"),
        ("gcp", "pd-balanced"),
        ("gcp", "pd-standard"),
        ("gcp", "pd-ssd"),
    ],
)
@pytest.mark.parametrize("enabled", [True, False])
def test_native_optional_data_disk_types(native_directories, provider, disk_type, enabled):
    from terraforma.project import ProjectSpecification, compile_project

    inputs = {
        "aws": {
            "aws_account_id": "123456789012",
            "ssh_public_key": "ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAIAEBAQEBAQEBAQEBAQEBAQEBAQEBAQEBAQEBAQEBAQEB",
        },
        "azure": {
            "subscription_id": "12345678-1234-1234-1234-123456789abc",
            "ssh_public_key": "ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAIAEBAQEBAQEBAQEBAQEBAQEBAQEBAQEBAQEBAQEBAQEB",
        },
        "gcp": {"gcp_project_id": "example-project"},
    }[provider]
    specification = ProjectSpecification(
        recipe=WizardConfig(
            provider=provider, project_name="disk-test", architecture_type="virtual_machine"
        ),
        inputs={
            **inputs,
            "enable_data_disk": enabled,
            "data_disk_type": disk_type,
            "data_disk_size_gb": 256,
        },
    )
    assert_native_files(native_directories[provider], compile_project(specification)["files"])


@pytest.mark.parametrize("provider", ["aws", "azure", "gcp"])
@pytest.mark.parametrize("cidr", ["10.80.0.0/16", "172.20.0.0/20", "192.168.16.0/20"])
def test_native_vm_network_ranges(native_directories, provider, cidr):
    from test_vm_networks import specification

    from terraforma.project import compile_project

    assert_native_files(
        native_directories[provider], compile_project(specification(provider, cidr))["files"]
    )


@pytest.mark.parametrize("provider", ["aws", "azure", "gcp"])
def test_native_vm_network_validation_matches_shared_contract(
    native_directories, tmp_path, provider
):
    from test_vm_networks import specification

    from terraforma.project import ProjectInputError, compile_project

    generator = TerraformGenerator(specification(provider, "10.80.0.0/16").recipe)
    generator.generate()
    variable = next(item for item in generator.variables if item.labels == ("network_cidr",))
    condition = variable.children[0].attributes["condition"].value
    ranges = [
        "10.80.0.0/16",
        "172.16.0.0/20",
        "172.31.0.0/16",
        "192.168.0.0/16",
        "10.0.0.0/21",
        "10.0.0.0/28",
        "10.0.0.1/16",
        "172.32.0.0/16",
        "192.169.0.0/16",
        "203.0.113.0/24",
        "fc00::/16",
        "0.0.0.0/0",
        "10.0.0.0/15",
        "10.0.0.0/29",
        "10.0.0.0/255.255.0.0",
        "invalid-range",
    ]
    expected = []
    for cidr in ranges:
        try:
            compile_project(specification(provider, cidr))
        except ProjectInputError:
            expected.append(False)
        else:
            expected.append(True)
    expressions = [condition.replace("var.network_cidr", value_hcl(cidr)) for cidr in ranges]
    result = subprocess.run(
        [shutil.which("terraform"), "console", "-no-color"],
        input="jsonencode([" + ",".join(expressions) + "])\n",
        cwd=tmp_path,
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    assert json.loads(json.loads(result.stdout)) == expected


@pytest.mark.parametrize("provider", ["aws", "azure", "gcp"])
@pytest.mark.parametrize("enabled", [True, False])
def test_native_workload_identity(native_directories, provider, enabled):
    from test_workload_identity import identity_spec

    from terraforma.project import compile_project

    assert_native_files(
        native_directories[provider], compile_project(identity_spec(provider, enabled))["files"]
    )


@pytest.mark.parametrize("provider", ["aws", "gcp"])
def test_native_identity_checks_require_reference_only_when_enabled(
    native_directories, tmp_path, provider
):
    from test_workload_identity import REFERENCES, identity_spec

    generator = TerraformGenerator(identity_spec(provider, True).recipe)
    generator.generate()
    variable = next(item for item in generator.variables if item.labels == ("workload_identity",))
    format_condition = variable.children[0].attributes["condition"].value
    required_condition = (
        generator._identity_precondition().children[0].attributes["condition"].value
    )
    expressions = []
    for enabled, reference in [
        (False, ""),
        (True, ""),
        (True, REFERENCES[provider]),
        (True, "private invalid value"),
    ]:
        condition = "(" + format_condition + ") && (" + required_condition + ")"
        condition = condition.replace("var.enable_workload_identity", value_hcl(enabled)).replace(
            "var.workload_identity", value_hcl(reference)
        )
        expressions.append(condition)
    result = subprocess.run(
        [shutil.which("terraform"), "console", "-no-color"],
        input="jsonencode([" + ",".join(expressions) + "])\n",
        cwd=tmp_path,
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    assert json.loads(json.loads(result.stdout)) == [True, False, True, False]
