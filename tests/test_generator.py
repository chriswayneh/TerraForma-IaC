import itertools
import json
import os
import shutil
import subprocess
from pathlib import Path

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


def test_native_object_keys_preserve_literal_templates(tmp_path):
    if os.environ.get("TERRAFORMA_NATIVE_TESTS") != "1":
        pytest.skip("Set TERRAFORMA_NATIVE_TESTS=1 to run native literal evaluation.")
    terraform = shutil.which("terraform")
    if not terraform:
        pytest.fail("Native tests require terraform on PATH.")
    values = {
        '${file("canary.txt")}': "interpolation stays literal",
        "%{ if true }changed%{ endif }": "directive stays literal",
        "café 🐬": "Unicode stays literal",
    }
    (tmp_path / "canary.txt").write_text("evaluated-key", encoding="utf-8")
    (tmp_path / "main.tf").write_text(
        'output "literal" {\n value = ' + value_hcl(values) + "\n}\n", encoding="utf-8"
    )
    expected = value_hcl(json.dumps(values, ensure_ascii=False))
    (tmp_path / "literal.tftest.hcl").write_text(
        'run "literal_keys" {\n command = plan\n assert {\n'
        f" condition = output.literal == jsondecode({expected})\n"
        ' error_message = "Object keys must preserve exact literal text."\n }\n}\n',
        encoding="utf-8",
    )
    for arguments in (
        ["init", "-backend=false", "-input=false", "-no-color"],
        ["test", "-no-color"],
    ):
        result = subprocess.run(
            [terraform, *arguments],
            cwd=tmp_path,
            capture_output=True,
            text=True,
            timeout=30,
            check=False,
        )
        assert result.returncode == 0, result.stdout + result.stderr


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
    config.write_text(
        'plugin "terraform" {\n  enabled = true\n  preset = "recommended"\n}\n', encoding="utf-8"
    )
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


@pytest.mark.parametrize("image", ["amazon-linux-2023", "ubuntu-24.04"])
@pytest.mark.parametrize("workload", ["virtual_machine", "single_web_server", "load_balanced_tier"])
def test_native_aws_pinned_image_versions(native_directories, image, workload):
    from terraforma.project import compile_project
    from tests.test_vm_protection import specification

    spec = specification("aws", os_image=image, image_version="ami-0123456789abcdef0")
    spec.recipe.architecture_type = workload
    if workload != "virtual_machine":
        spec.inputs.pop("ssh_public_key")
    assert_native_files(native_directories["aws"], compile_project(spec)["files"])


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


@pytest.mark.parametrize("image", ["ubuntu-22.04", "ubuntu-24.04"])
@pytest.mark.parametrize("enabled", [False, True])
def test_native_accelerated_networking(native_directories, image, enabled):
    from terraforma.project import compile_project
    from tests.test_trusted_launch import specification

    spec = specification(image=image)
    spec.inputs["enable_accelerated_networking"] = enabled
    assert_native_files(native_directories["azure"], compile_project(spec)["files"])


@pytest.mark.parametrize("provider", ["aws", "azure", "gcp"])
@pytest.mark.parametrize("public", [False, True])
def test_native_fixed_private_ip(native_directories, provider, public):
    from terraforma.project import compile_project
    from tests.test_private_ip import specification

    address = {
        "aws": "10.0.0.4" if public else "10.0.10.4",
        "azure": "10.0.1.4",
        "gcp": "10.0.1.2",
    }[provider]
    assert_native_files(
        native_directories[provider],
        compile_project(specification(provider, public, address=address))["files"],
    )


@pytest.mark.parametrize("disk_type", ["gp3", "gp2"])
@pytest.mark.parametrize("enabled", [True, False])
def test_native_gp3_performance_options(native_directories, disk_type, enabled):
    from terraforma.project import compile_project
    from tests.test_private_ip import specification

    spec = specification("aws")
    spec.inputs.update(boot_disk_type=disk_type, data_disk_type=disk_type, enable_data_disk=enabled)
    if disk_type == "gp3":
        spec.inputs.update(boot_disk_iops=6000, boot_disk_throughput=1000)
        if enabled:
            spec.inputs.update(data_disk_iops=16000, data_disk_throughput=1000)
    assert_native_files(native_directories["aws"], compile_project(spec)["files"])


