import copy
import json

import pytest
from click.testing import CliRunner
from fastapi.testclient import TestClient

from terraforma.cli import main
from terraforma.plan_review import review_plan
from terraforma.web import create_app
from tests.test_plan_review import plan


def firewall(port="22"):
    return {
        "direction": "INGRESS",
        "disabled": False,
        "source_ranges": ["35.235.240.0/20"],
        "source_tags": [],
        "source_service_accounts": [],
        "target_tags": ["private-secret-key"],
        "target_service_accounts": [],
        "allow": [{"protocol": "tcp", "ports": [port]}],
    }


def codes(report):
    return {item["code"] for item in report["findings"]}


@pytest.mark.parametrize("port", ["22", "3389"])
@pytest.mark.parametrize("marker", [False, [], [False], {"ports": [False], "protocol": False}])
def test_exact_iap_ingress_requires_manual_review_and_never_grants_approval(port, marker):
    payload = plan("google_compute_firewall", firewall(port))
    payload["resource_changes"][0]["change"]["after_unknown"] = {"allow": marker, "id": True}
    report = review_plan(payload, artifact_sha256="test")
    assert "iap_admin_ingress" in codes(report)
    assert "limited_policy_coverage" in codes(report) and "unknown_values" in codes(report)
    assert "public_admin_access" not in codes(report)
    assert report["approval_granted"] is False and report["policy_version"] == "0.12.0"
    assert "private-secret-key" not in json.dumps(report)


@pytest.mark.parametrize(
    "patch",
    [
        {"target_tags": []},
        {"target_tags": None},
        {"target_tags": ["one", "two"]},
        {"target_tags": ["UPPERCASE"]},
        {"target_tags": [True]},
        {"target_service_accounts": ["private@example.com"]},
        {"source_tags": ["other-source"]},
        {"source_service_accounts": ["private@example.com"]},
        {"source_ranges": ["35.235.240.0/19"]},
        {"source_ranges": ["0.0.0.0/0"]},
        {"source_ranges": ["35.235.240.0/20", "10.0.0.0/8"]},
        {"allow": [{"protocol": "tcp", "ports": ["22", "3389"]}]},
        {"allow": [{"protocol": "tcp", "ports": ["22-22"]}]},
        {"allow": [{"protocol": "tcp", "ports": ["22-3389"]}]},
        {"allow": [{"protocol": "tcp", "ports": []}]},
        {"allow": [{"protocol": "all", "ports": ["22"]}]},
        {"allow": [{"protocol": "6", "ports": ["22"]}]},
        {"allow": [{"protocol": "tcp", "ports": ["22"]}, {"protocol": "tcp", "ports": ["80"]}]},
    ],
)
def test_broader_or_untargeted_rules_keep_the_public_admin_block(patch):
    after = firewall()
    after.update(copy.deepcopy(patch))
    report = review_plan(plan("google_compute_firewall", after), artifact_sha256="test")
    assert "iap_admin_ingress" not in codes(report)
    assert "public_admin_access" in codes(report)
    assert report["approval_granted"] is False


@pytest.mark.parametrize(
    "field",
    [
        "source_ranges",
        "source_tags",
        "source_service_accounts",
        "target_tags",
        "target_service_accounts",
        "allow",
        "direction",
        "disabled",
    ],
)
@pytest.mark.parametrize("marker", [True, [True], "false", 0, None])
def test_unknown_or_malformed_control_markers_cannot_get_iap_classification(field, marker):
    payload = plan("google_compute_firewall", firewall())
    payload["resource_changes"][0]["change"]["after_unknown"] = {field: marker}
    report = review_plan(payload, artifact_sha256="test")
    assert "iap_admin_ingress" not in codes(report) and "public_admin_access" in codes(report)


@pytest.mark.parametrize("field", ["direction", "disabled"])
def test_missing_explicit_direction_or_enablement_keeps_the_block(field):
    after = firewall()
    del after[field]
    report = review_plan(plan("google_compute_firewall", after), artifact_sha256="test")
    assert "public_admin_access" in codes(report) and "iap_admin_ingress" not in codes(report)


def test_iap_rule_does_not_remove_a_destructive_change_block():
    report = review_plan(
        plan("google_compute_firewall", firewall(), ["delete", "create"]),
        artifact_sha256="test",
    )
    assert "destructive_change" in codes(report) and "iap_admin_ingress" in codes(report)
    assert report["approval_granted"] is False


def test_cli_api_use_same_redacted_review_report(tmp_path):
    raw = json.dumps(plan("google_compute_firewall", firewall("3389"))).encode()
    path = tmp_path / "review.tfplan.json"
    path.write_bytes(raw)
    result = CliRunner().invoke(main, ["review-plan", "--file", str(path), "--json-output"])
    with TestClient(create_app(), base_url="http://127.0.0.1") as client:
        token = client.get("/api/session").json()["token"]
        response = client.post(
            "/api/plans/review", headers={"X-TerraForma-Token": token}, content=raw
        )
    assert response.status_code == 200
    assert json.loads(result.output) == response.json()
    assert "private-secret-key" not in response.text
