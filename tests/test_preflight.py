import json
from pathlib import Path

import pytest
from click.testing import CliRunner

from terraforma.cli import main
from terraforma.generator import WizardConfig
from terraforma.preflight import target_preflight
from terraforma.process import CommandResult
from terraforma.project import ProjectSpecification

TARGETS = {
    "aws": {"aws_account_id": "123456789012"},
    "azure": {"subscription_id": "abcdef12-1234-1234-1234-123456789abc"},
    "gcp": {"gcp_project_id": "example-project"},
}
RESPONSES = {
    "aws": {"Account": "123456789012", "Arn": "private-principal-marker"},
    "azure": {"subscriptionId": "ABCDEF12-1234-1234-1234-123456789ABC", "state": "Enabled"},
    "gcp": {"projectId": "example-project", "lifecycleState": "ACTIVE"},
}


def spec(provider):
    return ProjectSpecification(
        recipe=WizardConfig(
            provider=provider, project_name="preflight-test", architecture_type="static_site"
        ),
        inputs=TARGETS[provider],
    )


def command(monkeypatch, *, data=None, result=None):
    calls = []
    monkeypatch.setattr(
        "terraforma.preflight.shutil.which", lambda name: f"/private-location/{name}"
    )

    def run(arguments, **kwargs):
        assert Path(kwargs["cwd"]).is_dir()
        calls.append((arguments, kwargs))
        return result or CommandResult(0, json.dumps(data).encode(), b"private-stderr-marker")

    monkeypatch.setattr("terraforma.preflight.run_bounded", run)
    return calls


@pytest.mark.parametrize("provider", TARGETS)
def test_no_cloud_discovery_or_command_without_explicit_opt_in(provider, monkeypatch):
    def forbidden(*args, **kwargs):
        raise AssertionError("Offline preflight must not discover or execute cloud tools.")

    monkeypatch.setattr("terraforma.preflight.shutil.which", forbidden)
    monkeypatch.setattr("terraforma.preflight.run_bounded", forbidden)
    report = target_preflight(spec(provider))
    assert report["status"] == "not_checked"
    assert report["target_matches"] is None
    assert report["approval_granted"] is False
    assert len(report["specification_sha256"]) == 64


@pytest.mark.parametrize("provider", TARGETS)
def test_matching_target_is_reported_without_principal_values(provider, monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "private-ai-marker")
    monkeypatch.setenv("TF_VAR_password", "private-password-marker")
    calls = command(monkeypatch, data=RESPONSES[provider])
    report = target_preflight(spec(provider), verify_target=True, timeout=12)
    assert report["status"] == "target_confirmed"
    assert report["target_matches"] is True
    assert report["deployment_readiness_verified"] is report["approval_granted"] is False
    arguments, options = calls[0]
    assert options["timeout"] == 12
    assert options["stream_limit"] == 128 * 1024
    assert "OPENAI_API_KEY" not in options["env"]
    assert "TF_VAR_password" not in options["env"]
    assert not Path(options["cwd"]).exists()
    if provider == "aws":
        assert arguments[1:3] == ["sts", "get-caller-identity"]
        assert "https://sts.amazonaws.com" in arguments
    elif provider == "azure":
        assert arguments[1:4] == ["rest", "--method", "GET"]
        assert any(item.startswith("/subscriptions/") for item in arguments)
    else:
        assert arguments[1:3] == ["projects", "describe"]
    assert "private-" not in json.dumps(report)


@pytest.mark.parametrize(
    "provider,data",
    [
        ("aws", {"Account": "999999999999"}),
        ("azure", {"subscriptionId": "99999999-1234-1234-1234-123456789abc", "state": "Enabled"}),
        ("gcp", {"projectId": "wrong-project", "lifecycleState": "ACTIVE"}),
    ],
)
def test_mismatched_targets_are_not_confirmed(provider, data, monkeypatch):
    command(monkeypatch, data=data)
    report = target_preflight(spec(provider), verify_target=True)
    assert report["status"] == "target_mismatch"
    assert report["target_matches"] is False
    assert next(iter(data.values())) not in json.dumps(report)


@pytest.mark.parametrize(
    "provider,data",
    [
        ("azure", {**RESPONSES["azure"], "state": "Disabled"}),
        ("azure", {**RESPONSES["azure"], "state": "Warned"}),
        ("gcp", {**RESPONSES["gcp"], "lifecycleState": "DELETE_REQUESTED"}),
    ],
)
def test_nonready_target_states_require_attention(provider, data, monkeypatch):
    command(monkeypatch, data=data)
    report = target_preflight(spec(provider), verify_target=True)
    assert report["status"] == "target_not_ready"
    assert report["target_state_acceptable"] is False