@pytest.mark.parametrize("prefix", ["boot_disk", "data_disk"])
@pytest.mark.parametrize(
    "iops,throughput,boot_valid,data_valid",
    [
        (3000, 125, True, True),
        (3000, 750, True, True),
        (3000, 751, False, False),
        (3000, 1000, False, False),
        (10000, 1000, True, True),
        (10001, 1000, False, True),
        (16000, 1000, False, True),
    ],
)
def test_native_gp3_throughput_precondition(
    tmp_path, prefix, iops, throughput, boot_valid, data_valid
):
    if os.environ.get("TERRAFORMA_NATIVE_TESTS") != "1":
        pytest.skip("Set TERRAFORMA_NATIVE_TESTS=1 to run native validation.")
    executable = shutil.which("terraform")
    if not executable:
        pytest.fail("Native tests require Terraform on PATH.")
    from terraforma.generator import block

    generator = TerraformGenerator(
        WizardConfig(provider="aws", project_name="disk-test", architecture_type="virtual_machine")
    )
    generator.generate()
    variables = [
        item.render()
        for item in generator.variables
        if item.labels[0].startswith(prefix + "_") or item.labels[0] == "enable_data_disk"
    ]
    resource = block(
        "resource",
        "terraform_data",
        "performance_check",
        children=[block("lifecycle", children=[generator._gp3_precondition(prefix)])],
    )
    (tmp_path / "main.tf").write_text(
        "\n\n".join([*variables, resource.render()]), encoding="utf-8"
    )
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
            "-input=false",
            "-lock=false",
            "-no-color",
            "-var=enable_data_disk=true",
            f"-var={prefix}_iops={iops}",
            f"-var={prefix}_throughput={throughput}",
        ],
        cwd=tmp_path,
        capture_output=True,
        text=True,
        timeout=60,
        check=False,
    )
    valid = boot_valid if prefix == "boot_disk" else data_valid
    assert result.returncode == (0 if valid else 1), result.stdout + result.stderr
    if not valid:
        assert "throughput no greater than one quarter" in " ".join(result.stderr.split())


@pytest.mark.parametrize(
    "provider,public,network,subnet",
    [
        ("aws", True, "10.32.0.0/20", "10.32.0.0/28"),
        ("aws", False, "10.32.0.0/16", "10.32.10.0/24"),
        ("azure", False, "10.32.0.0/20", "10.32.0.16/28"),
        ("gcp", True, "10.32.0.0/16", "10.32.0.0/16"),
    ],
)
@pytest.mark.parametrize(
    "choice",
    ["blank", "first_usable", "last_usable", "first_reserved", "last_reserved", "wrong_subnet"],
)
def test_native_private_ip_precondition(tmp_path, provider, public, network, subnet, choice):
    if os.environ.get("TERRAFORMA_NATIVE_TESTS") != "1":
        pytest.skip("Set TERRAFORMA_NATIVE_TESTS=1 to run native validation.")
    executable = shutil.which("terraform")
    if not executable:
        pytest.fail("Native tests require Terraform on PATH.")
    import ipaddress

    from terraforma.generator import block

    selected = ipaddress.IPv4Network(subnet)
    first, excluded_last = (2, 2) if provider == "gcp" else (4, 1)
    addresses = {
        "blank": "",
        "first_usable": str(selected[first]),
        "last_usable": str(selected[selected.num_addresses - excluded_last - 1]),
        "first_reserved": str(selected[first - 1]),
        "last_reserved": str(selected[-excluded_last]),
        "wrong_subnet": "192.168.250.10",
    }
    generator = TerraformGenerator(
        WizardConfig(
            provider=provider,
            project_name="address-test",
            architecture_type="virtual_machine",
            is_public=public,
        )
    )
    generator.generate()
    variables = [
        item.render()
        for item in generator.variables
        if item.labels[0]
        in {"network_cidr", "private_ip_address", "use_existing_network", "existing_subnet_cidr"}
    ]
    resource = block(
        "resource",
        "terraform_data",
        "address_check",
        children=[block("lifecycle", children=[generator._private_ip_precondition()])],
    )
    (tmp_path / "main.tf").write_text(
        "\n\n".join([*variables, resource.render()]), encoding="utf-8"
    )
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
            "-input=false",
            "-lock=false",
            "-no-color",
            f"-var=network_cidr={network}",
            f"-var=private_ip_address={addresses[choice]}",
        ],
        cwd=tmp_path,
        capture_output=True,
        text=True,
        timeout=60,
        check=False,
    )
    valid = choice in {"blank", "first_usable", "last_usable"}
    assert result.returncode == (0 if valid else 1), result.stdout + result.stderr
    if not valid:
        assert "provider-reserved addresses" in result.stderr


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


@pytest.mark.parametrize("public,encryption", list(itertools.product([False, True], repeat=2)))
def test_native_windows_vm_validation_and_lint(native_directories, public, encryption):
    from terraforma.project import compile_project
    from tests.test_windows_vm import specification

    spec = specification(public, encryption, enable_data_disk=True)
    assert_native_files(native_directories["aws"], compile_project(spec)["files"])


