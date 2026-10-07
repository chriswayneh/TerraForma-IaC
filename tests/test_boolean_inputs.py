import io
import json
import zipfile
from unittest.mock import Mock

import pytest
from click.testing import CliRunner
from fastapi.testclient import TestClient

from terraforma.cli import main
from terraforma.generator import WizardConfig
from terraforma.project import ProjectSpecification, compile_project, input_contract
from terraforma.web import create_app


@pytest.mark.parametrize("enabled", [False, True])
@pytest.mark.parametrize("workload", ["virtual_machine", "single_web_server", "load_balanced_tier"])
def test_monitoring_boolean_survives_compilation_export_and_import(enabled, workload):
    config = WizardConfig(provider="aws", project_name="monitor-test", architecture_type=workload)
    inputs = {"aws_account_id": "123456789012", "detailed_monitoring": enabled}
    if workload == "virtual_machine":
        inputs["ssh_public_key"] = (
            "ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAIAEBAQEBAQEBAQEBAQEBAQEBAQEBAQEBAQEBAQEBAQEB"
        )
    specification = ProjectSpecification(recipe=config, inputs=inputs)
    project = compile_project(specification)
    field = next(item for item in input_contract(config) if item["name"] == "detailed_monitoring")
    assert field["kind"] == "boolean" and field["default"] is False
    assert "monitoring = var.detailed_monitoring" in project["files"]["main.tf"]
    assert f"default = {str(enabled).lower()}" in project["files"]["variables.tf"]
    assert type(project["specification"]["inputs"]["detailed_monitoring"]) is bool
    with TestClient(create_app(), base_url="http://127.0.0.1") as client:
        headers = {"X-TerraForma-Token": client.get("/api/session").json()["token"]}
        response = client.post("/api/download", headers=headers, json=specification.model_dump())
        assert response.status_code == 200
        with zipfile.ZipFile(io.BytesIO(response.content)) as archive:
            manifest = archive.read("terraforma.project.json")
        assert json.loads(manifest)["inputs"]["detailed_monitoring"] is enabled
        imported = client.post("/api/projects/import", headers=headers, content=manifest)
        assert imported.status_code == 200
        assert imported.json()["specification"]["inputs"]["detailed_monitoring"] is enabled


@pytest.mark.parametrize("value", [0, 1, "true", "false", None, [], {}])
def test_boolean_input_does_not_coerce_other_types(value):
    with pytest.raises((ValueError, TypeError)):
        compile_project(
            ProjectSpecification(
                recipe=WizardConfig(
                    provider="aws",
                    project_name="monitor-test",
                    architecture_type="single_web_server",
                ),
                inputs={"aws_account_id": "123456789012", "detailed_monitoring": value},
            )
        )


def test_terminal_boolean_question_writes_actual_boolean(tmp_path, monkeypatch):
    answers = iter(
        [
            "aws",
            "monitor-test",
            "single_web_server",
            False,
            True,
            "development",
            "amazon-linux-2023",
            "us-east-1",
            "123456789012",
            "10.0.0.0/16",
            "t3.micro",
            True,
            "20",
            "gp3",
        ]
    )
    prompt = lambda *args, **kwargs: Mock(ask=lambda: next(answers))
    for name in ("select", "text", "confirm"):
        monkeypatch.setattr(f"terraforma.cli.questionary.{name}", prompt)
    result = CliRunner().invoke(main, ["wizard", "--dir", str(tmp_path)])
    assert result.exit_code == 0, result.output
    manifest = json.loads((tmp_path / "terraforma.project.json").read_text())
    assert manifest["inputs"]["detailed_monitoring"] is True
    assert "monitoring = var.detailed_monitoring" in (tmp_path / "main.tf").read_text()
