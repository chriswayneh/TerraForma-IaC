import hashlib
import io
import json
import os
import stat
import zipfile
from pathlib import Path

import pytest
from click.testing import CliRunner
from fastapi.testclient import TestClient

from terraforma.artifacts import checksum_document, project_artifacts, verify_project
from terraforma.cli import main
from terraforma.generator import WizardConfig, write_configuration
from terraforma.project import ProjectSpecification, compile_project
from terraforma.web import create_app


def project():
    return compile_project(
        ProjectSpecification(
            recipe=WizardConfig(
                provider="aws", project_name="example", architecture_type="static_site"
            ),
            inputs={"aws_account_id": "123456789012", "environment": "development"},
        )
    )


def test_receipt_is_deterministic_and_changes_with_answers():
    first = project()
    specification = first["specification"]
    specification["inputs"] = dict(reversed(list(specification["inputs"].items())))
    equivalent = compile_project(ProjectSpecification.model_validate(specification))
    assert first["receipt"] == equivalent["receipt"]
    specification["inputs"]["environment"] = "production"
    changed = compile_project(ProjectSpecification.model_validate(specification))
    assert changed["receipt"]["specification_sha256"] != first["receipt"]["specification_sha256"]
    assert (
        changed["receipt"]["file_sha256"]["variables.tf"]
        != first["receipt"]["file_sha256"]["variables.tf"]
    )


def test_receipt_comparison_detects_changes_without_echoing_file_values(tmp_path):
    files = project_artifacts(project())
    files["SHA256SUMS.txt"] = checksum_document(files)
    write_configuration(files, tmp_path)
    original = verify_project(tmp_path)
    assert original["status"] == "matches_receipt"
    assert original["receipt_authenticated"] is original["approval_granted"] is False
    (tmp_path / "main.tf").write_text("private-value-marker")
    changed = verify_project(tmp_path)
    assert changed["status"] == "mismatch"
    assert {item["file"]: item["status"] for item in changed["files"]}["main.tf"] == "modified"
    assert "private-value-marker" not in json.dumps(changed)


def test_receipt_rejects_arbitrary_paths_and_duplicate_keys(tmp_path):
    receipt = project()["receipt"]
    receipt["file_sha256"]["../outside.tf"] = receipt["file_sha256"].pop("main.tf")
    (tmp_path / "terraforma.receipt.json").write_text(json.dumps(receipt))
    with pytest.raises(ValueError):
        verify_project(tmp_path)
    (tmp_path / "terraforma.receipt.json").write_text('{"receipt_version":1,"receipt_version":1}')
    with pytest.raises(ValueError):
        verify_project(tmp_path)


def test_directory_in_place_of_artifact_is_not_read(tmp_path):
    write_configuration(project_artifacts(project()), tmp_path)
    (tmp_path / "main.tf").unlink()
    (tmp_path / "main.tf").mkdir()
    report = verify_project(tmp_path)
    assert report["status"] == "mismatch"
    assert {item["file"]: item["status"] for item in report["files"]}[
        "main.tf"
    ] == "missing_or_unsupported"


def test_existing_manifest_is_preserved_and_no_outputs_written(tmp_path):
    source = tmp_path / "terraforma.project.json"
    source.write_text("original")
    with pytest.raises(FileExistsError):
        write_configuration(project_artifacts(project()), tmp_path)
    assert source.read_text() == "original"
    assert not list(tmp_path.glob("*.tf"))
    assert not (tmp_path / "terraforma.receipt.json").exists()


def test_failed_write_rolls_back_only_new_files(tmp_path, monkeypatch):
    note = tmp_path / "note.txt"
    note.write_text("existing note")
    original_open = open

    def fail_second_write(path, mode="r", *args, **kwargs):
        if Path(path).name == "variables.tf" and mode == "x":
            raise OSError("simulated write failure")
        return original_open(path, mode, *args, **kwargs)

    monkeypatch.setattr("builtins.open", fail_second_write)
    with pytest.raises(OSError):
        write_configuration(project_artifacts(project()), tmp_path)
    assert note.read_text() == "existing note"
    assert list(tmp_path.iterdir()) == [note]


