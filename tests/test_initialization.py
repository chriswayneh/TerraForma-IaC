import json
import os
import shutil
import subprocess
from unittest.mock import Mock

import pytest
from fastapi.testclient import TestClient

from terraforma.cli import collect_recipe_inputs
from terraforma.generator import TerraformGenerator
from terraforma.hcl import value_hcl
from terraforma.initialization import read_initialization_file, validate_initialization_script
from terraforma.project import ProjectInputError, compile_project, input_contract
from terraforma.web import create_app
from tests.test_custom_images import specification
from tests.test_generator import assert_native_files

pytest_plugins = ["tests.test_generator"]

SHELL = '#!/bin/bash\nprintf "%s\\n" "review-marker $literal"\n'
POWERSHELL = 'Write-Output "review-marker $' + '{literal}"\n'


def initialized_spec(provider, windows=False, public=False, **changes):
    return specification(
        provider,
        windows,
        custom=False,
        public=public,
        **{
            "enable_initialization": True,
            "initialization_script": POWERSHELL if windows else SHELL,
            "confirm_initialization_review": True,
            **changes,
        },
    )


@pytest.mark.parametrize("provider", ["aws", "azure", "gcp"])
@pytest.mark.parametrize("windows", [False, True])
def test_initialization_roundtrip_has_no_host_execution_and_summary_hides_content(
    provider, windows, monkeypatch
):
    monkeypatch.setattr(
        "subprocess.run", lambda *a, **k: pytest.fail("Generation must not execute scripts.")
    )
    spec = initialized_spec(provider, windows)
    result = compile_project(spec)
    assert value_hcl(spec.inputs["initialization_script"]) in result["files"]["variables.tf"]
    assert "review-marker" not in json.dumps(result["choice_summary"])
    with TestClient(create_app(), base_url="http://127.0.0.1") as client:
        headers = {"X-TerraForma-Token": client.get("/api/session").json()["token"]}
        response = client.post(
            "/api/projects/import", headers=headers, content=spec.model_dump_json()
        )
    assert response.status_code == 200, response.text
    assert response.json()["specification"]["inputs"] == spec.inputs


@pytest.mark.parametrize("provider", ["aws", "azure", "gcp"])
@pytest.mark.parametrize("windows", [False, True])
def test_generated_guide_reports_initialization_without_echoing_script(provider, windows):
    spec = initialized_spec(provider, windows)
    with TestClient(create_app(), base_url="http://127.0.0.1") as client:
        headers = {"X-TerraForma-Token": client.get("/api/session").json()["token"]}
        response = client.post("/api/generate", headers=headers, json=spec.model_dump())
    assert response.status_code == 200, response.text
    project = response.json()
    text = json.dumps({"guide": project["guide"], "notes": project["notes"]})
    assert "review-marker" not in text
    assert "Reviewed initialization script" in text
    assert "no application startup script" not in text
    assert "initialization is left" not in text


@pytest.mark.parametrize("provider", ["aws", "azure", "gcp"])
@pytest.mark.parametrize("windows", [False, True])
@pytest.mark.parametrize(
    "changes,field",
    [
        ({"confirm_initialization_review": False}, "confirm_initialization_review"),
        ({"initialization_script": ""}, "initialization_script"),
        ({"enable_initialization": False}, "enable_initialization"),
        ({"initialization_script": "secret-marker\x00"}, "initialization_script"),
        ({"initialization_script": "secret-marker" * 400}, "initialization_script"),
    ],
)
def test_initialization_rejects_missing_review_inactive_or_invalid_content(
    provider, windows, changes, field
):
    with pytest.raises(ProjectInputError) as error:
        compile_project(initialized_spec(provider, windows, **changes))
    assert error.value.field == field
    assert "secret-marker" not in str(error.value)


@pytest.mark.parametrize(
    "windows,script",
    [
        (False, "#cloud-config\npackages: []\n"),
        (False, "#!/usr/bin/env bash\ntrue\n"),
        (False, "#!/bin/bash"),
        (True, "#!/bin/bash\ntrue\n"),
        (True, "<PowerShell>Write-Output 'example'</PowerShell>"),
        (True, "<persist>true</persist>"),
    ],
)
def test_initialization_format_matches_selected_guest(windows, script):
    with pytest.raises(ProjectInputError) as error:
        compile_project(initialized_spec("aws", windows, initialization_script=script))
    assert error.value.field == "initialization_script"


