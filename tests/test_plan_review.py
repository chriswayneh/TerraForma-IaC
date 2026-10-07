import json

import pytest
from click.testing import CliRunner

from terraforma.cli import main
from terraforma.plan_review import load_and_review, review_plan


def plan(resource_type="aws_security_group", after=None, actions=None):
    return {
        "format_version": "1.2",
        "configuration": {},
        "planned_values": {},
        "complete": True,
        "applyable": True,
        "errored": False,
        "resource_changes": [
            {
                "address": resource_type + '.example["private-secret-key"]',
                "mode": "managed",
                "type": resource_type,
                "change": {
                    "actions": actions or ["create"],
                    "after": after or {},
                    "after_unknown": {},
                },
            }
        ],
    }


def codes(data):
    return {finding["code"] for finding in review_plan(data, artifact_sha256="test")["findings"]}


@pytest.mark.parametrize(
    "resource_type,after",
    [
        (
            "aws_security_group",
            {
                "ingress": [
                    {
                        "protocol": "tcp",
                        "from_port": 22,
                        "to_port": 22,
                        "cidr_blocks": ["0.0.0.0/0"],
                        "ipv6_cidr_blocks": [],
                    }
                ]
            },
        ),
        (
            "aws_vpc_security_group_ingress_rule",
            {"ip_protocol": "tcp", "from_port": 3389, "to_port": 3389, "cidr_ipv6": "::/0"},
        ),
        (
            "azurerm_network_security_rule",
            {
                "direction": "Inbound",
                "access": "Allow",
                "protocol": "Tcp",
                "source_address_prefix": "Internet",
                "destination_port_range": "5985-5986",
            },
        ),
        (
            "google_compute_firewall",
            {"allow": [{"protocol": "all"}], "source_ranges": ["0.0.0.0/0"]},
        ),
    ],
)
def test_blocks_internet_admin_access_across_providers(resource_type, after):
    result = review_plan(plan(resource_type, after), artifact_sha256="test")
    assert result["status"] == "blocked"
    assert "public_admin_access" in {finding["code"] for finding in result["findings"]}
    assert result["approval_granted"] is False


@pytest.mark.parametrize("source,port", [("10.1.0.0/16", 22), ("0.0.0.0/0", 443)])
def test_private_admin_and_public_https_require_review_without_admin_block(source, port):
    data = plan(
        after={
            "ingress": [
                {"protocol": "tcp", "from_port": port, "to_port": port, "cidr_blocks": [source]}
            ]
        }
    )
    result = review_plan(data, artifact_sha256="test")
    assert result["status"] == "manual_review_required"
    assert result["approval_granted"] is False
    assert "public_admin_access" not in codes(data)


@pytest.mark.parametrize(
    "actions", [["delete"], ["create", "delete"], ["delete", "create"], ["forget"]]
)
def test_destructive_actions_are_blocked(actions):
    assert "destructive_change" in codes(plan(actions=actions))


@pytest.mark.parametrize(
    "resource_type,after,code",
    [
        ("aws_instance", {"root_block_device": [{"encrypted": False}]}, "unencrypted_disk"),
        ("aws_ebs_volume", {"encrypted": False}, "unencrypted_storage"),
        (
            "aws_db_instance",
            {"storage_encrypted": True, "publicly_accessible": True, "deletion_protection": False},
            "public_database",
        ),
        (
            "aws_db_instance",
            {"storage_encrypted": True, "deletion_protection": False},
            "database_protection",
        ),
    ],
)
def test_storage_and_database_protections(resource_type, after, code):
    assert code in codes(plan(resource_type, after))


@pytest.mark.parametrize(
    "resource_type,field",
    [
        ("aws_instance", "disable_api_termination"),
        ("google_compute_instance", "deletion_protection"),
    ],
)
@pytest.mark.parametrize("protected", [True, False, None])
def test_vm_protection_state_requires_manual_review(resource_type, field, protected):
    data = plan(resource_type, {field: protected})
    findings = codes(data)
    assert ("vm_protection_disabled" in findings) is (protected is False)
    assert ("vm_protection_unknown" in findings) is (protected is None)
    assert "limited_policy_coverage" in findings
    assert review_plan(data, artifact_sha256="test")["approval_granted"] is False


@pytest.mark.parametrize(
    "resource_type,field",
    [
        ("aws_instance", "disable_api_termination"),
        ("google_compute_instance", "deletion_protection"),
    ],
)
def test_removing_existing_vm_protection_is_blocked_and_private(resource_type, field):
    data = plan(resource_type, {field: False}, ["update"])
    data["resource_changes"][0]["change"]["before"] = {field: True, "secret": "private-secret"}
    report = review_plan(data, artifact_sha256="test")
    assert report["status"] == "blocked"
    assert "vm_protection_removed" in codes(data)
    assert "private-secret" not in json.dumps(report)