@pytest.mark.parametrize("public,secure_boot", list(itertools.product([False, True], repeat=2)))
def test_native_gcp_windows_vm_validation_and_lint(native_directories, public, secure_boot):
    from terraforma.project import compile_project
    from tests.test_gcp_windows_vm import specification

    spec = specification(public, enable_data_disk=True, enable_secure_boot=secure_boot)
    assert_native_files(native_directories["gcp"], compile_project(spec)["files"])


@pytest.mark.parametrize("public,secure_boot", list(itertools.product([False, True], repeat=2)))
def test_native_azure_windows_vm_validation_and_lint(native_directories, public, secure_boot):
    from terraforma.project import compile_project
    from tests.test_azure_windows_vm import specification

    spec = specification(
        public,
        enable_data_disk=True,
        enable_secure_boot=secure_boot,
        enable_patch_assessment=public,
    )
    assert_native_files(native_directories["azure"], compile_project(spec)["files"])


@pytest.mark.parametrize("mode", ["None", "ReadOnly", "ReadWrite"])
def test_native_azure_disk_cache_modes(native_directories, mode):
    from terraforma.project import compile_project
    from tests.test_azure_disk_caching import specification

    spec = specification(
        True, enable_data_disk=True, boot_disk_caching=mode, data_disk_caching=mode
    )
    assert_native_files(native_directories["azure"], compile_project(spec)["files"])


@pytest.mark.parametrize(
    "windows,policy", list(itertools.product([False, True], ["MIGRATE", "TERMINATE"]))
)
def test_native_gcp_standard_scheduling(native_directories, windows, policy):
    from terraforma.project import compile_project
    from tests.test_gcp_scheduling import specification

    spec = specification(
        windows, host_maintenance_policy=policy, automatic_restart=policy == "MIGRATE"
    )
    assert_native_files(native_directories["gcp"], compile_project(spec)["files"])


@pytest.mark.parametrize("windows,public", list(itertools.product([False, True], [False, True])))
def test_native_gcp_iap_access(native_directories, windows, public):
    from terraforma.project import compile_project
    from tests.test_gcp_scheduling import specification

    spec = specification(windows, admin_access_method="iap_tunnel")
    spec.recipe.is_public = public
    assert_native_files(native_directories["gcp"], compile_project(spec)["files"])


@pytest.mark.parametrize("public", [False, True])
def test_native_gcp_windows_exact_image(native_directories, public):
    from terraforma.project import compile_project
    from tests.test_gcp_windows_vm import specification

    spec = specification(public=public, image_version="windows-server-2022-dc-v20261001")
    assert_native_files(native_directories["gcp"], compile_project(spec)["files"])


@pytest.mark.parametrize(
    "provider,windows,delete",
    list(itertools.product(["aws", "gcp"], [False, True], [False, True])),
)
def test_native_standalone_boot_retention(native_directories, provider, windows, delete):
    from terraforma.project import compile_project
    from tests.test_boot_disk_retention import specification

    spec = specification(provider, windows, delete_boot_disk_with_vm=delete)
    assert_native_files(native_directories[provider], compile_project(spec)["files"])


@pytest.mark.parametrize(
    "public,version", list(itertools.product([False, True], ["latest", "ami-0123456789abcdef0"]))
)
def test_native_aws_windows_core(native_directories, public, version):
    from terraforma.project import compile_project
    from tests.test_windows_vm import specification

    spec = specification(public=public, os_image="windows-server-2022-core", image_version=version)
    assert_native_files(native_directories["aws"], compile_project(spec)["files"])


@pytest.mark.parametrize(
    "windows,mode",
    list(itertools.product([False, True], ["provider_default", "one_hop", "two_hops"])),
)
def test_native_aws_metadata_hops(native_directories, windows, mode):
    from terraforma.project import compile_project
    from tests.test_aws_metadata_hops import specification

    assert_native_files(
        native_directories["aws"],
        compile_project(specification(windows, metadata_hop_limit=mode))["files"],
    )


@pytest.mark.parametrize("windows,public", list(itertools.product([False, True], repeat=2)))
def test_native_aws_expanded_gp3(native_directories, windows, public):
    from terraforma.project import compile_project
    from tests.test_aws_placement import specification

    spec = specification(
        windows,
        public=public,
        boot_disk_size_gb=160,
        boot_disk_iops=80000,
        boot_disk_throughput=2000,
        enable_data_disk=True,
        data_disk_size_gb=160,
        data_disk_iops=80000,
        data_disk_throughput=2000,
    )
    assert_native_files(native_directories["aws"], compile_project(spec)["files"])