@pytest.mark.parametrize(
    "provider,data",
    [
        ("aws", {"Account": True}),
        ("aws", {"Account": "private-invalid-account"}),
        ("azure", {**RESPONSES["azure"], "state": []}),
        ("azure", {"subscriptionId": "private-invalid-subscription", "state": "Enabled"}),
        ("gcp", {**RESPONSES["gcp"], "lifecycleState": "private-unknown-state"}),
        ("gcp", []),
    ],
)
def test_invalid_metadata_fails_without_echoing_values(provider, data, monkeypatch):
    command(monkeypatch, data=data)
    report = target_preflight(spec(provider), verify_target=True)
    assert report["status"] == "invalid_response"
    assert "private-" not in json.dumps(report)


@pytest.mark.parametrize(
    "content",
    [
        b"private-invalid-json",
        b'{"Account":"123456789012","Account":"999999999999"}',
        b'{"Account":NaN}',
        b'{"Account":"123456789012","ignored":1e999}',
        pytest.param(b"[" * 65 + b"0" + b"]" * 65, id="excessive-depth"),
        b"\xff",
    ],
)
def test_ambiguous_or_invalid_json_is_rejected(content, monkeypatch):
    command(monkeypatch, result=CommandResult(0, content, b""))
    assert target_preflight(spec("aws"), verify_target=True)["status"] == "invalid_response"


@pytest.mark.parametrize(
    "result",
    [
        CommandResult(1, b"private-value", b"private-error"),
        CommandResult(-1, b"", b"", "private-limit-message"),
    ],
)
def test_failed_commands_never_return_raw_diagnostics(result, monkeypatch):
    command(monkeypatch, result=result)
    report = target_preflight(spec("aws"), verify_target=True)
    assert report["status"] == "failed"
    assert "private-" not in json.dumps(report)


def test_missing_or_unlaunchable_tool(monkeypatch):
    monkeypatch.setattr("terraforma.preflight.shutil.which", lambda name: None)
    assert target_preflight(spec("aws"), verify_target=True)["status"] == "unavailable"
    command(monkeypatch, data=RESPONSES["aws"])

    def fail(*args, **kwargs):
        raise OSError("private-machine-marker")

    monkeypatch.setattr("terraforma.preflight.run_bounded", fail)
    report = target_preflight(spec("aws"), verify_target=True)
    assert report["status"] == "failed"
    assert "private-" not in json.dumps(report)


@pytest.mark.parametrize("timeout", [0, -1, 121, float("inf"), float("nan")])
def test_invalid_timeout_never_runs_a_tool(timeout, monkeypatch):
    calls = command(monkeypatch, data=RESPONSES["aws"])
    with pytest.raises(ValueError):
        target_preflight(spec("aws"), verify_target=True, timeout=timeout)
    assert not calls


@pytest.mark.parametrize("opt_in", ["true", 1, None])
def test_nonboolean_opt_in_never_executes_a_command(opt_in, monkeypatch):
    calls = command(monkeypatch, data=RESPONSES["aws"])
    with pytest.raises(ValueError):
        target_preflight(spec("aws"), verify_target=opt_in)
    assert not calls


def test_cli_explicit_opt_in_exit_status_and_invalid_input(tmp_path, monkeypatch):
    source = tmp_path / "project.json"
    source.write_text(spec("aws").model_dump_json(), encoding="utf-8")
    calls = command(monkeypatch, data={"Account": "999999999999"})
    runner = CliRunner()
    offline = runner.invoke(main, ["preflight", "--spec", str(source), "--json-output"])
    assert offline.exit_code == 0
    assert not calls
    failed = runner.invoke(
        main, ["preflight", "--spec", str(source), "--verify-target", "--json-output"]
    )
    assert failed.exit_code == 1
    assert json.loads(failed.output)["status"] == "target_mismatch"
    assert "999999999999" not in failed.output
    command(monkeypatch, data=RESPONSES["aws"])
    confirmed = runner.invoke(
        main, ["preflight", "--spec", str(source), "--verify-target", "--json-output"]
    )
    assert confirmed.exit_code == 0
    assert json.loads(confirmed.output)["status"] == "target_confirmed"
    assert "private-principal-marker" not in confirmed.output
    calls.clear()
    source.write_text('{"private-marker":true}', encoding="utf-8")
    invalid = runner.invoke(main, ["preflight", "--spec", str(source), "--verify-target"])
    assert invalid.exit_code == 1
    assert not calls
    assert "private-marker" not in invalid.output
