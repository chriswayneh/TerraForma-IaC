import io
import json
import zipfile

import pytest
from click.testing import CliRunner
from fastapi.testclient import TestClient

from terraforma.cli import main
from terraforma.generator import WizardConfig
from terraforma.project import ProjectSpecification, choice_summary, compile_project, input_contract
from terraforma.web import create_app


def spec(**inputs):
    return ProjectSpecification(
        recipe=WizardConfig(
            provider="aws", project_name="review-test", architecture_type="single_web_server"
        ),
        inputs={"aws_account_id": "123456789012", **inputs},
    )


def test_summary_explains_effective_defaults_and_supplied_boolean():
    result = compile_project(spec(detailed_monitoring=False, boot_disk_size_gb=40))
    choices = {item["name"]: item for item in result["choice_summary"]}
    assert choices["detailed_monitoring"]["value"] == "Disabled"
    assert choices["detailed_monitoring"]["source"] == "answer"
    assert choices["boot_disk_size_gb"]["value"] == "40"
    assert choices["region"]["value"] == "us-east-1"
    assert choices["region"]["source"] == "default"
    assert choices["project_name"]["value"] == "review-test"
    assert choices["project_name"]["source"] == "recipe"


def test_summary_records_external_secret_requirement_without_reading_environment(monkeypatch):
    monkeypatch.setenv("TF_VAR_database_password", "must-not-be-read")
    result = compile_project(
        ProjectSpecification(
            recipe=WizardConfig(
                provider="aws", project_name="review-test", architecture_type="secure_database"
            ),
            inputs={"aws_account_id": "123456789012"},
        )
    )
    choices = {item["name"]: item for item in result["choice_summary"]}
    assert choices["database_password"]["source"] == "external"
    assert "TF_VAR_database_password" in choices["database_password"]["value"]
    assert "must-not-be-read" not in json.dumps(result)


def test_long_content_is_summarized_and_terminal_controls_are_removed():
    summary = choice_summary(
        input_contract(spec().recipe), {"region": "line\nvalue\x1b\u202e" + "x" * 200}, {}
    )
    region = next(choice["value"] for choice in summary if choice["name"] == "region")
    assert len(region) == 120 and region.endswith("...")
    assert "\n" not in region and "\x1b" not in region and "\u202e" not in region
    site = compile_project(
        ProjectSpecification(
            recipe=WizardConfig(
                provider="aws", project_name="review-test", architecture_type="static_site"
            ),
            inputs={"aws_account_id": "123456789012", "index_html": "<h1>private page text</h1>"},
        )
    )
    assert "private page text" not in json.dumps(site["choice_summary"])


def test_browser_export_guide_uses_literal_answers_and_import_summary_matches():
    with TestClient(create_app(), base_url="http://127.0.0.1") as client:
        headers = {"X-TerraForma-Token": client.get("/api/session").json()["token"]}
        payload = spec(region="us-east-1").model_dump()
        generated = client.post("/api/generate", headers=headers, json=payload)
        assert generated.status_code == 200
        exported = client.post("/api/download", headers=headers, json=payload)
        assert exported.status_code == 200
        with zipfile.ZipFile(io.BytesIO(exported.content)) as archive:
            guide = archive.read("README.md").decode()
            manifest = archive.read("terraforma.project.json")
            assert "Your configuration choices:" in guide
            assert "us\\-east\\-1" in guide
        imported = client.post("/api/projects/import", headers=headers, content=manifest)
        assert imported.json()["choice_summary"] == generated.json()["choice_summary"]


@pytest.mark.parametrize("as_json", [True, False])
def test_terminal_describe_is_read_only_and_matches_summary(tmp_path, as_json):
    manifest = tmp_path / "project.json"
    manifest.write_text(spec(detailed_monitoring=True).model_dump_json(), encoding="utf-8")
    arguments = ["describe", "--spec", str(manifest)] + (["--json-output"] if as_json else [])
    result = CliRunner().invoke(main, arguments)
    assert result.exit_code == 0, result.output
    if as_json:
        assert (
            json.loads(result.output)["choices"]
            == compile_project(spec(detailed_monitoring=True))["choice_summary"]
        )
    else:
        assert "Enable detailed EC2 monitoring: Enabled (answer)" in result.output
        assert "remain unverified" in result.output
    assert {file.name for file in tmp_path.iterdir()} == {"project.json"}


def test_invalid_describe_error_does_not_echo_input(tmp_path):
    manifest = tmp_path / "project.json"
    manifest.write_text('{"inputs": {"secret": "private-marker"}}')
    result = CliRunner().invoke(main, ["describe", "--spec", str(manifest)])
    assert result.exit_code != 0 and "private-marker" not in result.output
