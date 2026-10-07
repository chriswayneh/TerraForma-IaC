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
        ["single_web_server", "load_balanced_tier", "secure_database", "static_site"],
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


def test_partial_write_rolls_back(tmp_path):
    with pytest.raises(ValueError, match="filename"):
        write_configuration({"main.tf": "new", "../escape.tf": "bad"}, tmp_path)
    assert not (tmp_path / "main.tf").exists()
    assert not (tmp_path.parent / "escape.tf").exists()


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
