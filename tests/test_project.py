import io
import json
import zipfile

import hcl2
import pytest
from click.testing import CliRunner
from fastapi.testclient import TestClient

from terraforma import __version__
from terraforma.cli import main
from terraforma.generator import TerraformGenerator, WizardConfig
from terraforma.project import ProjectSpecification, compile_project, input_contract
from terraforma.web import create_app
from tests.hcl_text import unaligned


def recipe(provider="aws", workload="static_site"):
    return WizardConfig(provider=provider, project_name="project-test", architecture_type=workload)


@pytest.mark.parametrize("version", ["0.3.0", "0.3.0.dev0"])
def test_release_preserves_saved_development_specifications(version):
    specification = ProjectSpecification(
        recipe=recipe(), template_version=version, inputs={"aws_account_id": "123456789012"}
    )
    result = compile_project(specification)
    assert result["specification"]["template_version"] == version
    assert result["receipt"]["template_version"] == version
    assert result["receipt"]["generator_version"] == __version__


def test_new_specification_defaults_to_release_template():
    assert ProjectSpecification(recipe=recipe()).template_version == __version__


def test_browser_import_round_trip_preserves_answers_and_export():
    specification = ProjectSpecification(
        recipe=recipe("aws", "single_web_server"),
        inputs={
            "aws_account_id": "123456789012",
            "region": "us-west-2",
            "instance_type": "t3.small",
            "boot_disk_size_gb": 100,
            "boot_disk_type": "gp2",
        },
    )
    with TestClient(create_app(), base_url="http://127.0.0.1") as client:
        headers = {"X-TerraForma-Token": client.get("/api/session").json()["token"]}
        original = client.post("/api/download", headers=headers, json=specification.model_dump())
        with zipfile.ZipFile(io.BytesIO(original.content)) as archive:
            manifest = archive.read("terraforma.project.json")
            variables = archive.read("variables.tf").decode()
        imported = client.post("/api/projects/import", headers=headers, content=manifest)
        assert imported.status_code == 200
        assert imported.json()["specification"] == specification.model_dump()
        assert imported.json()["files"]["variables.tf"] == variables
        assert imported.json()["capabilities"]["account_checks"] == "unverified"
        assert imported.json()["target"] == {
            "provider": "aws",
            "account_reference": "123456789012",
            "identity_verified": False,
            "environment": "development",
        }


@pytest.mark.parametrize(
    "workload", ["single_web_server", "load_balanced_tier", "secure_database", "static_site"]
)
def test_aws_recipes_bind_explicit_account_with_shared_identifier_constraint(workload):
    config = recipe("aws", workload)
    generated = compile_project(
        ProjectSpecification(recipe=config, inputs={"aws_account_id": "123456789012"})
    )
    assert "allowed_account_ids = [var.aws_account_id]" in unaligned(generated["files"]["main.tf"])
    account = next(item for item in input_contract(config) if item["name"] == "aws_account_id")
    assert account["required"] and account["default"] is None
    assert account["pattern"] == "^[0-9]{12}$"
    assert 'can(regex("^[0-9]{12}$", var.aws_account_id))' in generated["files"]["variables.tf"]


@pytest.mark.parametrize("value", ["123", "12345678901x", "1234567890123", 123456789012, True])
def test_invalid_aws_target_account_is_rejected(value):
    with pytest.raises((ValueError, TypeError)):
        compile_project(ProjectSpecification(recipe=recipe(), inputs={"aws_account_id": value}))


def test_aws_specification_requires_explicit_target_account():
    with pytest.raises(ValueError, match="aws_account_id"):
        compile_project(ProjectSpecification(recipe=recipe()))


@pytest.mark.parametrize(
    "payload",
    [
        b'{"schema_version":1,"schema_version":1}',
        b'{"schema_version":NaN}',
        b'{"schema_version":1,"inputs":{"index_html":"private-marker"}}',
        b"\xff\xfe\x00",
        json.dumps({"recipe": recipe().model_dump(), "template_version": "0.2.0"}).encode(),
        json.dumps(
            {"recipe": recipe().model_dump(), "inputs": {"database_password": "private-marker"}}
        ).encode(),
    ],
)
def test_import_rejects_invalid_files_without_disclosing_content(payload):
    with TestClient(create_app(), base_url="http://127.0.0.1") as client:
        headers = {"X-TerraForma-Token": client.get("/api/session").json()["token"]}
        result = client.post("/api/projects/import", headers=headers, content=payload)
        assert result.status_code == 422
        assert "private-marker" not in result.text


def test_import_is_bounded_and_requires_local_session():
    with TestClient(create_app(), base_url="http://127.0.0.1") as client:
        assert client.post("/api/projects/import", content=b"{}").status_code == 403
        headers = {"X-TerraForma-Token": client.get("/api/session").json()["token"]}
        assert (
            client.post("/api/projects/import", headers=headers, content=b" " * 65537).status_code
            == 413
        )


