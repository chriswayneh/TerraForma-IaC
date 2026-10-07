import hashlib
import io
import json
import os
import shutil
import stat
import subprocess
import zipfile
from pathlib import Path

import pytest
from click.testing import CliRunner
from fastapi.testclient import TestClient

from terraforma.artifacts import checksum_document, project_artifacts, verify_project
from terraforma.cli import main
from terraforma.generator import ArtifactCleanupError, WizardConfig, write_configuration
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


def test_generated_ignore_rules_exclude_private_artifacts_but_keep_source_and_lock(tmp_path):
    git = shutil.which("git")
    if not git:
        pytest.skip("Git is required to verify exported ignore semantics.")
    write_configuration(project_artifacts(project()), tmp_path)
    subprocess.run(
        [git, "init", "--quiet", str(tmp_path)], check=True, capture_output=True, timeout=15
    )
    ignored = [
        ".terraform/providers/provider.exe",
        "terraform.tfstate",
        "terraform.tfstate.backup",
        "secret.tfvars",
        "production.auto.tfvars.json",
        "review.tfplan",
        "review.tfplan.json",
        "review.plan",
        "review.plan.json",
        "crash.log",
        "crash.123.log",
        ".env",
        ".env.local",
        ".terraformrc",
        "terraform.rc",
        "environments/dev/terraform.tfstate",
    ]
    visible = [
        ".gitignore",
        ".terraform.lock.hcl",
        "main.tf",
        "variables.tf",
        "outputs.tf",
        "terraforma.project.json",
        "terraforma.receipt.json",
        "SHA256SUMS.txt",
    ]
    result = subprocess.run(
        [git, "check-ignore", "--no-index", "--stdin", "-z"],
        input=("\0".join(ignored + visible) + "\0").encode(),
        cwd=tmp_path,
        capture_output=True,
        timeout=15,
        check=False,
    )
    assert result.returncode == 0
    assert set(result.stdout.decode().rstrip("\0").split("\0")) == set(ignored)


def test_generation_preserves_existing_ignore_file(tmp_path):
    (tmp_path / ".gitignore").write_text("existing-project-rules\n")
    with pytest.raises(FileExistsError):
        write_configuration(project_artifacts(project()), tmp_path)
    assert (tmp_path / ".gitignore").read_text() == "existing-project-rules\n"
    assert not (tmp_path / "main.tf").exists()


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


@pytest.mark.parametrize(
    "field,value,expected",
    [
        ("specification_sha256", "0" * 64, "digest_mismatch"),
        ("template_version", "private-version-marker", "template_mismatch"),
    ],
)
def test_receipt_metadata_must_agree_with_hashed_questionnaire(tmp_path, field, value, expected):
    files = project_artifacts(project())
    receipt = json.loads(files["terraforma.receipt.json"])
    receipt[field] = value
    files["terraforma.receipt.json"] = json.dumps(receipt)
    write_configuration(files, tmp_path)
    report = verify_project(tmp_path)
    assert all(item["status"] == "match" for item in report["files"])
    assert report["status"] == "mismatch"
    assert report["specification_status"] == expected
    assert "private-version-marker" not in json.dumps(report)
    result = CliRunner().invoke(main, ["verify-project", "--dir", str(tmp_path)])
    assert result.exit_code == 1
    assert expected in result.output
    assert "private-version-marker" not in result.output


@pytest.mark.parametrize(
    "content",
    [
        '{"template_version":"first","template_version":"second"}',
        '{"template_version":"0.3.0.dev0","private-marker":NaN}',
        '{"template_version":true}',
        '"private-value-marker"',
        "private-invalid-json",
    ],
)
def test_even_matching_file_hashes_cannot_validate_invalid_metadata(tmp_path, content):
    files = project_artifacts(project())
    receipt = json.loads(files["terraforma.receipt.json"])
    receipt["file_sha256"]["terraforma.project.json"] = hashlib.sha256(content.encode()).hexdigest()
    files["terraforma.project.json"] = content
    files["terraforma.receipt.json"] = json.dumps(receipt)
    write_configuration(files, tmp_path)
    report = verify_project(tmp_path)
    assert report["specification_status"] == "invalid"
    assert report["status"] == "mismatch"
    assert "private-" not in json.dumps(report)