@pytest.mark.parametrize("forced", [True, False, None])
def test_forced_attachment_detach_policy(forced):
    data = plan("aws_volume_attachment", {"force_detach": forced})
    findings = codes(data)
    assert ("forced_disk_detach" in findings) is (forced is True)
    assert ("disk_detach_unknown" in findings) is (forced is None)
    report = review_plan(data, artifact_sha256="test")
    assert report["status"] == ("blocked" if forced is True else "manual_review_required")


@pytest.mark.parametrize(
    "resource_type,field",
    [
        ("aws_instance", "disable_api_termination"),
        ("google_compute_instance", "deletion_protection"),
        ("aws_volume_attachment", "force_detach"),
    ],
)
@pytest.mark.parametrize("malformed", ["false", 0, [], {}])
def test_lifecycle_control_types_fail_closed(resource_type, field, malformed):
    assert "unresolved_policy_input" in codes(plan(resource_type, {field: malformed}))


def test_malformed_previous_vm_protection_fails_closed():
    data = plan("google_compute_instance", {"deletion_protection": False}, ["update"])
    data["resource_changes"][0]["change"]["before"] = {"deletion_protection": "true"}
    assert "unresolved_policy_input" in codes(data)


@pytest.mark.parametrize(
    "endpoint,tokens,expected",
    [
        ("enabled", "optional", "legacy_instance_metadata"),
        (None, "optional", "legacy_instance_metadata"),
        ("enabled", None, "instance_metadata_unknown"),
        (None, "required", "instance_metadata_unknown"),
        ("enabled", "required", None),
        ("disabled", "optional", None),
        ("disabled", None, None),
    ],
)
def test_instance_metadata_token_policy(endpoint, tokens, expected):
    report = review_plan(
        plan(
            "aws_instance",
            {"metadata_options": [{"http_endpoint": endpoint, "http_tokens": tokens}]},
        ),
        artifact_sha256="test",
    )
    findings = {finding["code"] for finding in report["findings"]}
    if expected:
        assert expected in findings
    else:
        assert not {"legacy_instance_metadata", "instance_metadata_unknown"} & findings
    assert report["status"] == (
        "blocked" if expected == "legacy_instance_metadata" else "manual_review_required"
    )
    assert report["approval_granted"] is False


@pytest.mark.parametrize("options", [None, []])
def test_missing_metadata_options_remain_unknown(options):
    assert "instance_metadata_unknown" in codes(plan("aws_instance", {"metadata_options": options}))


@pytest.mark.parametrize(
    "options",
    [
        "enabled",
        {},
        [True],
        [{}, {}],
        [{"http_tokens": True}],
        [{"http_endpoint": "private-invalid-value"}],
        [{"http_tokens": []}],
    ],
)
def test_malformed_metadata_controls_fail_closed(options):
    data = plan("aws_instance", {"metadata_options": options})
    assert "unresolved_policy_input" in codes(data)
    assert "private-invalid-value" not in json.dumps(review_plan(data, artifact_sha256="test"))


@pytest.mark.parametrize(
    "resource_type,after",
    [
        ("aws_instance", {"iam_instance_profile": "private-profile-reference"}),
        (
            "google_compute_instance",
            {
                "service_account": [
                    {
                        "email": "private-account@example-project.iam.gserviceaccount.com",
                        "scopes": ["cloud-platform"],
                    }
                ]
            },
        ),
        ("google_compute_instance", {"service_account": [{"email": None}]}),
    ],
)
def test_attached_identity_permissions_are_not_certified_or_disclosed(resource_type, after):
    data = plan(resource_type, after)
    report = review_plan(data, artifact_sha256="test")
    assert "identity_permissions_unknown" in codes(data)
    assert "private-profile-reference" not in json.dumps(report)
    assert "private-account@" not in json.dumps(report)
    assert report["approval_granted"] is False


@pytest.mark.parametrize(
    "resource_type,after",
    [
        ("aws_instance", {"iam_instance_profile": []}),
        ("google_compute_instance", {"service_account": "private-value"}),
        ("google_compute_instance", {"service_account": [{"email": False}]}),
        ("google_compute_instance", {"service_account": [{}, {}]}),
    ],
)
def test_malformed_identity_attachment_fields_fail_closed(resource_type, after):
    assert "unresolved_policy_input" in codes(plan(resource_type, after))


def test_unknown_configuration_and_coverage_remain_visible():
    data = plan("azurerm_linux_virtual_machine", {"password": "private-secret-value"})
    data["resource_changes"][0]["change"]["after_unknown"] = {"disk": [True]}
    report = review_plan(data, artifact_sha256="test")
    assert {"policy_coverage_gap", "unknown_values"} <= codes(data)
    assert "private-secret" not in json.dumps(report)
    assert report["approval_granted"] is False