@pytest.mark.parametrize("provider", ["aws", "azure", "gcp"])
@pytest.mark.parametrize(
    "workload",
    [
        "virtual_machine",
        "single_web_server",
        "load_balanced_tier",
        "secure_database",
        "static_site",
    ],
)
def test_contract_matches_every_generated_variable(provider, workload):
    config = recipe(provider, workload)
    generator = TerraformGenerator(config)
    files = generator.generate()
    variables = [
        {name.strip('"'): attributes for name, attributes in block.items()}
        for block in hcl2.loads(files["variables.tf"])["variable"]
    ]
    names = {name for block in variables for name in block}
    contract = input_contract(config)
    assert {item["name"] for item in contract} == names
    for item in contract:
        definition = next(block[item["name"]] for block in variables if item["name"] in block)
        assert item["required"] == ("default" not in definition)
        assert item["sensitive"] == definition.get("sensitive", False)
        if item["sensitive"]:
            assert item["default"] is None
            assert item["kind"] == "external_secret"


def test_compilation_answers_required_inputs_and_keeps_secrets_external():
    specification = ProjectSpecification(
        recipe=recipe("azure", "secure_database"),
        inputs={"subscription_id": "12345678-1234-1234-1234-123456789abc", "location": "westus2"},
        secret_references={"database_password": "TF_VAR_database_password"},
    )
    result = compile_project(specification)
    variables = hcl2.loads(result["files"]["variables.tf"])["variable"]
    lookup = {
        name.strip('"'): attributes for block in variables for name, attributes in block.items()
    }
    for attributes in lookup.values():
        if isinstance(attributes.get("default"), str) and attributes["default"].startswith('"'):
            attributes["default"] = json.loads(attributes["default"])
    assert lookup["location"]["default"] == "westus2"
    assert lookup["subscription_id"]["default"] == specification.inputs["subscription_id"]
    assert "default" not in lookup["database_password"]
    assert result["required_secret_environment_variables"] == ["TF_VAR_database_password"]
    assert result["target"] == {
        "provider": "azure",
        "account_reference": specification.inputs["subscription_id"],
        "identity_verified": False,
        "environment": "development",
    }


@pytest.mark.parametrize(
    "inputs",
    [
        {"subscription_id": "invalid"},
        {"subscription_id": "12345678-1234-1234-1234-123456789abc", "database_password": "secret"},
        {"unknown": "value"},
        {"project_name": "different-name"},
    ],
)
def test_invalid_and_secret_inputs_are_rejected(inputs):
    with pytest.raises(ValueError):
        compile_project(
            ProjectSpecification(recipe=recipe("azure", "secure_database"), inputs=inputs)
        )


def test_missing_inputs_and_cross_region_zone_are_rejected():
    with pytest.raises(ValueError, match="missing"):
        compile_project(ProjectSpecification(recipe=recipe("gcp")))
    with pytest.raises(ValueError, match="zone"):
        compile_project(
            ProjectSpecification(
                recipe=recipe("gcp", "single_web_server"),
                inputs={"gcp_project_id": "my-project", "region": "europe-west1"},
            )
        )


def test_user_strings_remain_literal_hcl():
    result = compile_project(
        ProjectSpecification(
            recipe=recipe(),
            inputs={
                "aws_account_id": "123456789012",
                "index_html": '${file("private.txt")}%{if true}',
            },
        )
    )
    assert "$${file(" in result["files"]["variables.tf"]
    assert "%%{if true}" in result["files"]["variables.tf"]


@pytest.mark.parametrize(
    "provider,inputs",
    [
        (
            "aws",
            {
                "aws_account_id": "123456789012",
                "instance_type": "t3.small",
                "boot_disk_size_gb": 100,
                "boot_disk_type": "gp2",
            },
        ),
        (
            "azure",
            {
                "subscription_id": "12345678-1234-1234-1234-123456789abc",
                "ssh_public_key": "ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAIAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA",
                "vm_size": "Standard_B2s",
                "boot_disk_size_gb": 100,
                "boot_disk_type": "Premium_LRS",
            },
        ),
        (
            "gcp",
            {
                "gcp_project_id": "my-project",
                "machine_type": "e2-medium",
                "boot_disk_size_gb": 100,
                "boot_disk_type": "pd-ssd",
            },
        ),
    ],
)
def test_compute_dimensions_are_typed_and_configurable(provider, inputs):
    result = compile_project(
        ProjectSpecification(recipe=recipe(provider, "single_web_server"), inputs=inputs)
    )
    assert "default = 100" in unaligned(result["files"]["variables.tf"])
    assert "var.boot_disk_size_gb" in result["files"]["main.tf"]
    assert "var.boot_disk_type" in result["files"]["main.tf"]
    definition = next(
        item for item in result["input_contract"] if item["name"] == "boot_disk_size_gb"
    )
    assert definition["type"] == "number"
    assert definition["kind"] == "integer"
    assert definition["maximum"] == 2048
    assert "floor(var.boot_disk_size_gb)" in result["files"]["variables.tf"]


