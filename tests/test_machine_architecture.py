import itertools
import shutil
import subprocess

import pytest
from click.testing import CliRunner
from fastapi.testclient import TestClient

from terraforma.cli import main
from terraforma.generator import TerraformGenerator
from terraforma.hcl import value_hcl
from terraforma.machine_architecture import (
    MACHINE_SIZE_FIELDS,
    validate_machine_architecture,
)
from terraforma.project import ProjectInputError, compile_project, input_contract, validate_answer
from terraforma.terragrunt import terragrunt_artifacts
from terraforma.web import create_app
from tests.test_custom_images import specification
from tests.test_generator import assert_native_files

pytest_plugins = ["tests.test_generator"]

ARM_CASES = {
    "aws": [
        "t4g.small",
        "m6gd.large",
        "c7gn.large",
        "r8gb.large",
        "g5g.xlarge",
        "im4gn.large",
        "m9g.large",
        "p6e-gb200.36xlarge",
    ],
    "azure": [
        "Standard_D2ps_v5",
        "Standard_D2pds_v6",
        "Standard_B2pts_v2",
        "Standard_E2pds_v6",
        "Standard_D16-4ps_v6",
        "standard_d2ps_v5",
        "STANDARD_D2PDS_V6",
    ],
    "gcp": [
        "t2a-standard-1",
        "c4a-standard-2",
        "n4a-standard-2",
        "a4x-highgpu-4g",
        "a4x-maxgpu-4g",
    ],
}
X86_OR_UNKNOWN_CASES = {
    "aws": [
        "t3a.small",
        "t8i.small",
        "m8a.large",
        "c7i.large",
        "g5.xlarge",
        "r7iz.large",
        "future.large",
        "m6gextra.large",
    ],
    "azure": [
        "Standard_D2s_v5",
        "Standard_D2as_v6",
        "Standard_NP20s",
        "Standard_NC24ads_A100_v4",
        "Standard_HB120-16rs_v3",
        "Standard_Future2_v1",
    ],
    "gcp": [
        "e2-micro",
        "t2d-standard-1",
        "n4d-standard-2",
        "a4-highgpu-8g",
        "future-standard-1",
        "c4ax-standard-2",
    ],
}


@pytest.mark.parametrize("provider,size", [(p, s) for p, sizes in ARM_CASES.items() for s in sizes])
@pytest.mark.parametrize("windows,custom", list(itertools.product([False, True], repeat=2)))
def test_known_arm_sizes_fail_before_export(provider, size, windows, custom):
    name = MACHINE_SIZE_FIELDS[provider]
    spec = specification(provider, windows, custom=custom, **{name: size})
    with pytest.raises(ProjectInputError) as error:
        compile_project(spec)
    assert error.value.field == name
    assert size not in str(error.value)
    with pytest.raises(ProjectInputError):
        terragrunt_artifacts({"dev": spec})


@pytest.mark.parametrize(
    "provider,size", [(p, s) for p, sizes in X86_OR_UNKNOWN_CASES.items() for s in sizes]
)
def test_guard_does_not_invent_compatibility_for_other_sizes(provider, size):
    validate_machine_architecture(MACHINE_SIZE_FIELDS[provider], size)
    spec = specification(provider, False, **{MACHINE_SIZE_FIELDS[provider]: size})
    result = compile_project(spec)
    assert result["target"]["identity_verified"] is False


@pytest.mark.parametrize("provider", list(MACHINE_SIZE_FIELDS))
@pytest.mark.parametrize("windows", [False, True])
def test_shared_contract_and_api_reject_known_arm_fields(provider, windows):
    name = MACHINE_SIZE_FIELDS[provider]
    spec = specification(provider, windows)
    field = next(item for item in input_contract(spec.recipe) if item["name"] == name)
    with pytest.raises(ProjectInputError) as error:
        validate_answer(field, ARM_CASES[provider][0])
    assert error.value.field == name
    spec.inputs[name] = ARM_CASES[provider][0]
    with TestClient(create_app(), base_url="http://127.0.0.1") as client:
        headers = {"X-TerraForma-Token": client.get("/api/session").json()["token"]}
        for endpoint in ("compile", "import"):
            response = client.post(
                f"/api/projects/{endpoint}", json=spec.model_dump(), headers=headers
            )
            assert response.status_code == 422
            assert ARM_CASES[provider][0] not in response.text


@pytest.mark.parametrize("provider", list(MACHINE_SIZE_FIELDS))
@pytest.mark.parametrize("windows", [False, True])
def test_cli_rejects_arm_before_writing_artifacts(tmp_path, provider, windows):
    spec = specification(
        provider, windows, **{MACHINE_SIZE_FIELDS[provider]: ARM_CASES[provider][0]}
    )
    path = tmp_path / "project.json"
    path.write_text(spec.model_dump_json(), encoding="utf-8")
    target = tmp_path / "output"
    result = CliRunner().invoke(main, ["generate", "--spec", str(path), "--dir", str(target)])
    assert result.exit_code == 1
    assert MACHINE_SIZE_FIELDS[provider] in result.output
    assert ARM_CASES[provider][0] not in result.output
    assert not target.exists()


@pytest.mark.parametrize("provider", list(MACHINE_SIZE_FIELDS))
@pytest.mark.parametrize("windows", [False, True])
def test_native_architecture_validations(native_directories, provider, windows):
    assert_native_files(
        native_directories[provider], compile_project(specification(provider, windows))["files"]
    )


@pytest.mark.parametrize("provider", list(MACHINE_SIZE_FIELDS))
def test_native_variable_validation_blocks_arm_overrides_without_providers(
    native_directories, provider
):
    directory = native_directories[provider] / "architecture-guard"
    directory.mkdir(exist_ok=True)
    generator = TerraformGenerator(specification(provider).recipe)
    generator.generate()
    name = MACHINE_SIZE_FIELDS[provider]
    variable = next(item for item in generator.variables if item.labels[0] == name)
    (directory / "main.tf").write_text(variable.render(), encoding="utf-8")
    runs = []
    for index, size in enumerate(ARM_CASES[provider]):
        runs.append(
            f'run "reject_arm_{index}" {{\n command = plan\n variables {{ {name} = {value_hcl(size)} }}\n expect_failures = [var.{name}]\n}}'
        )
    for index, size in enumerate(X86_OR_UNKNOWN_CASES[provider]):
        runs.append(
            f'run "leave_other_size_unverified_{index}" {{\n command = plan\n variables {{ {name} = {value_hcl(size)} }}\n}}'
        )
    (directory / "architecture.tftest.hcl").write_text("\n\n".join(runs), encoding="utf-8")
    init = subprocess.run(
        [shutil.which("terraform"), "init", "-backend=false", "-input=false", "-no-color"],
        cwd=directory,
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    )
    assert init.returncode == 0, init.stdout + init.stderr
    result = subprocess.run(
        [shutil.which("terraform"), "test", "-no-color"],
        cwd=directory,
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    )
    assert result.returncode == 0, result.stdout + result.stderr