@pytest.mark.parametrize(
    "public,version", list(itertools.product([False, True], ["latest", "20348.1.1"]))
)
def test_native_azure_refreshed_windows_offer(native_directories, public, version):
    from terraforma.project import compile_project
    from tests.test_azure_windows_vm import specification

    spec = specification(public=public, image_version=version)
    assert_native_files(native_directories["azure"], compile_project(spec)["files"])


@pytest.mark.parametrize(
    "public,version", list(itertools.product([False, True], ["latest", "20348.1.1"]))
)
def test_native_azure_windows_core(native_directories, public, version):
    from terraforma.project import compile_project
    from tests.test_azure_windows_core import specification

    spec = specification(public=public, os_image="windows-server-2022-core", image_version=version)
    assert_native_files(native_directories["azure"], compile_project(spec)["files"])


@pytest.mark.parametrize(
    "public,version",
    list(itertools.product([False, True], ["latest", "windows-server-2022-dc-core-v20261001"])),
)
def test_native_gcp_windows_core(native_directories, public, version):
    from terraforma.project import compile_project
    from tests.test_gcp_windows_vm import specification

    spec = specification(
        public=public,
        os_image="windows-server-2022-core",
        image_version=version,
        admin_access_method="iap_tunnel",
    )
    assert_native_files(native_directories["gcp"], compile_project(spec)["files"])


@pytest.mark.parametrize(
    "windows,data_disk,enabled", list(itertools.product([False, True], repeat=3))
)
def test_native_gcp_disk_key(native_directories, windows, data_disk, enabled):
    from terraforma.project import compile_project
    from tests.test_gcp_disk_key import KEY, specification

    spec = specification(windows, enable_data_disk=data_disk, use_customer_managed_disk_key=enabled)
    if enabled:
        spec.inputs["disk_kms_key"] = KEY
    assert_native_files(native_directories["gcp"], compile_project(spec)["files"])


@pytest.mark.parametrize("windows,zone", list(itertools.product([False, True], ["regional", "2"])))
def test_native_azure_standalone_placement(native_directories, windows, zone):
    from terraforma.project import compile_project
    from tests.test_azure_disk_caching import specification

    spec = specification(windows, availability_zone=zone, enable_data_disk=True)
    spec.recipe.is_public = True
    spec.inputs["allowed_cidr"] = "10.20.0.0/24"
    assert_native_files(native_directories["azure"], compile_project(spec)["files"])


@pytest.mark.parametrize("windows,zone", list(itertools.product([False, True], ["", "us-east-1b"])))
def test_native_aws_standalone_placement(native_directories, windows, zone):
    from terraforma.project import compile_project
    from tests.test_aws_placement import specification

    spec = specification(windows, availability_zone=zone, enable_data_disk=True)
    assert_native_files(native_directories["aws"], compile_project(spec)["files"])


@pytest.mark.parametrize(
    "windows,mode", list(itertools.product([False, True], ["standard", "unlimited"]))
)
def test_native_aws_cpu_credit_modes(native_directories, windows, mode):
    from terraforma.project import compile_project
    from tests.test_aws_placement import specification

    assert_native_files(
        native_directories["aws"],
        compile_project(specification(windows, cpu_credit_mode=mode))["files"],
    )


@pytest.mark.parametrize("incompatible", [False, True])
def test_native_validation_preserves_locks_and_rejects_conflicting_requirements(
    native_directories, tmp_path, incompatible
):
    from terraforma.sandbox import ValidationSandbox

    locked = (native_directories["aws"] / ".terraform.lock.hcl").read_bytes()
    files = TerraformGenerator(
        WizardConfig(provider="aws", project_name="lock-test", architecture_type="static_site")
    ).generate()
    if incompatible:
        assert '"~> 6.0"' in files["main.tf"]
        files["main.tf"] = files["main.tf"].replace('"~> 6.0"', '"< 6.0"')
    for name, content in files.items():
        (tmp_path / name).write_text(content, encoding="utf-8")
    (tmp_path / ".terraform.lock.hcl").write_bytes(locked)
    with ValidationSandbox(target_dir=tmp_path) as sandbox:
        result = sandbox.execute_checks()
        assert result["is_valid"] is not incompatible, result["logs"]
        copied = (Path(sandbox.temp_dir) / ".terraform.lock.hcl").read_bytes()
        assert copied == locked
        if incompatible:
            assert "[terraform validate;" not in result["logs"]
            assert result["errors"][0]["tool"] == "terraform_validate"
    assert (tmp_path / ".terraform.lock.hcl").read_bytes() == locked
    assert (native_directories["aws"] / ".terraform.lock.hcl").read_bytes() == locked