@pytest.mark.parametrize(
    "field", ["enable_secure_boot", "enable_vtpm", "enable_integrity_monitoring"]
)
@pytest.mark.parametrize("previously_enabled", [None, False, True])
def test_shielded_vm_disabled_controls_and_removal_require_review(field, previously_enabled):
    settings = {
        "enable_secure_boot": True,
        "enable_vtpm": True,
        "enable_integrity_monitoring": True,
    }
    data = plan(
        "google_compute_instance", {"shielded_instance_config": [{**settings, field: False}]}
    )
    data["resource_changes"][0]["change"]["before"] = {
        "shielded_instance_config": [{**settings, field: previously_enabled}]
    }
    report = review_plan(data, artifact_sha256="test")
    expected = (
        "vm_boot_protection_removed"
        if previously_enabled is True
        else "vm_boot_protection_disabled"
    )
    finding = next(item for item in report["findings"] if item["code"] == expected)
    assert finding["severity"] == ("block" if previously_enabled is True else "review")
    assert report["approval_granted"] is False


@pytest.mark.parametrize("settings", [None, [], [{}], [{"enable_secure_boot": None}]])
def test_missing_shielded_controls_remain_review_gaps(settings):
    assert "vm_boot_protection_unknown" in codes(
        plan("google_compute_instance", {"shielded_instance_config": settings})
    )


@pytest.mark.parametrize(
    "settings",
    [
        "private-invalid-value",
        {},
        [False],
        [{}, {}],
        [{"enable_vtpm": "false"}],
        [{"enable_secure_boot": 0}],
    ],
)
@pytest.mark.parametrize("side", ["after", "before"])
def test_malformed_shielded_controls_fail_closed_without_exposing_values(settings, side):
    data = plan("google_compute_instance", {})
    data["resource_changes"][0]["change"][side] = {"shielded_instance_config": settings}
    report = review_plan(data, artifact_sha256="test")
    assert "unresolved_policy_input" in {finding["code"] for finding in report["findings"]}
    assert "private-invalid-value" not in json.dumps(report)


def test_enabled_shielded_controls_do_not_hide_other_policy_gaps():
    data = plan(
        "google_compute_instance",
        {
            "shielded_instance_config": [
                {
                    "enable_secure_boot": True,
                    "enable_vtpm": True,
                    "enable_integrity_monitoring": True,
                }
            ]
        },
    )
    found = codes(data)
    assert (
        not {
            "vm_boot_protection_unknown",
            "vm_boot_protection_disabled",
            "vm_boot_protection_removed",
        }
        & found
    )
    assert {"limited_policy_coverage", "vm_protection_unknown"} <= found


def test_malformed_network_values_fail_closed():
    data = plan(
        "aws_security_group", {"ingress": [{"protocol": "tcp", "from_port": "bad", "to_port": 22}]}
    )
    assert "unresolved_policy_input" in codes(data)


@pytest.mark.parametrize(
    "mutation",
    [
        lambda data: data.update(format_version="2.0"),
        lambda data: data.pop("configuration"),
        lambda data: data.update(resource_changes="unexpected"),
        lambda data: data["resource_changes"][0]["change"].update(actions=["execute"]),
    ],
)
def test_rejects_invalid_plan_contract(mutation):
    data = plan()
    mutation(data)
    with pytest.raises(ValueError):
        review_plan(data, artifact_sha256="test")


def test_plan_status_and_checks():
    data = plan()
    data.update(complete=False, errored=True, checks=[{"status": "unknown"}])
    assert {"incomplete_plan", "planning_failed", "unresolved_check"} <= codes(data)


def test_cli_report_digest_exit_and_no_secret_disclosure(tmp_path):
    source = tmp_path / "plan.json"
    source.write_text(
        json.dumps(plan("aws_ebs_volume", {"encrypted": False, "secret": "do-not-print"}))
    )
    report = load_and_review(source)
    assert len(report["artifact_sha256"]) == 64
    result = CliRunner().invoke(main, ["review-plan", "--file", str(source), "--json-output"])
    assert result.exit_code == 1
    assert json.loads(result.output)["status"] == "blocked"
    assert "do-not-print" not in result.output
    assert "private-secret-key" not in result.output


def test_oversized_and_invalid_files(tmp_path, monkeypatch):
    monkeypatch.setattr("terraforma.plan_review.MAX_PLAN_BYTES", 32)
    source = tmp_path / "plan.json"
    source.write_bytes(b"x" * 33)
    with pytest.raises(ValueError, match="limit"):
        load_and_review(source)
    source.write_bytes(b"private-invalid-json")
    result = CliRunner().invoke(main, ["review-plan", "--file", str(source)])
    assert result.exit_code != 0
    assert "private-invalid-json" not in result.output


@pytest.mark.parametrize("content", ['{"encrypted":true,"encrypted":false}', '{"value":NaN}'])
def test_ambiguous_json_is_rejected(tmp_path, content):
    source = tmp_path / "plan.json"
    source.write_text(content)
    with pytest.raises(ValueError):
        load_and_review(source)