def test_file_loader_decodes_bom_and_preserves_utf8_byte_boundary(tmp_path):
    file = tmp_path / "reviewed.sh"
    file.write_bytes(b"\xef\xbb\xbf" + SHELL.encode())
    assert read_initialization_file(file) == SHELL
    validate_initialization_script("a" * 4096)
    validate_initialization_script("é" * 2048)
    with pytest.raises(ValueError):
        validate_initialization_script("é" * 2049)
    for data in (b"a" * 4097, b"\xff", b"\x00", "\ufffd".encode()):
        file.write_bytes(data)
        with pytest.raises((ValueError, UnicodeError)):
            read_initialization_file(file)
    with pytest.raises((ValueError, OSError)):
        read_initialization_file(tmp_path)


@pytest.mark.parametrize("provider", ["aws", "azure", "gcp"])
@pytest.mark.parametrize("windows", [False, True])
def test_terminal_loads_content_from_regular_file_without_execution(
    provider, windows, tmp_path, monkeypatch
):
    spec = initialized_spec(provider, windows)
    file = tmp_path / ("reviewed.ps1" if windows else "reviewed.sh")
    file.write_bytes(spec.inputs["initialization_script"].encode("utf-8"))
    fields = {field["label"]: field for field in input_contract(spec.recipe)}

    def prompt(message, **options):
        if message == "Trusted initialization file path:":
            return Mock(ask=lambda: str(file))
        field = fields[message.rstrip("?:")]
        answer = spec.inputs.get(field["name"], field["default"])
        return Mock(ask=lambda: str(answer) if field["kind"] == "integer" else answer)

    for kind in ("text", "confirm", "select"):
        monkeypatch.setattr(f"terraforma.cli.questionary.{kind}", prompt)
    monkeypatch.setattr(
        "subprocess.run", lambda *a, **k: pytest.fail("Loading must not execute scripts.")
    )
    collected = collect_recipe_inputs(spec.recipe)
    assert collected.inputs["initialization_script"] == file.read_text(encoding="utf-8")
    compile_project(collected)


@pytest.mark.parametrize("provider", ["aws", "azure", "gcp"])
@pytest.mark.parametrize("windows", [False, True])
@pytest.mark.parametrize("public", [False, True])
@pytest.mark.parametrize("enabled", [False, True])
def test_native_initialization_combinations(native_directories, provider, windows, public, enabled):
    spec = (
        initialized_spec(provider, windows, public)
        if enabled
        else specification(provider, windows, custom=False, public=public)
    )
    assert_native_files(
        native_directories[provider],
        compile_project(spec)["files"],
    )


@pytest.mark.parametrize("windows", [False, True])
def test_native_aws_userdata_decodes_literal_script_without_interpolation(tmp_path, windows):
    if os.environ.get("TERRAFORMA_NATIVE_TESTS") != "1":
        pytest.skip("Set TERRAFORMA_NATIVE_TESTS=1 to run native checks.")
    from terraforma.initialization import aws_initialization_payload

    spec = initialized_spec("aws", windows)
    generator = TerraformGenerator(spec.recipe)
    generator.generate()
    variables = [
        variable.render()
        for variable in generator.variables
        if variable.labels[0]
        in {"enable_initialization", "initialization_script", "confirm_initialization_review"}
    ]
    (tmp_path / "main.tf").write_text(
        "\n".join(variables)
        + f"\nlocals {{ payload = {aws_initialization_payload(windows).value} }}\n",
        encoding="utf-8",
    )
    (tmp_path / "terraform.tfvars.json").write_text(
        json.dumps(
            {
                name: spec.inputs[name]
                for name in (
                    "enable_initialization",
                    "initialization_script",
                    "confirm_initialization_review",
                )
            }
        ),
        encoding="utf-8",
    )
    environment = {
        key: value
        for key, value in os.environ.items()
        if not key.startswith(("TF_VAR_", "TF_CLI_ARGS"))
    }
    result = subprocess.run(
        [shutil.which("terraform"), "console", "-no-color"],
        cwd=tmp_path,
        env=environment,
        input="jsonencode(base64decode(local.payload))\n",
        capture_output=True,
        text=True,
        timeout=15,
        check=False,
    )
    assert result.returncode == 0, result.stderr
    expected = spec.inputs["initialization_script"]
    if windows:
        expected = f"<powershell>\n{expected}\n</powershell>"
    assert json.loads(json.loads(result.stdout)) == expected


