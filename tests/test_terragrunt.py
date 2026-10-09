import json
import os
import shutil
import subprocess
from pathlib import Path

import hcl2
import pytest
from click.testing import CliRunner

from terraforma.artifacts import checksum_document
from terraforma.cli import main
from terraforma.project import compile_project
from terraforma.terragrunt import terragrunt_artifacts, write_terragrunt_bundle
from tests.test_aws_placement import specification
from tests.test_vm_configuration_matrix import combined_spec


def parse_unit(content):
    return hcl2.loads(
        content, serialization_options=hcl2.utils.SerializationOptions(strip_string_quotes=True)
    )


@pytest.mark.parametrize("provider", ["aws", "azure", "gcp"])
@pytest.mark.parametrize("windows", [False, True])
def test_combined_units_preserve_effective_inputs_and_external_secrets(provider, windows):
    spec = combined_spec(provider, windows, False, False)
    result = compile_project(spec)
    files = terragrunt_artifacts({"dev": spec, "test": spec})
    modules = {name.split("/")[1] for name in files if name.startswith("modules/")}
    assert len(modules) == 1
    for unit in ("dev", "test"):
        config = parse_unit(files[f"units/{unit}/terragrunt.hcl"])
        expected = {
            name: value.replace("${", "$${").replace("%{", "%%{")
            if isinstance(value, str)
            else value
            for name, value in result["terraform_inputs"].items()
        }
        assert config["inputs"] == expected
        for name in result["required_secret_environment_variables"]:
            assert name.removeprefix("TF_VAR_") not in config["inputs"]
        assert json.loads(files[f"units/{unit}/terraforma.project.json"]) == result["specification"]
    assert files["SHA256SUMS.txt"] == checksum_document(
        {k: v for k, v in files.items() if k != "SHA256SUMS.txt"}
    )
    assert not any("backend" in name or "tfstate" in name for name in files)


def test_different_environment_answers_share_recipe_but_keep_values_separate():
    dev = specification(False, environment="dev", instance_type="t3.micro")
    prod = specification(False, environment="prod", instance_type="t3.large")
    files = terragrunt_artifacts({"dev": dev, "prod": prod})
    assert len([name for name in files if name.endswith("/main.tf")]) == 1
    assert parse_unit(files["units/dev/terragrunt.hcl"])["inputs"]["environment"] == "dev"
    assert parse_unit(files["units/prod/terragrunt.hcl"])["inputs"]["instance_type"] == "t3.large"


@pytest.mark.parametrize(
    "name", ["../prod", "Prod", "con", "aux", "lpt1", "dev/prod", "a" * 33, "", "x${run_cmd}"]
)
def test_reject_unsafe_unit_names(name):
    with pytest.raises(ValueError):
        terragrunt_artifacts({name: specification(False)})


def test_bundle_requires_fresh_destination_and_writes_exact_bytes(tmp_path):
    files = terragrunt_artifacts({"dev": specification(False)})
    destination = tmp_path / "bundle"
    write_terragrunt_bundle(files, destination)
    for name, content in files.items():
        assert (destination / name).read_bytes() == content.encode("utf-8")
    with pytest.raises(FileExistsError):
        write_terragrunt_bundle(files, destination)


def test_failed_write_removes_only_owned_bundle(tmp_path, monkeypatch):
    marker = tmp_path / "keep.txt"
    marker.write_text("existing user file", encoding="utf-8")

    def fail_sync(*args):
        raise OSError("Simulated disk failure")

    monkeypatch.setattr(os, "fsync", fail_sync)
    with pytest.raises(OSError, match="Simulated disk failure"):
        write_terragrunt_bundle(
            terragrunt_artifacts({"dev": specification(False)}), tmp_path / "bundle"
        )
    assert not (tmp_path / "bundle").exists()
    assert marker.read_text(encoding="utf-8") == "existing user file"


@pytest.mark.parametrize(
    "path", ["../outside", "/outside", "C:/outside", "units/../outside", "units\\outside"]
)
def test_writer_rejects_paths_before_creating_destination(tmp_path, path):
    with pytest.raises(ValueError):
        write_terragrunt_bundle({path: "content"}, tmp_path / "bundle")
    assert not (tmp_path / "bundle").exists()


def test_cli_exports_without_running_terraform(tmp_path, monkeypatch):
    def forbidden(*args, **kwargs):
        pytest.fail("Export must not execute infrastructure commands")

    monkeypatch.setattr(subprocess, "run", forbidden)
    source = tmp_path / "project.json"
    source.write_text(specification(False).model_dump_json(), encoding="utf-8")
    result = CliRunner().invoke(
        main,
        [
            "export-terragrunt",
            "--unit",
            f"dev={source}",
            "--unit",
            f"test={source}",
            "--dir",
            str(tmp_path / "bundle"),
        ],
    )
    assert result.exit_code == 0, result.output
    assert "No infrastructure commands ran" in result.output
    duplicate = CliRunner().invoke(
        main,
        [
            "export-terragrunt",
            "--unit",
            f"dev={source}",
            "--unit",
            f"dev={source}",
            "--dir",
            str(tmp_path / "duplicate"),
        ],
    )
    assert duplicate.exit_code == 1
    assert not (tmp_path / "duplicate").exists()


@pytest.mark.parametrize("provider", ["aws", "azure", "gcp"])
@pytest.mark.parametrize("windows", [False, True])
def test_native_terragrunt_evaluates_combined_inputs_without_cloud(tmp_path, provider, windows):
    if os.environ.get("TERRAFORMA_NATIVE_TESTS") != "1" or not shutil.which("terragrunt"):
        pytest.skip("Optional native Terragrunt verification")
    spec = combined_spec(provider, windows, False, False)
    files = terragrunt_artifacts({"dev": spec})
    destination = write_terragrunt_bundle(files, tmp_path / "bundle")
    result = subprocess.run(
        [
            shutil.which("terragrunt"),
            "render",
            "--config",
            str(destination / "units/dev/terragrunt.hcl"),
            "--json",
            "--tf-path",
            shutil.which("terraform"),
            "--log-disable",
        ],
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    )
    assert result.returncode == 0, result.stderr
    evaluated = json.loads(result.stdout)
    assert evaluated["inputs"] == compile_project(spec)["terraform_inputs"]
    assert Path(evaluated["terraform"]["source"]).resolve().is_dir()
    assert not evaluated.get("remote_state")
    assert not evaluated["dependency"]
    assert not evaluated["terraform"]["before_hook"]
    assert not evaluated["terraform"]["after_hook"]
