import os
from pathlib import Path

import pytest

from terraforma.file_input import read_regular_bytes
from terraforma.sandbox import ValidationSandbox


@pytest.mark.parametrize(
    "name",
    [
        "review.tfplan",
        "review.tfplan.json",
        "review.plan",
        "review.plan.json",
        "backend.tfbackend",
        ".terraformrc",
        "terraform.rc",
        "crash.1234.log",
        "PRIVATE.TFPLAN",
        "PRIVATE.TFSTATE",
        "PRIVATE.TFVARS.JSON",
        ".ENV.LOCAL",
    ],
)
@pytest.mark.parametrize("nested", [False, True])
def test_private_artifacts_are_not_copied_into_validation(tmp_path, name, nested):
    (tmp_path / "main.tf").write_text("terraform {}", encoding="utf-8")
    directory = tmp_path / "assets" if nested else tmp_path
    directory.mkdir(exist_ok=True)
    artifact = directory / name
    artifact.write_bytes(b"private-file-marker")
    with ValidationSandbox(target_dir=tmp_path) as sandbox:
        assert not (Path(sandbox.temp_dir) / artifact.relative_to(tmp_path)).exists()
    assert artifact.read_bytes() == b"private-file-marker"


def test_binary_assets_and_provider_lock_are_preserved_exactly(tmp_path):
    (tmp_path / "main.tf").write_text("terraform {}", encoding="utf-8")
    (tmp_path / "asset.bin").write_bytes(bytes(range(256)))
    (tmp_path / ".terraform.lock.hcl").write_bytes(b"provider lock\r\n")
    with ValidationSandbox(target_dir=tmp_path) as sandbox:
        destination = Path(sandbox.temp_dir)
        assert (destination / "asset.bin").read_bytes() == bytes(range(256))
        assert (destination / ".terraform.lock.hcl").read_bytes() == b"provider lock\r\n"


def test_excluded_directory_names_are_case_insensitive(tmp_path):
    (tmp_path / "main.tf").write_text("terraform {}", encoding="utf-8")
    excluded = tmp_path / ".GIT"
    excluded.mkdir()
    (excluded / "private.txt").write_text("private-file-marker", encoding="utf-8")
    with ValidationSandbox(target_dir=tmp_path) as sandbox:
        assert not (Path(sandbox.temp_dir) / ".GIT").exists()


@pytest.mark.parametrize("generated", [False, True])
def test_raw_and_generated_hcl_limits_count_encoded_bytes(monkeypatch, generated):
    monkeypatch.setattr(ValidationSandbox, "file_limit", 16)
    arguments = (
        {"generated_files": {"main.tf": "é" * 9}} if generated else {"raw_main_hcl": "é" * 9}
    )
    sandbox = ValidationSandbox(**arguments)
    with pytest.raises(ValueError, match="limit"):
        sandbox.create_environment()
    assert sandbox.temp_dir is None


@pytest.mark.parametrize("limit", ["file", "workspace"])
def test_growth_after_size_check_cannot_exceed_copy_limits(tmp_path, monkeypatch, limit):
    (tmp_path / "main.tf").write_bytes(b"terraform {}")
    asset = tmp_path / "asset.bin"
    asset.write_bytes(b"a")
    monkeypatch.setattr(ValidationSandbox, "file_limit", 32 if limit == "workspace" else 16)
    monkeypatch.setattr(ValidationSandbox, "workspace_limit", 24 if limit == "workspace" else 64)
    calls = []

    def grow_before_read(path, maximum):
        if path.name == "asset.bin":
            calls.append(path)
            path.write_bytes(b"a" * 17)
        return read_regular_bytes(path, maximum)

    monkeypatch.setattr("terraforma.sandbox.read_regular_bytes", grow_before_read)
    sandbox = ValidationSandbox(target_dir=tmp_path)
    with pytest.raises(ValueError, match="limit"):
        sandbox.create_environment()
    assert calls == [asset]
    assert sandbox.temp_dir is None
    assert (tmp_path / "main.tf").read_bytes() == b"terraform {}"


def test_exact_file_and_workspace_limits_are_accepted(tmp_path, monkeypatch):
    (tmp_path / "main.tf").write_bytes(b"terraform {}")
    (tmp_path / "asset.bin").write_bytes(b"a" * 16)
    monkeypatch.setattr(ValidationSandbox, "file_limit", 16)
    monkeypatch.setattr(ValidationSandbox, "workspace_limit", 28)
    with ValidationSandbox(target_dir=tmp_path) as sandbox:
        assert (Path(sandbox.temp_dir) / "asset.bin").read_bytes() == b"a" * 16


@pytest.mark.skipif(not hasattr(os, "mkfifo"), reason="POSIX named pipe required")
def test_file_replaced_by_pipe_at_open_does_not_block_copy(tmp_path, monkeypatch):
    (tmp_path / "main.tf").write_bytes(b"terraform {}")
    asset = tmp_path / "asset.bin"
    asset.write_bytes(b"a")
    original_open = os.open

    def replace_at_open(name, flags, *args, **kwargs):
        if Path(name) == asset:
            assert flags & os.O_NONBLOCK
            asset.unlink()
            os.mkfifo(asset)
        return original_open(name, flags, *args, **kwargs)

    monkeypatch.setattr(os, "open", replace_at_open)
    sandbox = ValidationSandbox(target_dir=tmp_path)
    with pytest.raises(ValueError, match="regular file"):
        sandbox.create_environment()
    assert sandbox.temp_dir is None
