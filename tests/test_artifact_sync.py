import json
from pathlib import Path

import pytest
from click.testing import CliRunner

from terraforma.artifacts import project_artifacts
from terraforma.cli import main
from terraforma.generator import ArtifactCleanupError, write_configuration
from tests.test_artifacts import project


@pytest.mark.parametrize("failure_type", [OSError, KeyboardInterrupt])
@pytest.mark.parametrize("failed_file", [1, 3, 6])
def test_sync_failure_cleans_created_artifacts_and_preserves_existing_files(
    tmp_path, monkeypatch, failure_type, failed_file
):
    note = tmp_path / "note.txt"
    note.write_text("existing")
    calls = 0
    failure = failure_type("private-sync-marker")

    def fail_sync(fd):
        nonlocal calls
        calls += 1
        if calls == failed_file:
            raise failure

    monkeypatch.setattr("terraforma.generator.os.fsync", fail_sync)
    with pytest.raises(failure_type) as error:
        write_configuration(project_artifacts(project()), tmp_path)
    assert error.value is failure
    assert list(tmp_path.iterdir()) == [note]
    assert note.read_text() == "existing"


def test_sync_failure_reports_incomplete_cleanup_without_private_details(tmp_path, monkeypatch):
    failure = OSError("private-sync-marker")

    def fail_sync(fd):
        raise failure

    original_unlink = Path.unlink

    def deny_main_removal(path, *args, **kwargs):
        if path.name == "main.tf":
            raise PermissionError("private-cleanup-marker")
        return original_unlink(path, *args, **kwargs)

    monkeypatch.setattr("terraforma.generator.os.fsync", fail_sync)
    monkeypatch.setattr(Path, "unlink", deny_main_removal)
    with pytest.raises(ArtifactCleanupError) as error:
        write_configuration(project_artifacts(project()), tmp_path)
    assert error.value.__cause__ is failure
    assert error.value.filenames == ("main.tf",)
    assert "private-" not in str(error.value)


def test_cli_does_not_report_success_or_expose_sync_errors(tmp_path, monkeypatch):
    source = tmp_path / "source.json"
    source.write_text(json.dumps(project()["specification"]))

    def fail_sync(fd):
        raise OSError("private-sync-marker")

    monkeypatch.setattr("terraforma.generator.os.fsync", fail_sync)
    destination = tmp_path / "output"
    result = CliRunner().invoke(
        main, ["generate", "--spec", str(source), "--dir", str(destination)]
    )
    assert result.exit_code == 1
    assert "private-sync-marker" not in result.output
    assert "Created Terraform" not in result.output
    assert not list(destination.iterdir())
