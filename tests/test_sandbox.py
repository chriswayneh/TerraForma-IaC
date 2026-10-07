from pathlib import Path

import pytest

from terraforma.process import CommandResult
from terraforma.sandbox import ValidationSandbox


def test_copy_preserves_modules_assets_and_lock_but_excludes_state(tmp_path):
    (tmp_path / "main.tf").write_text('module "child" { source = "./modules/child" }')
    child = tmp_path / "modules" / "child"
    child.mkdir(parents=True)
    (child / "main.tf").write_text('output "result" { value = 1 }')
    (tmp_path / ".terraform.lock.hcl").write_text("lock")
    (tmp_path / "terraform.tfstate").write_text("private state")
    (tmp_path / "secret.tfvars").write_text("password")
    (tmp_path / ".env").write_text("secret")
    (tmp_path / "asset.txt").write_text("asset")
    sandbox = ValidationSandbox(target_dir=tmp_path)
    with sandbox:
        copy = Path(sandbox.temp_dir)
        assert (copy / "modules/child/main.tf").exists()
        assert (copy / ".terraform.lock.hcl").read_text() == "lock"
        assert (copy / "asset.txt").read_text() == "asset"
        assert not (copy / "terraform.tfstate").exists()
        assert not (copy / "secret.tfvars").exists()
        assert not (copy / ".env").exists()
    assert not copy.exists()
    assert not (tmp_path / ".terraform").exists()


def test_missing_dependencies_cannot_report_success(monkeypatch):
    monkeypatch.setattr("terraforma.sandbox.shutil.which", lambda name: None)
    result = ValidationSandbox("terraform {}").validate()
    assert not result["is_valid"]
    assert {item["tool"] for item in result["errors"]} == {"terraform_validate", "tflint"}


@pytest.mark.parametrize("locked", [False, True])
@pytest.mark.parametrize("init_success", [False, True])
def test_existing_provider_locks_are_readonly_without_an_upgrade_or_retry(
    tmp_path, monkeypatch, locked, init_success
):
    (tmp_path / "main.tf").write_text("terraform {}", encoding="utf-8")
    lock = tmp_path / ".terraform.lock.hcl"
    if locked:
        lock.write_bytes(b"reviewed-provider-selection\r\n")
    calls = []
    monkeypatch.setattr("terraforma.sandbox.shutil.which", lambda name: f"/tools/{name}")

    def run(arguments, **kwargs):
        calls.append(arguments)
        if arguments[1] == "init":
            assert ("-lockfile=readonly" in arguments) is locked
            assert "-upgrade" not in arguments
            assert "-backend=false" in arguments
            if locked:
                assert (Path(kwargs["cwd"]) / lock.name).read_bytes() == lock.read_bytes()
            return CommandResult(0 if init_success else 1, b"", b"lock selection requires review")
        return CommandResult(0, b"", b"")

    monkeypatch.setattr("terraforma.sandbox.run_bounded", run)
    result = ValidationSandbox(target_dir=tmp_path).validate()
    assert result["is_valid"] is init_success
    assert sum(arguments[1] == "init" for arguments in calls) == 1
    assert any(arguments[1] == "validate" for arguments in calls) is init_success
    if locked:
        assert lock.read_bytes() == b"reviewed-provider-selection\r\n"
    else:
        assert not lock.exists()


def test_init_failure_skips_validate_and_preserves_both_streams(monkeypatch):
    monkeypatch.setattr("terraforma.sandbox.shutil.which", lambda name: f"/tools/{name}")
    calls = []

    def run(arguments, **kwargs):
        calls.append(arguments)
        if "init" in arguments:
            return CommandResult(1, b"stdout error", b"stderr error")
        return CommandResult(0, b"ok", b"")

    monkeypatch.setattr("terraforma.sandbox.run_bounded", run)
    result = ValidationSandbox("terraform {}").validate()
    assert not result["is_valid"]
    assert "stdout error" in result["logs"] and "stderr error" in result["logs"]
    assert not any("validate" in arguments for arguments in calls)
    assert any("--format=json" in arguments for arguments in calls)


def test_timeout_is_a_failure(monkeypatch):
    monkeypatch.setattr("terraforma.sandbox.shutil.which", lambda name: f"/tools/{name}")

    def run(arguments, **kwargs):
        return CommandResult(-1, b"partial stdout", b"partial stderr", "Command timed out.")

    monkeypatch.setattr("terraforma.sandbox.run_bounded", run)
    result = ValidationSandbox("terraform {}", timeout=1).validate()
    assert not result["is_valid"]
    assert "timed out" in result["logs"]
    assert "partial stderr" in result["logs"]


def test_environment_overrides_cannot_change_commands(monkeypatch):
    monkeypatch.setenv("TF_CLI_ARGS_init", "-backend=true")
    monkeypatch.setenv("TF_DATA_DIR", "outside")
    monkeypatch.setenv("TF_VAR_database_password", "private-database-value")
    monkeypatch.setenv("OPENAI_API_KEY", "private-ai-value")
    monkeypatch.setattr("terraforma.sandbox.shutil.which", lambda name: f"/tools/{name}")

    def run(arguments, **kwargs):
        assert "TF_CLI_ARGS_init" not in kwargs["env"]
        assert "TF_VAR_database_password" not in kwargs["env"]
        assert "OPENAI_API_KEY" not in kwargs["env"]
        assert Path(kwargs["env"]["TF_DATA_DIR"]).parent == Path(kwargs["cwd"])
        return CommandResult(0, b"", b"")

    monkeypatch.setattr("terraforma.sandbox.run_bounded", run)
    assert ValidationSandbox("terraform {}").validate()["is_valid"]


def test_cleanup_after_exception():
    sandbox = ValidationSandbox("terraform {}")
    with pytest.raises(RuntimeError), sandbox:
        directory = Path(sandbox.temp_dir)
        raise RuntimeError("test")
    assert not directory.exists()


def test_empty_target_is_rejected_and_cleaned(tmp_path):
    sandbox = ValidationSandbox(target_dir=tmp_path)
    with pytest.raises(ValueError, match="no root"):
        sandbox.create_environment()
    assert sandbox.temp_dir is None


def test_diagnostics_remove_terminal_controls_and_preserve_plain_text():
    raw = "\x1b[31mFailure\x1b[0m\rHidden\x1b]52;c;clipboard-payload\x07\nDetails\tremain\x08\x00\x9b\u202e"
    assert ValidationSandbox._clean(raw) == "Failure\nHidden\nDetails\tremain"
    assert ValidationSandbox._clean(b"invalid-utf8\xff") == "invalid-utf8\ufffd"
    assert ValidationSandbox._clean("\x1b]0;title\x1b\\message") == "message"