def test_canonical_comparison_ignores_json_key_order_and_whitespace(tmp_path):
    files = project_artifacts(project())
    receipt = json.loads(files["terraforma.receipt.json"])
    specification = json.loads(files["terraforma.project.json"])
    content = json.dumps(dict(reversed(list(specification.items()))), indent=4)
    files["terraforma.project.json"] = content
    receipt["file_sha256"]["terraforma.project.json"] = hashlib.sha256(content.encode()).hexdigest()
    files["terraforma.receipt.json"] = json.dumps(receipt)
    write_configuration(files, tmp_path)
    report = verify_project(tmp_path)
    assert report["specification_status"] == "match"
    assert report["status"] == "matches_receipt"


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


@pytest.mark.parametrize("failure_type", [OSError, KeyboardInterrupt])
def test_cleanup_continues_after_one_removal_fails(tmp_path, monkeypatch, failure_type):
    note = tmp_path / "note.txt"
    note.write_text("existing note")
    original_open = open
    original_unlink = Path.unlink
    failure = failure_type("private-failure-marker")

    def fail_third_write(path, mode="r", *args, **kwargs):
        if Path(path).name == "outputs.tf" and mode == "x":
            raise failure
        return original_open(path, mode, *args, **kwargs)

    def deny_first_removal(path, *args, **kwargs):
        if path.name == "main.tf":
            raise PermissionError("private-cleanup-marker")
        return original_unlink(path, *args, **kwargs)

    monkeypatch.setattr("builtins.open", fail_third_write)
    monkeypatch.setattr(Path, "unlink", deny_first_removal)
    with pytest.raises(ArtifactCleanupError) as captured:
        write_configuration(project_artifacts(project()), tmp_path)
    assert captured.value.filenames == ("main.tf",)
    assert captured.value.__cause__ is failure
    assert "private-" not in str(captured.value)
    assert "Inspect these partial artifacts" in str(captured.value)
    assert {path.name for path in tmp_path.iterdir()} == {"note.txt", "main.tf"}
    assert note.read_text() == "existing note"
    with pytest.raises(ValueError, match="fresh project directory"):
        write_configuration(project_artifacts(project()), tmp_path)


def test_interrupted_write_removes_new_files_and_preserves_original_interrupt(
    tmp_path, monkeypatch
):
    original_open = open
    failure = KeyboardInterrupt()

    def interrupt_second_write(path, mode="r", *args, **kwargs):
        if Path(path).name == "variables.tf" and mode == "x":
            raise failure
        return original_open(path, mode, *args, **kwargs)

    monkeypatch.setattr("builtins.open", interrupt_second_write)
    with pytest.raises(KeyboardInterrupt) as captured:
        write_configuration(project_artifacts(project()), tmp_path)
    assert captured.value is failure
    assert not list(tmp_path.iterdir())


def test_cli_explains_incomplete_cleanup_without_exposing_failure_details(tmp_path, monkeypatch):
    source = tmp_path / "source.json"
    source.write_text(json.dumps(project()["specification"]))

    def fail_write(*args, **kwargs):
        raise ArtifactCleanupError(["variables.tf", "main.tf"]) from OSError("private-marker")

    monkeypatch.setattr("terraforma.cli.write_configuration", fail_write)
    result = CliRunner().invoke(
        main, ["generate", "--spec", str(source), "--dir", str(tmp_path / "output")]
    )
    assert result.exit_code == 1
    assert "cleanup was incomplete" in result.output
    assert "main.tf, variables.tf" in result.output
    assert "private-marker" not in result.output
    assert "Created Terraform" not in result.output


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
