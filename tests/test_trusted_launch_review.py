import json

import pytest
from click.testing import CliRunner

from terraforma.cli import main
from terraforma.plan_review import review_plan
from tests.test_plan_review import plan


@pytest.fixture(params=["azurerm_linux_virtual_machine", "azurerm_windows_virtual_machine"])
def vm_type(request):
    return request.param


@pytest.mark.parametrize("field", ["secure_boot_enabled", "vtpm_enabled"])
@pytest.mark.parametrize("previous", [None, False, True])
def test_disabled_azure_boot_control_and_removal(field, previous, vm_type):
    settings = {"secure_boot_enabled": True, "vtpm_enabled": True}
    data = plan(vm_type, {**settings, field: False})
    data["resource_changes"][0]["change"]["before"] = {**settings, field: previous}
    report = review_plan(data, artifact_sha256="test")
    code = "vm_boot_protection_removed" if previous is True else "vm_boot_protection_disabled"
    finding = next(item for item in report["findings"] if item["code"] == code)
    assert finding["severity"] == ("block" if previous is True else "review")
    assert report["policy_version"] == "0.11.0"
    assert report["approval_granted"] is False


@pytest.mark.parametrize("field", ["secure_boot_enabled", "vtpm_enabled"])
def test_missing_azure_boot_controls_are_review_gaps(field, vm_type):
    settings = {"secure_boot_enabled": True, "vtpm_enabled": True}
    del settings[field]
    report = review_plan(plan(vm_type, settings), artifact_sha256="test")
    assert "vm_boot_protection_unknown" in {item["code"] for item in report["findings"]}


@pytest.mark.parametrize("field", ["secure_boot_enabled", "vtpm_enabled"])
@pytest.mark.parametrize("value", ["private-invalid-value", 0, [], {}])
@pytest.mark.parametrize("side", ["before", "after"])
def test_malformed_azure_boot_controls_fail_closed(field, value, side, vm_type):
    data = plan(vm_type, {})
    data["resource_changes"][0]["change"][side] = {field: value}
    report = review_plan(data, artifact_sha256="test")
    assert "unresolved_policy_input" in {item["code"] for item in report["findings"]}
    assert "private-invalid-value" not in json.dumps(report)


def test_enabled_azure_boot_controls_do_not_hide_coverage_gaps(vm_type):
    report = review_plan(
        plan(vm_type, {"secure_boot_enabled": True, "vtpm_enabled": True}),
        artifact_sha256="test",
    )
    found = {item["code"] for item in report["findings"]}
    assert "limited_policy_coverage" in found
    assert (
        not {
            "vm_boot_protection_disabled",
            "vm_boot_protection_removed",
            "vm_boot_protection_unknown",
        }
        & found
    )
    assert report["approval_granted"] is False


def test_azure_boot_removal_is_visible_in_cli_and_never_approved(tmp_path):
    data = plan(
        "azurerm_linux_virtual_machine",
        {"secure_boot_enabled": False, "vtpm_enabled": True},
        ["update"],
    )
    data["resource_changes"][0]["change"]["before"] = {
        "secure_boot_enabled": True,
        "vtpm_enabled": True,
    }
    path = tmp_path / "boot-plan.json"
    path.write_text(json.dumps(data), encoding="utf-8")
    result = CliRunner().invoke(main, ["review-plan", "--file", str(path), "--json-output"])
    assert result.exit_code == 1, result.output
    report = json.loads(result.output)
    assert "vm_boot_protection_removed" in {item["code"] for item in report["findings"]}
    assert report["approval_granted"] is False
