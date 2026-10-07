import io
import json
import zipfile

import hcl2
import pytest
from click.testing import CliRunner
from fastapi.testclient import TestClient

from terraforma.cli import main
from terraforma.generator import TerraformGenerator, WizardConfig
from terraforma.project import ProjectSpecification, compile_project, input_contract
from terraforma.web import create_app


def recipe(provider="aws", workload="static_site"):
    return WizardConfig(provider=provider, project_name="project-test", architecture_type=workload)


@pytest.mark.parametrize("provider", ["aws", "azure", "gcp"])
@pytest.mark.parametrize(
    "workload", ["single_web_server", "load_balanced_tier", "secure_database", "static_site"]
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
            recipe=recipe(), inputs={"index_html": '${file("private.txt")}%{if true}'}
        )
    )
    assert "$${file(" in result["files"]["variables.tf"]
    assert "%%{if true}" in result["files"]["variables.tf"]


def test_cli_specification_workflow_and_private_error(tmp_path):
    source = tmp_path / "project.json"
    source.write_text(
        json.dumps(
            ProjectSpecification(recipe=recipe(), inputs={"region": "us-west-2"}).model_dump()
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
        assert len(contract.json()["inputs"]) == 3
        specification = ProjectSpecification(
            recipe=recipe(), inputs={"region": "us-west-2"}
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
        recipe=recipe(), inputs={"region": "us-west-2"}
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
