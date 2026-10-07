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


def test_unknown_configuration_and_coverage_remain_visible():
    data = plan("azurerm_linux_virtual_machine", {"password": "private-secret-value"})
    data["resource_changes"][0]["change"]["after_unknown"] = {"disk": [True]}
    report = review_plan(data, artifact_sha256="test")
    assert {"policy_coverage_gap", "unknown_values"} <= codes(data)
    assert "private-secret" not in json.dumps(report)
    assert report["approval_granted"] is False


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
