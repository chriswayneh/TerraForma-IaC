from unittest.mock import Mock

from click.testing import CliRunner

from terraforma.cli import main, readable_error


def test_cancelled_wizard_writes_nothing(tmp_path, monkeypatch):
    monkeypatch.setattr(
        "terraforma.cli.questionary.select", lambda *args, **kwargs: Mock(ask=lambda: None)
    )
    result = CliRunner().invoke(main, ["wizard", "--dir", str(tmp_path)])
    assert result.exit_code == 1
    assert not list(tmp_path.iterdir())


def test_json_diagnostics_are_readable():
    raw = 'terraform validate:\n{"diagnostics": [{"summary": "Missing variable", "detail": "Declare the variable", "range": {"filename": "main.tf", "start": {"line": 2}}}]}'
    assert (
        readable_error(raw)
        == "terraform validate:\nmain.tf:2: Missing variable\nDeclare the variable"
    )
    assert readable_error("terraform init:\nnetwork failure") == "terraform init:\nnetwork failure"


def test_wizard_writes_selected_configuration(tmp_path, monkeypatch):
    answers = iter(["gcp", "example", "static_site", False, True])
    prompt = lambda *args, **kwargs: Mock(ask=lambda: next(answers))
    monkeypatch.setattr("terraforma.cli.questionary.select", prompt)
    monkeypatch.setattr("terraforma.cli.questionary.text", prompt)
    monkeypatch.setattr("terraforma.cli.questionary.confirm", prompt)
    result = CliRunner().invoke(main, ["wizard", "--dir", str(tmp_path)])
    assert result.exit_code == 0, result.output
    assert '"google_storage_bucket"' in (tmp_path / "main.tf").read_text()
    assert 'public_access_prevention = "enforced"' in (tmp_path / "main.tf").read_text()


def test_failure_uses_ai_and_preserves_failure_exit(tmp_path, monkeypatch):
    monkeypatch.setattr(
        "terraforma.cli.ValidationSandbox.validate",
        lambda self: {
            "is_valid": False,
            "logs": "raw log",
            "errors": [{"tool": "tflint", "raw_output": "raw log"}],
        },
    )

    class Engine:
        async def diagnose(self, logs):
            assert logs == "raw log"
            return {"friendly_explanation": "Clear reason", "recommended_fix": "Exact fix"}

    monkeypatch.setattr("terraforma.cli.AIDiagnosticsEngine", Engine)
    result = CliRunner().invoke(main, ["run", "--dir", str(tmp_path)])
    assert result.exit_code == 1
    assert "Clear reason" in result.output and "Exact fix" in result.output


def test_no_ai_and_success_do_not_call_openai(tmp_path, monkeypatch):
    def forbidden():
        raise AssertionError("Unexpected AI request")

    monkeypatch.setattr("terraforma.cli.AIDiagnosticsEngine", forbidden)
    for success in [False, True]:
        monkeypatch.setattr(
            "terraforma.cli.ValidationSandbox.validate",
            lambda self, success=success: {
                "is_valid": success,
                "logs": "log",
                "errors": [] if success else [{"tool": "tflint", "raw_output": "log"}],
            },
        )
        result = CliRunner().invoke(main, ["run", "--dir", str(tmp_path), "--no-ai"])
        assert result.exit_code == (0 if success else 1)
