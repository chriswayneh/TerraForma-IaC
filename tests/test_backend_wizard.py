import json
from unittest.mock import Mock

import pytest
from click.testing import CliRunner

from terraforma.backend import (
    backend_input_contract,
    load_and_review_backend,
    validate_backend_answer,
)
from terraforma.cli import main
from tests.test_backend import intent


def answers_for(backend):
    data = intent(backend)
    return [backend, *(data[item["name"]] for item in backend_input_contract(backend))]


def mock_prompts(monkeypatch, answers):
    values = iter(answers)
    prompt = lambda *args, **kwargs: Mock(ask=lambda: next(values))
    for name in ("select", "text", "confirm"):
        monkeypatch.setattr(f"terraforma.cli.questionary.{name}", prompt)


@pytest.mark.parametrize("backend", ["s3", "azurerm", "gcs"])
def test_guided_file_roundtrips_through_checker_without_terraform(tmp_path, monkeypatch, backend):
    mock_prompts(monkeypatch, answers_for(backend))
    monkeypatch.setattr("subprocess.run", lambda *a, **k: pytest.fail("No subprocess is allowed."))
    destination = tmp_path / "backend"
    result = CliRunner().invoke(main, ["backend-wizard", "--dir", str(destination)])
    assert result.exit_code == 0, result.output
    path = destination / "terraforma.backend.json"
    assert json.loads(path.read_text()) == intent(backend)
    assert list(destination.iterdir()) == [path]
    assert load_and_review_backend(path)["backend_configured"] is False
    assert "No backend was configured" in result.output
    assert "private-team" not in result.output
    checked = CliRunner().invoke(main, ["check-backend", "--file", str(path), "--json-output"])
    assert checked.exit_code == 0
    assert json.loads(checked.output)["approval_granted"] is False


@pytest.mark.parametrize("backend", ["s3", "azurerm", "gcs"])
@pytest.mark.parametrize("stage", ["selection", "middle", "last"])
def test_cancellation_creates_no_artifact_or_directory(tmp_path, monkeypatch, backend, stage):
    answers = answers_for(backend)
    index = (
        0 if stage == "selection" else len(answers) // 2 if stage == "middle" else len(answers) - 1
    )
    answers[index] = None
    mock_prompts(monkeypatch, answers)
    destination = tmp_path / "backend"
    result = CliRunner().invoke(main, ["backend-wizard", "--dir", str(destination)])
    assert result.exit_code != 0
    assert not destination.exists()


@pytest.mark.parametrize("filename", ["terraforma.backend.json", "terraform.tfstate", "main.tf"])
def test_occupied_destination_fails_before_prompts(tmp_path, monkeypatch, filename):
    path = tmp_path / filename
    path.write_text("private-existing-content")
    monkeypatch.setattr(
        "terraforma.cli.questionary.select", lambda *a, **k: pytest.fail("No prompts.")
    )
    result = CliRunner().invoke(main, ["backend-wizard", "--dir", str(tmp_path)])
    assert result.exit_code != 0
    assert path.read_text() == "private-existing-content"
    assert "private-existing-content" not in result.output


def test_s3_lock_decline_writes_nothing(tmp_path, monkeypatch):
    answers = answers_for("s3")
    answers[-1] = False
    mock_prompts(monkeypatch, answers)
    result = CliRunner().invoke(main, ["backend-wizard", "--dir", str(tmp_path)])
    assert result.exit_code != 0
    assert "lockfile intent is required" in result.output
    assert not list(tmp_path.iterdir())


def test_invalid_answers_never_reach_writer(tmp_path, monkeypatch):
    answers = answers_for("gcs")
    answers[-1] = "../private-location"
    mock_prompts(monkeypatch, answers)
    result = CliRunner().invoke(main, ["backend-wizard", "--dir", str(tmp_path)])
    assert result.exit_code != 0
    assert "private-location" not in result.output
    assert not list(tmp_path.iterdir())


def test_concurrent_creation_is_preserved(tmp_path, monkeypatch):
    values = iter(answers_for("gcs"))
    path = tmp_path / "terraforma.backend.json"

    def next_answer():
        value = next(values)
        if value == intent("gcs")["prefix"]:
            path.write_text("private-race-content")
        return value

    prompt = lambda *a, **k: Mock(ask=next_answer)
    monkeypatch.setattr("terraforma.cli.questionary.select", prompt)
    monkeypatch.setattr("terraforma.cli.questionary.text", prompt)
    result = CliRunner().invoke(main, ["backend-wizard", "--dir", str(tmp_path)])
    assert result.exit_code != 0
    assert path.read_text() == "private-race-content"
    assert "private-race-content" not in result.output


def test_write_sync_failure_cleans_up_and_omits_error(tmp_path, monkeypatch):
    mock_prompts(monkeypatch, answers_for("gcs"))

    def fail(fd):
        raise OSError("private-storage-error")

    monkeypatch.setattr("terraforma.generator.os.fsync", fail)
    result = CliRunner().invoke(main, ["backend-wizard", "--dir", str(tmp_path)])
    assert result.exit_code != 0
    assert "Saved backend inputs" not in result.output
    assert "private-storage-error" not in result.output
    assert not list(tmp_path.iterdir())


@pytest.mark.parametrize("backend", ["s3", "azurerm", "gcs"])
def test_questions_validate_without_remaining_answers(backend):
    data = intent(backend)
    for definition in backend_input_contract(backend):
        name = definition["name"]
        assert validate_backend_answer(backend, {}, name, data[name]) is True
        invalid = False if definition["kind"] == "boolean" else "private\ninvalid"
        error = validate_backend_answer(backend, {}, name, invalid)
        assert isinstance(error, str)
        assert "private" not in error


def test_unknown_contract_or_field_fails_closed():
    with pytest.raises(ValueError):
        backend_input_contract("private-unknown-backend")
    assert validate_backend_answer("s3", {}, "access_key", "private-secret") is not True
