import json

import pytest
from click.testing import CliRunner
from fastapi.testclient import TestClient

from terraforma.cli import main
from terraforma.plan_review import review_plan
from terraforma.web import create_app
from tests.test_plan_review import plan


def disk_plan(**values):
    return plan(
        "azurerm_managed_disk",
        {"network_access_policy": "DenyAll", "public_network_access_enabled": False, **values},
    )


def findings(data):
    report = review_plan(data, artifact_sha256="test")
    assert report["policy_version"] == "0.10.0"
    assert report["approval_granted"] is False
    assert "private-secret-key" not in json.dumps(report)
    return {item["code"]: item["severity"] for item in report["findings"]}


@pytest.mark.parametrize("public", [False, True, None])
def test_unrestricted_disk_exports_are_blocked_even_without_a_public_endpoint(public):
    found = findings(
        disk_plan(network_access_policy="AllowAll", public_network_access_enabled=public)
    )
    assert found["managed_disk_export_unrestricted"] == "block"


@pytest.mark.parametrize("policy", ["DenyAll", "AllowPrivate", "AllowAll", None])
def test_public_network_flag_is_blocked_independently_of_export_policy(policy):
    found = findings(disk_plan(network_access_policy=policy, public_network_access_enabled=True))
    assert found["managed_disk_public_network"] == "block"


@pytest.mark.parametrize("previous", ["DenyAll", "AllowPrivate", "AllowAll", None])
def test_private_exports_need_separate_review_and_cannot_remove_a_deny_all_boundary(previous):
    data = disk_plan(network_access_policy="AllowPrivate")
    data["resource_changes"][0]["change"]["before"] = {"network_access_policy": previous}
    found = findings(data)
    if previous == "DenyAll":
        assert found["managed_disk_export_protection_removed"] == "block"
    else:
        assert found["managed_disk_private_export"] == "review"


@pytest.mark.parametrize(
    "field,code",
    [
        ("network_access_policy", "managed_disk_export_unknown"),
        ("public_network_access_enabled", "managed_disk_public_network_unknown"),
    ],
)
@pytest.mark.parametrize("mode", ["missing", "null", "unknown"])
def test_unresolved_access_fields_remain_review_gaps(field, code, mode):
    data = disk_plan()
    change = data["resource_changes"][0]["change"]
    if mode == "missing":
        del change["after"][field]
    elif mode == "null":
        change["after"][field] = None
    else:
        change["after_unknown"][field] = True
    assert findings(data)[code] == "review"


@pytest.mark.parametrize("side", ["before", "after"])
@pytest.mark.parametrize(
    "field,value",
    [
        ("network_access_policy", "private-invalid-value"),
        ("network_access_policy", "denyall"),
        ("network_access_policy", False),
        ("network_access_policy", []),
        ("public_network_access_enabled", "private-invalid-value"),
        ("public_network_access_enabled", 0),
        ("public_network_access_enabled", {}),
    ],
)
def test_malformed_access_controls_block_without_disclosing_values(side, field, value):
    data = disk_plan()
    data["resource_changes"][0]["change"][side] = {field: value}
    found = findings(data)
    assert found["unresolved_policy_input"] == "block"
    report = review_plan(data, artifact_sha256="test")
    assert "private-invalid-value" not in json.dumps(report)


@pytest.mark.parametrize(
    "unknown",
    [
        None,
        [],
        True,
        {"network_access_policy": "private-invalid-value"},
        {"public_network_access_enabled": 1},
    ],
)
def test_malformed_unknown_markers_cannot_bypass_access_checks(unknown):
    data = disk_plan()
    data["resource_changes"][0]["change"]["after_unknown"] = unknown
    assert findings(data)["unresolved_policy_input"] == "block"


def test_restricted_disk_still_requires_manual_review_of_other_properties():
    data = disk_plan(secret="private-disk-value")
    report = review_plan(data, artifact_sha256="test")
    assert report["status"] == "manual_review_required"
    assert findings(data) == {"limited_policy_coverage": "review"}
    assert "private-disk-value" not in json.dumps(report)


@pytest.mark.parametrize("action", [["delete"], ["forget"], ["delete", "create"]])
def test_disk_access_controls_cannot_hide_destructive_actions(action):
    data = disk_plan()
    data["resource_changes"][0]["change"]["actions"] = action
    assert findings(data)["destructive_change"] == "block"


def test_data_sources_do_not_trigger_managed_disk_access_rules():
    data = disk_plan(network_access_policy="AllowAll")
    data["resource_changes"][0]["mode"] = "data"
    data["resource_changes"][0]["change"]["actions"] = ["read"]
    assert findings(data) == {}


@pytest.mark.parametrize("action", [["no-op"], ["update"], ["create", "delete"]])
def test_access_policy_is_reviewed_beyond_new_disk_creation(action):
    data = disk_plan(network_access_policy="AllowAll")
    data["resource_changes"][0]["change"]["actions"] = action
    assert findings(data)["managed_disk_export_unrestricted"] == "block"


@pytest.mark.parametrize("previous", [[], "private-invalid-value", True])
def test_malformed_previous_disk_object_blocks_review(previous):
    data = disk_plan()
    data["resource_changes"][0]["change"]["before"] = previous
    assert findings(data)["unresolved_policy_input"] == "block"


def test_cli_and_api_return_the_same_blocked_redacted_review(tmp_path):
    raw = json.dumps(disk_plan(network_access_policy="AllowAll", secret="private-disk-value"))
    path = tmp_path / "disk.tfplan.json"
    path.write_text(raw, encoding="utf-8")
    result = CliRunner().invoke(main, ["review-plan", "--file", str(path), "--json-output"])
    assert result.exit_code == 1, result.output
    with TestClient(create_app(), base_url="http://127.0.0.1") as client:
        token = client.get("/api/session").json()["token"]
        response = client.post(
            "/api/plans/review",
            content=raw,
            headers={"X-TerraForma-Token": token, "Content-Type": "application/json"},
        )
    assert response.status_code == 200
    report = response.json()
    assert report == json.loads(result.output)
    assert report["status"] == "blocked"
    assert report["approval_granted"] is False
    assert "private-disk-value" not in json.dumps(report)
