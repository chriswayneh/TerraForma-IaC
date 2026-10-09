"""Generated Terraform must already be in ``terraform fmt`` canonical form."""

import itertools
import shutil
import subprocess
from pathlib import Path

import pytest

from terraforma.generator import TerraformGenerator, WizardConfig
from terraforma.hcl import block, ref
from terraforma.project import compile_project, load_specification

PROVIDERS = ["aws", "azure", "gcp"]
WORKLOADS = [
    "virtual_machine",
    "windows_virtual_machine",
    "single_web_server",
    "load_balanced_tier",
    "secure_database",
    "static_site",
]
EXAMPLES = sorted((Path(__file__).parents[1] / "examples").rglob("*.project.json"))


def test_attributes_align_equals_like_terraform_fmt():
    rendered = block(
        "resource",
        "aws_instance",
        "this",
        ami=ref("var.ami"),
        instance_type="t3.micro",
        children=[block("metadata_options", http_tokens="required", http_endpoint="enabled")],
    ).render()
    assert rendered == (
        'resource "aws_instance" "this" {\n'
        "  ami           = var.ami\n"
        '  instance_type = "t3.micro"\n'
        "  metadata_options {\n"
        '    http_tokens   = "required"\n'
        '    http_endpoint = "enabled"\n'
        "  }\n"
        "}"
    )


def test_multiline_values_follow_terraform_fmt_alignment_runs():
    rendered = block(
        "locals",
        a=1,
        long_name=ref("<<EOT\nx\nEOT"),
        bb=2,
        c=ref("{\n    x = 1\n  }"),
        ddd=3,
    ).render()
    assert rendered.splitlines()[1:] == [
        "  a         = 1",
        "  long_name = <<EOT",
        "x",
        "EOT",
        "  bb        = 2",
        "  c = {",
        "    x = 1",
        "  }",
        "  ddd = 3",
        "}",
    ]


@pytest.mark.skipif(shutil.which("terraform") is None, reason="terraform is not on PATH")
def test_multiline_alignment_matches_terraform_fmt(tmp_path):
    source = block(
        "locals",
        a=1,
        long_name=ref("<<EOT\nx\nEOT"),
        bb=2,
        c=ref("{\n    x = 1\n  }"),
        ddd=3,
    ).render()
    (tmp_path / "main.tf").write_text(source + "\n", encoding="utf-8")
    result = subprocess.run(
        ["terraform", "fmt", "-check", "-no-color", str(tmp_path)],
        capture_output=True,
        text=True,
        timeout=60,
        check=False,
    )
    assert result.returncode == 0, result.stdout + result.stderr


def _write(root: Path, name: str, files: dict[str, str]) -> None:
    target = root / name
    target.mkdir(parents=True)
    for filename, text in files.items():
        if filename.endswith(".tf"):
            (target / filename).write_text(text, encoding="utf-8")


@pytest.mark.skipif(shutil.which("terraform") is None, reason="terraform is not on PATH")
def test_every_recipe_and_example_passes_terraform_fmt_check(tmp_path):
    combinations = list(itertools.product(PROVIDERS, WORKLOADS, [False, True], [True, False]))
    assert len({c[:3] for c in combinations}) == 36
    for provider, workload, public, encryption in combinations:
        files = TerraformGenerator(
            WizardConfig(
                provider=provider,
                project_name="fmt-check",
                architecture_type=workload,
                is_public=public,
                enable_encryption=encryption,
            )
        ).generate()
        name = f"{provider}-{workload}-{'pub' if public else 'priv'}-{'enc' if encryption else 'noenc'}"
        _write(tmp_path, name, files)
    assert EXAMPLES, "expected example specifications under examples/"
    for path in EXAMPLES:
        _write(tmp_path, "example-" + path.name, compile_project(load_specification(path))["files"])
    result = subprocess.run(
        ["terraform", "fmt", "-check", "-recursive", "-list=true", "-no-color", str(tmp_path)],
        capture_output=True,
        text=True,
        timeout=120,
        check=False,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    assert result.stdout.strip() == ""
