import json

import pytest

from terraforma.plan_review import review_plan
from tests.test_plan_review import plan

TYPES = ["google_compute_instance", "google_compute_instance_template"]


@pytest.mark.parametrize("resource_type", TYPES)
@pytest.mark.parametrize("value", ["TRUE", "true", "Yes", "y", "1"])
def test_interactive_console_true_values_are_blocked(resource_type, value):
    report = review_plan(
        plan(resource_type, {"metadata": {"serial-port-enable": value}}), artifact_sha256="test"
    )
    finding = next(
        item for item in report["findings"] if item["code"] == "interactive_serial_console"
    )
    assert finding["severity"] == "block"
    assert report["approval_granted"] is False


@pytest.mark.parametrize("resource_type", TYPES)
@pytest.mark.parametrize("value", ["FALSE", "n", "No", "0"])
def test_explicit_disable_does_not_hide_other_policy_gaps(resource_type, value):
    report = review_plan(
        plan(resource_type, {"metadata": {"serial-port-enable": value}}), artifact_sha256="test"
    )
    found = {item["code"] for item in report["findings"]}
    assert (
        not {
            "interactive_serial_console",
            "serial_console_unknown",
            "serial_console_protection_removed",
        }
        & found
    )
    assert "limited_policy_coverage" in found
    assert report["approval_granted"] is False


@pytest.mark.parametrize("resource_type", TYPES)
@pytest.mark.parametrize("metadata", [None, {}, {"serial-port-enable": None}])
def test_missing_console_settings_remain_inheritance_review_gaps(resource_type, metadata):
    report = review_plan(plan(resource_type, {"metadata": metadata}), artifact_sha256="test")
    assert "serial_console_unknown" in {item["code"] for item in report["findings"]}


@pytest.mark.parametrize("resource_type", TYPES)
@pytest.mark.parametrize(
    "metadata",
    [
        "private-invalid-value",
        [],
        {"serial-port-enable": True},
        {"serial-port-enable": "private-invalid-value"},
    ],
)
@pytest.mark.parametrize("side", ["before", "after"])
def test_malformed_console_controls_fail_closed_without_values(resource_type, metadata, side):
    data = plan(resource_type, {})
    data["resource_changes"][0]["change"][side] = {"metadata": metadata}
    report = review_plan(data, artifact_sha256="test")
    assert "unresolved_policy_input" in {item["code"] for item in report["findings"]}
    assert "private-invalid-value" not in json.dumps(report)


@pytest.mark.parametrize("resource_type", TYPES)
def test_removing_explicit_disable_is_blocked(resource_type):
    data = plan(resource_type, {"metadata": {}}, ["update"])
    data["resource_changes"][0]["change"]["before"] = {"metadata": {"serial-port-enable": "FALSE"}}
    report = review_plan(data, artifact_sha256="test")
    finding = next(
        item for item in report["findings"] if item["code"] == "serial_console_protection_removed"
    )
    assert finding["severity"] == "block"
    assert report["policy_version"] == "0.8.0" and report["approval_granted"] is False