@pytest.mark.skipif(os.name != "posix", reason="Unix permission semantics")
def test_new_project_is_private_even_with_permissive_umask(tmp_path):
    destination = tmp_path / "private-output"
    previous = os.umask(0)
    try:
        write_configuration(project_artifacts(project()), destination)
    finally:
        os.umask(previous)
    assert stat.S_IMODE(destination.stat().st_mode) == 0o700
    assert all(stat.S_IMODE(path.stat().st_mode) == 0o600 for path in destination.iterdir())
    assert verify_project(destination)["status"] == "matches_receipt"


@pytest.mark.skipif(os.name != "posix", reason="Unix permission semantics")
def test_existing_directory_permissions_are_preserved(tmp_path):
    destination = tmp_path / "existing-output"
    destination.mkdir(mode=0o750)
    original_mode = stat.S_IMODE(destination.stat().st_mode)
    write_configuration(project_artifacts(project()), destination)
    assert stat.S_IMODE(destination.stat().st_mode) == original_mode
    assert all(stat.S_IMODE(path.stat().st_mode) & 0o077 == 0 for path in destination.iterdir())


def test_zip_checksums_and_receipt_cover_exact_exported_bytes(tmp_path):
    with TestClient(create_app(), base_url="http://127.0.0.1") as client:
        headers = {"X-TerraForma-Token": client.get("/api/session").json()["token"]}
        response = client.post("/api/download", json=project()["specification"], headers=headers)
        assert response.status_code == 200
        with zipfile.ZipFile(io.BytesIO(response.content)) as archive:
            for line in archive.read("SHA256SUMS.txt").decode().splitlines():
                digest, name = line.split("  ", 1)
                assert hashlib.sha256(archive.read(name)).hexdigest() == digest
            for name in (
                "main.tf",
                "variables.tf",
                "outputs.tf",
                "terraforma.project.json",
                "terraforma.receipt.json",
            ):
                (tmp_path / name).write_bytes(archive.read(name))
    assert verify_project(tmp_path)["status"] == "matches_receipt"


def test_cli_generates_receipt_and_verification_has_failure_exit(tmp_path):
    source = tmp_path / "source.json"
    source.write_text(json.dumps(project()["specification"]))
    destination = tmp_path / "output"
    runner = CliRunner()
    generated = runner.invoke(main, ["generate", "--spec", str(source), "--dir", str(destination)])
    assert generated.exit_code == 0, generated.output
    checked = runner.invoke(main, ["verify-project", "--dir", str(destination), "--json-output"])
    assert checked.exit_code == 0
    assert json.loads(checked.output)["status"] == "matches_receipt"
    (destination / "variables.tf").write_text("private-marker")
    failed = runner.invoke(main, ["verify-project", "--dir", str(destination), "--json-output"])
    assert failed.exit_code == 1
    assert "private-marker" not in failed.output


@pytest.mark.parametrize("version", [True, 0, 2])
def test_receipt_version_is_exact_and_cli_omits_invalid_values(tmp_path, version):
    receipt = project()["receipt"]
    receipt["receipt_version"] = version
    (tmp_path / "terraforma.receipt.json").write_text(json.dumps(receipt))
    with pytest.raises(ValueError):
        verify_project(tmp_path)
    failed = CliRunner().invoke(main, ["verify-project", "--dir", str(tmp_path), "--json-output"])
    assert failed.exit_code != 0
    assert "receipt values are omitted" in failed.output


def test_invalid_receipt_error_does_not_disclose_values(tmp_path):
    receipt = project()["receipt"]
    receipt["generator_version"] = "private-marker\n"
    (tmp_path / "terraforma.receipt.json").write_text(json.dumps(receipt))
    failed = CliRunner().invoke(main, ["verify-project", "--dir", str(tmp_path), "--json-output"])
    assert failed.exit_code != 0
    assert "private-marker" not in failed.output


def test_oversized_artifact_is_rejected_with_bounded_read(tmp_path):
    write_configuration(project_artifacts(project()), tmp_path)
    with (tmp_path / "main.tf").open("wb") as stream:
        stream.write(b"x" * (8 * 1024 * 1024 + 1))
    report = verify_project(tmp_path)
    assert report["status"] == "mismatch"
    assert {item["file"]: item["status"] for item in report["files"]}["main.tf"] == "too_large"