@pytest.mark.parametrize("value", [19, 2049, "100", True, 100.5])
def test_disk_limits_and_types_reject_invalid_inputs(value):
    with pytest.raises(ValueError):
        compile_project(
            ProjectSpecification(
                recipe=recipe("aws", "single_web_server"), inputs={"boot_disk_size_gb": value}
            )
        )


def test_unsupported_disk_classes_are_not_silently_used():
    with pytest.raises(ValueError):
        compile_project(
            ProjectSpecification(
                recipe=recipe("aws", "single_web_server"), inputs={"boot_disk_type": "io1"}
            )
        )


def test_boolean_schema_version_is_rejected():
    with pytest.raises(ValueError):
        ProjectSpecification(schema_version=True, recipe=recipe())


def test_cli_specification_workflow_and_private_error(tmp_path):
    source = tmp_path / "project.json"
    source.write_text(
        json.dumps(
            ProjectSpecification(
                recipe=recipe(), inputs={"aws_account_id": "123456789012", "region": "us-west-2"}
            ).model_dump()
        )
    )
    runner = CliRunner()
    contract = runner.invoke(main, ["project-inputs", "--spec", str(source)])
    assert contract.exit_code == 0
    assert any(item["name"] == "region" for item in json.loads(contract.output))
    destination = tmp_path / "generated"
    result = runner.invoke(main, ["generate", "--spec", str(source), "--dir", str(destination)])
    assert result.exit_code == 0
    assert "us-west-2" in (destination / "variables.tf").read_text()
    repeated = runner.invoke(main, ["generate", "--spec", str(source), "--dir", str(destination)])
    assert repeated.exit_code != 0
    source.write_text(
        json.dumps(
            {"schema_version": 99, "recipe": recipe().model_dump(), "private": "do-not-echo"}
        )
    )
    failed = runner.invoke(
        main, ["generate", "--spec", str(source), "--dir", str(tmp_path / "bad")]
    )
    assert failed.exit_code != 0
    assert "do-not-echo" not in failed.output


def test_api_contract_compilation_and_private_errors():
    with TestClient(create_app(), base_url="http://127.0.0.1") as client:
        headers = {"X-TerraForma-Token": client.get("/api/session").json()["token"]}
        contract = client.post("/api/input-contract", json=recipe().model_dump(), headers=headers)
        assert contract.status_code == 200
        assert len(contract.json()["inputs"]) == 5
        specification = ProjectSpecification(
            recipe=recipe(), inputs={"aws_account_id": "123456789012", "region": "us-west-2"}
        ).model_dump()
        response = client.post("/api/projects/compile", json=specification, headers=headers)
        assert response.status_code == 200
        assert "us-west-2" in response.json()["files"]["variables.tf"]
        specification["private"] = "do-not-echo"
        rejected = client.post("/api/projects/compile", json=specification, headers=headers)
        assert rejected.status_code == 422
        assert "do-not-echo" not in rejected.text
        assert client.post("/api/input-contract", json=recipe().model_dump()).status_code == 403


def test_configured_download_and_validation_preserve_inputs(monkeypatch):
    specification = ProjectSpecification(
        recipe=recipe(), inputs={"aws_account_id": "123456789012", "region": "us-west-2"}
    ).model_dump()
    captured = {}

    def validate(sandbox):
        captured.update(sandbox.generated_files)
        return {"is_valid": True, "errors": [], "logs": ""}

    monkeypatch.setattr("terraforma.web.ValidationSandbox.validate", validate)
    with TestClient(create_app(), base_url="http://127.0.0.1") as client:
        headers = {"X-TerraForma-Token": client.get("/api/session").json()["token"]}
        generated = client.post("/api/generate", json=specification, headers=headers)
        assert generated.status_code == 200
        assert generated.json()["specification"]["inputs"]["region"] == "us-west-2"
        downloaded = client.post("/api/download", json=specification, headers=headers)
        assert downloaded.status_code == 200
        with zipfile.ZipFile(io.BytesIO(downloaded.content)) as archive:
            assert "us-west-2" in archive.read("variables.tf").decode()
            assert (
                json.loads(archive.read("terraforma.project.json"))["inputs"]["region"]
                == "us-west-2"
            )
        validated = client.post("/api/validate", json={"config": specification}, headers=headers)
        assert validated.status_code == 200
        assert "us-west-2" in captured["variables.tf"]