@pytest.mark.parametrize("windows", [False, True])
@pytest.mark.parametrize(
    "change,valid",
    [
        ({}, True),
        ({"confirm_initialization_review": False}, False),
        ({"initialization_script": ""}, False),
        ({"enable_initialization": False}, False),
        (
            {
                "enable_initialization": False,
                "initialization_script": "",
                "confirm_initialization_review": False,
            },
            True,
        ),
        ({"initialization_script": "a" * 4097}, False),
        ({"initialization_script": "-----BEGIN PRIVATE KEY-----"}, False),
        ({"initialization_script": "\ufffd"}, False),
    ],
)
def test_native_initialization_guard_without_cloud_providers(tmp_path, windows, change, valid):
    if os.environ.get("TERRAFORMA_NATIVE_TESTS") != "1":
        pytest.skip("Set TERRAFORMA_NATIVE_TESTS=1 to run native checks.")
    from terraforma.hcl import block, ref
    from terraforma.initialization import initialization_precondition

    spec = initialized_spec("aws", windows, **change)
    generator = TerraformGenerator(spec.recipe)
    generator.generate()
    names = {"enable_initialization", "initialization_script", "confirm_initialization_review"}
    variables = [item.render() for item in generator.variables if item.labels[0] in names]
    resource = block(
        "resource",
        "terraform_data",
        "guard",
        input=ref("var.enable_initialization"),
        children=[block("lifecycle", children=[initialization_precondition(windows)])],
    )
    (tmp_path / "main.tf").write_text(
        "\n".join(variables) + "\n" + resource.render(), encoding="utf-8"
    )
    (tmp_path / "terraform.tfvars.json").write_text(
        json.dumps({name: spec.inputs[name] for name in names}), encoding="utf-8"
    )
    environment = {
        key: value
        for key, value in os.environ.items()
        if not key.startswith(("TF_VAR_", "TF_CLI_ARGS"))
    }
    executable = shutil.which("terraform")
    assert executable
    initialized = subprocess.run(
        [executable, "init", "-backend=false", "-input=false", "-no-color"],
        cwd=tmp_path,
        env=environment,
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    )
    assert initialized.returncode == 0, initialized.stdout + initialized.stderr
    result = subprocess.run(
        [executable, "plan", "-input=false", "-no-color", "-refresh=false"],
        cwd=tmp_path,
        env=environment,
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    )
    assert (result.returncode == 0) == valid, result.stdout + result.stderr
    assert not (tmp_path / "terraform.tfstate").exists()


def test_native_azure_protected_command_encodes_script_and_fits_inline_limit(tmp_path):
    if os.environ.get("TERRAFORMA_NATIVE_TESTS") != "1":
        pytest.skip("Set TERRAFORMA_NATIVE_TESTS=1 to run native checks.")
    import base64

    script = (POWERSHELL + "# " + "a" * 4096)[:4096]
    spec = initialized_spec("azure", True, initialization_script=script)
    generator = TerraformGenerator(spec.recipe)
    generator.generate()
    extension = next(
        resource
        for resource in generator.main
        if tuple(resource.labels) == ("azurerm_virtual_machine_extension", "initialization")
    )
    expression = extension.attributes["protected_settings"].value
    (tmp_path / "main.tf").write_text(
        'variable "initialization_script" { type = string }\n'
        + f"locals {{ settings = {expression} }}\n",
        encoding="utf-8",
    )
    (tmp_path / "terraform.tfvars.json").write_text(
        json.dumps({"initialization_script": script}), encoding="utf-8"
    )
    environment = {
        key: value
        for key, value in os.environ.items()
        if not key.startswith(("TF_VAR_", "TF_CLI_ARGS"))
    }
    result = subprocess.run(
        [shutil.which("terraform"), "console", "-no-color"],
        cwd=tmp_path,
        env=environment,
        input="local.settings\n",
        capture_output=True,
        text=True,
        timeout=15,
        check=False,
    )
    assert result.returncode == 0, result.stderr
    settings = json.loads(json.loads(result.stdout))
    command = settings["commandToExecute"]
    assert base64.b64encode(script.encode()).decode() in command
    assert "review-marker" not in command
    assert len(command) < 8191
    assert "$ErrorActionPreference = 'Stop'" in command
    assert set(settings) == {"commandToExecute"}
