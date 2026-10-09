import json

import pytest
from click.testing import CliRunner
from fastapi.testclient import TestClient

from terraforma.cli import main
from terraforma.initialization_review import GCP_TYPES, STARTUP_KEYS, VM_FIELDS
from terraforma.plan_review import review_plan
from terraforma.web import create_app
from tests.test_plan_review import plan

MARKER = "private-script-marker"


def report(data):
    result = review_plan(data, artifact_sha256="synthetic")
    assert result["approval_granted"] is False
    assert result["policy_version"] == "0.12.0"
    assert MARKER not in json.dumps(result)
    assert "private-secret-key" not in json.dumps(result)
    return {item["code"]: item for item in result["findings"]}


@pytest.mark.parametrize(
    "resource_type,field",
    [(resource, field) for resource, fields in VM_FIELDS.items() for field in fields],
)
def test_present_initialization_requires_manual_review_without_payload_echo(resource_type, field):
    findings = report(plan(resource_type, {field: MARKER}))
    assert findings["guest_initialization_review"]["severity"] == "review"
    assert "limited_policy_coverage" in findings or "policy_coverage_gap" in findings


@pytest.mark.parametrize("resource_type", sorted(GCP_TYPES))
@pytest.mark.parametrize("key", sorted(STARTUP_KEYS))
def test_inline_and_remote_startup_metadata_require_review(resource_type, key):
    findings = report(plan(resource_type, {"metadata": {key: MARKER}}))
    assert findings["guest_initialization_review"]["severity"] == "review"


@pytest.mark.parametrize("value", ["", None])
@pytest.mark.parametrize("resource_type", sorted(VM_FIELDS))
def test_absent_payload_does_not_imply_initialization_or_approval(resource_type, value):
    fields = {field: value for field in VM_FIELDS[resource_type]}
    findings = report(plan(resource_type, fields))
    assert "guest_initialization_review" not in findings
    assert "guest_initialization_removed" not in findings
    assert "limited_policy_coverage" in findings or "policy_coverage_gap" in findings


@pytest.mark.parametrize("resource_type", sorted(VM_FIELDS))
def test_unknown_script_has_specific_review_gap(resource_type):
    data = plan(resource_type)
    field = VM_FIELDS[resource_type][0]
    data["resource_changes"][0]["change"]["after_unknown"] = {field: True}
    findings = report(data)
    assert "guest_initialization_unknown" in findings
    assert "guest_initialization_removed" not in findings


@pytest.mark.parametrize(
    "markers", [True, {"startup-script": True}, {"windows-startup-script-ps1": True}]
)
def test_unknown_metadata_has_specific_review_gap(markers):
    data = plan("google_compute_instance")
    data["resource_changes"][0]["change"]["after_unknown"] = {"metadata": markers}
    assert "guest_initialization_unknown" in report(data)


def test_unrelated_metadata_unknowns_do_not_invent_script_payload():
    data = plan("google_compute_instance", {"metadata": {"serial-port-enable": "FALSE"}})
    data["resource_changes"][0]["change"]["after_unknown"] = {"metadata": {"other": True}}
    findings = report(data)
    assert "guest_initialization_unknown" not in findings
    assert "guest_initialization_review" not in findings


@pytest.mark.parametrize("value", [True, 1, [], {}, [MARKER]])
def test_malformed_initialization_values_fail_closed_without_echo(value):
    assert (
        report(plan("aws_instance", {"user_data": value}))["unresolved_policy_input"]["severity"]
        == "block"
    )


@pytest.mark.parametrize("marker", [None, 1, MARKER, [], {}])
def test_malformed_script_unknown_markers_fail_closed(marker):
    data = plan("aws_instance")
    data["resource_changes"][0]["change"]["after_unknown"] = {"user_data": marker}
    assert report(data)["unresolved_policy_input"]["severity"] == "block"


@pytest.mark.parametrize("metadata", [[], MARKER, {"startup-script": 1}])
def test_malformed_startup_metadata_fails_closed(metadata):
    findings = report(plan("google_compute_instance", {"metadata": metadata}))
    assert findings["unresolved_policy_input"]["severity"] == "block"


@pytest.mark.parametrize("resource_type", sorted(VM_FIELDS))
def test_removing_initialization_does_not_undo_guest_changes(resource_type):
    data = plan(resource_type, actions=["update"])
    data["resource_changes"][0]["change"]["before"] = {VM_FIELDS[resource_type][0]: MARKER}
    findings = report(data)
    assert "guest_initialization_removed" in findings
    assert "guest_initialization_review" not in findings


@pytest.mark.parametrize("actions", [["no-op"], ["create"], ["update"], ["delete", "create"]])
def test_guest_extensions_retain_opaque_manual_coverage_gap(actions):
    data = plan("azurerm_virtual_machine_extension", {"protected_settings": MARKER}, actions)
    findings = report(data)
    assert "guest_extension_review" in findings
    assert "policy_coverage_gap" in findings
    if "delete" in actions:
        assert findings["destructive_change"]["severity"] == "block"


@pytest.mark.parametrize(
    "mode,actions", [("data", ["read"]), ("managed", ["delete"]), ("managed", ["forget"])]
)
def test_removed_or_read_resources_do_not_claim_future_script_execution(mode, actions):
    data = plan("aws_instance", {"user_data": MARKER}, actions)
    data["resource_changes"][0]["mode"] = mode
    assert "guest_initialization_review" not in report(data)


def test_browser_and_terminal_reports_never_echo_initialization_payload(tmp_path, monkeypatch):
    monkeypatch.setattr("subprocess.run", lambda *a, **k: pytest.fail("Review must remain local."))
    data = plan("aws_instance", {"user_data": MARKER})
    path = tmp_path / "synthetic.tfplan.json"
    path.write_text(json.dumps(data), encoding="utf-8")
    result = CliRunner().invoke(main, ["review-plan", "--file", str(path)])
    assert "guest_initialization_review" in result.output
    assert MARKER not in result.output
    with TestClient(create_app(), base_url="http://127.0.0.1") as client:
        headers = {"X-TerraForma-Token": client.get("/api/session").json()["token"]}
        response = client.post("/api/plans/review", headers=headers, content=json.dumps(data))
    assert response.status_code == 200, response.text
    assert MARKER not in response.text
    assert response.json()["approval_granted"] is False
