import hashlib
import ipaddress
import json
import re
from collections import Counter
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

MAX_PLAN_BYTES = 8 * 1024 * 1024
MAX_RESOURCES = 2000
POLICY_VERSION = "0.4.0"
ADMIN_PORTS = {22, 3389, 5985, 5986}
PRIVATE_NETWORKS = tuple(
    ipaddress.ip_network(value)
    for value in ("10.0.0.0/8", "172.16.0.0/12", "192.168.0.0/16", "fc00::/7")
)


@dataclass(frozen=True)
class Finding:
    code: str
    severity: str
    resource_id: str
    message: str


def public_source(value: Any) -> bool:
    if not isinstance(value, str):
        raise TypeError("Network source must be a string.")
    if value.lower() in {"*", "internet", "any"}:
        return True
    try:
        network = ipaddress.ip_network(value, strict=False)
    except ValueError:
        raise ValueError("Network source requires manual review.") from None
    return not any(
        network.version == private.version and network.subnet_of(private)
        for private in PRIVATE_NETWORKS
    )


def administrative_ports(values: list[Any]) -> bool:
    if not values:
        return True
    for value in values:
        if str(value) == "*":
            return True
        if not re.fullmatch(r"\d{1,5}(?:-\d{1,5})?", str(value)):
            raise ValueError("Port selection requires manual review.")
        parts = str(value).split("-")
        lower, upper = int(parts[0]), int(parts[-1])
        if not 0 <= lower <= upper <= 65535:
            raise ValueError("Port range is invalid.")
        if any(lower <= port <= upper for port in ADMIN_PORTS):
            return True
    return False


def unknown_values(value: Any) -> bool:
    if isinstance(value, dict):
        return any(unknown_values(item) for item in value.values())
    if isinstance(value, list):
        return any(unknown_values(item) for item in value)
    return value is True


def network_rules(resource_type: str, after: dict) -> list[tuple[list, list, str]]:
    rules = []
    if resource_type == "aws_security_group":
        for rule in after.get("ingress", []):
            protocol = str(rule.get("protocol", "-1")).lower()
            ports = [] if protocol == "-1" else [f"{rule['from_port']}-{rule['to_port']}"]
            rules.append(
                (rule.get("cidr_blocks", []) + rule.get("ipv6_cidr_blocks", []), ports, protocol)
            )
    elif resource_type == "aws_vpc_security_group_ingress_rule":
        protocol = str(after.get("ip_protocol", "-1")).lower()
        ports = [] if protocol == "-1" else [f"{after['from_port']}-{after['to_port']}"]
        rules.append(
            (
                [value for value in (after.get("cidr_ipv4"), after.get("cidr_ipv6")) if value],
                ports,
                protocol,
            )
        )
    elif resource_type == "azurerm_network_security_rule":
        if (
            after.get("direction", "").lower() == "inbound"
            and after.get("access", "").lower() == "allow"
        ):
            sources = after.get("source_address_prefixes") or [after.get("source_address_prefix")]
            ports = after.get("destination_port_ranges") or [after.get("destination_port_range")]
            rules.append((sources, ports, str(after.get("protocol", "*")).lower()))
    elif (
        resource_type == "google_compute_firewall"
        and after.get("direction", "INGRESS") == "INGRESS"
        and not after.get("disabled", False)
    ):
        for rule in after.get("allow", []):
            rules.append(
                (
                    after.get("source_ranges") or ["0.0.0.0/0"],
                    rule.get("ports", []),
                    str(rule.get("protocol", "all")).lower(),
                )
            )
    return rules


NETWORK_TYPES = {
    "aws_security_group",
    "aws_vpc_security_group_ingress_rule",
    "azurerm_network_security_rule",
    "google_compute_firewall",
}
POLICY_TYPES = NETWORK_TYPES | {
    "aws_instance",
    "aws_ebs_volume",
    "aws_volume_attachment",
    "aws_db_instance",
    "google_compute_instance",
}


def planned_boolean(values: dict, field: str) -> bool | None:
    value = values.get(field)
    if value is not None and not isinstance(value, bool):
        raise TypeError("Policy control must be boolean.")
    return value


def review_plan(data: dict, *, artifact_sha256: str) -> dict:
    if not isinstance(data, dict) or not re.fullmatch(
        r"1\.\d+", str(data.get("format_version", ""))
    ):
        raise ValueError("Expected Terraform plan JSON with a supported format version (1.x).")
    if "planned_values" not in data or "configuration" not in data:
        raise ValueError("Expected a plan, not Terraform state or event-stream JSON.")
    changes = data.get("resource_changes", [])
    if not isinstance(changes, list) or len(changes) > MAX_RESOURCES:
        raise ValueError("Plan resource changes exceed the supported review limit.")
    findings: list[Finding] = []
    counts: Counter = Counter()

    def add(code: str, severity: str, resource_id: str, message: str):
        findings.append(Finding(code, severity, resource_id, message))

    for flag in ("errored", "complete", "applyable"):
        if flag in data and not isinstance(data[flag], bool):
            raise ValueError("Plan status flags must be boolean.")
    if data.get("errored") is True:
        add("planning_failed", "block", "plan", "Terraform reported a planning error.")
    if data.get("complete") is False:
        add(
            "incomplete_plan",
            "block",
            "plan",
            "This plan requires another planning round to converge.",
        )
    if "complete" not in data:
        add(
            "completion_unknown",
            "review",
            "plan",
            "This export does not declare plan completeness.",
        )
    if data.get("applyable") is False:
        add(
            "not_applyable",
            "review",
            "plan",
            "Terraform does not mark this plan as applyable; it may contain no changes.",
        )
    checks = data.get("checks", [])
    if not isinstance(checks, list):
        raise TypeError("Plan checks must be a list.")
    for check in checks:
        if not isinstance(check, dict) or check.get("status") not in {
            "pass",
            "fail",
            "error",
            "unknown",
        }:
            raise ValueError("Plan check has an unsupported status.")
        if check["status"] != "pass":
            add(
                "unresolved_check",
                "block",
                "plan",
                "A Terraform check failed or has an unresolved result.",
            )
    for resource in changes:
        if not isinstance(resource, dict):
            raise TypeError("Resource change must be an object.")
        resource_type = resource.get("type")
        address = resource.get("address")
        mode = resource.get("mode")
        if not isinstance(resource_type, str) or not re.fullmatch(
            r"[a-z][a-z0-9_]{1,100}", resource_type
        ):
            raise ValueError("Resource type is malformed.")
        if not isinstance(address, str) or len(address) > 2048 or mode not in {"managed", "data"}:
            raise ValueError("Resource identity is malformed.")
        resource_id = resource_type + ":" + hashlib.sha256(address.encode()).hexdigest()[:12]
        change = resource.get("change")
        if not isinstance(change, dict):
            raise TypeError("Resource change details are missing.")
        actions = change.get("actions")
        valid_actions = [
            ["no-op"],
            ["create"],
            ["read"],
            ["update"],
            ["delete"],
            ["delete", "create"],
            ["create", "delete"],
            ["forget"],
        ]
        if actions not in valid_actions:
            raise ValueError("Resource change has an unsupported action sequence.")
        label = "replace" if len(actions) == 2 else actions[0]
        counts[label] += 1
        if "delete" in actions or "forget" in actions:
            add(
                "destructive_change",
                "block",
                resource_id,
                "Deletion, replacement, or removal from state requires separate destructive approval.",
            )
        if mode == "data" or actions == ["delete"] or actions == ["forget"]:
            continue
        after = change.get("after")
        if not isinstance(after, dict):
            add(
                "unknown_configuration",
                "block",
                resource_id,
                "Planned resource values are unavailable for policy review.",
            )
            continue
        if unknown_values(change.get("after_unknown", {})):
            add(
                "unknown_values",
                "review",
                resource_id,
                "Some planned values are unknown; review cannot establish their safety.",
            )
        if resource_type not in POLICY_TYPES:
            add(
                "policy_coverage_gap",
                "review",
                resource_id,
                "This resource has no resource-specific policy rules in this reviewer.",
            )
            continue
        add(
            "limited_policy_coverage",
            "review",
            resource_id,
            "Only the documented initial checks are implemented; manual review remains required.",
        )
        try:
            if resource_type == "aws_instance":
                options = after.get("metadata_options")
                if options is None or options == []:
                    add(
                        "instance_metadata_unknown",
                        "review",
                        resource_id,
                        "The plan does not establish instance metadata endpoint and token settings.",
                    )
                else:
                    if (
                        not isinstance(options, list)
                        or len(options) != 1
                        or not isinstance(options[0], dict)
                    ):
                        raise TypeError("Metadata options must contain one object.")
                    endpoint = options[0].get("http_endpoint")
                    tokens = options[0].get("http_tokens")
                    if endpoint not in {None, "enabled", "disabled"} or tokens not in {
                        None,
                        "required",
                        "optional",
                    }:
                        raise ValueError("Metadata controls have unsupported values.")
                    if endpoint != "disabled":
                        if tokens == "optional":
                            add(
                                "legacy_instance_metadata",
                                "block",
                                resource_id,
                                "Instance metadata permits tokenless IMDSv1 requests. Require IMDSv2 or disable the metadata endpoint before provisioning.",
                            )
                        elif endpoint is None or tokens is None:
                            add(
                                "instance_metadata_unknown",
                                "review",
                                resource_id,
                                "The plan does not establish whether IMDSv2 tokens are required for the metadata endpoint.",
                            )
                profile = after.get("iam_instance_profile")
                if profile is not None and not isinstance(profile, str):
                    raise TypeError("Instance profile must be a string.")
                if profile:
                    add(
                        "identity_permissions_unknown",
                        "review",
                        resource_id,
                        "An IAM instance profile is attached, but this plan review does not establish its role policies, trust or attachment authorization. Review least privilege separately.",
                    )
            elif resource_type == "google_compute_instance":
                shielded = after.get("shielded_instance_config")
                before = change.get("before")
                if before is not None and not isinstance(before, dict):
                    raise TypeError("Previous resource values must be an object.")
                previous_shielded = (before or {}).get("shielded_instance_config")
                for settings in (shielded, previous_shielded):
                    if (
                        settings is not None
                        and settings != []
                        and (
                            not isinstance(settings, list)
                            or len(settings) != 1
                            or not isinstance(settings[0], dict)
                        )
                    ):
                        raise TypeError("Shielded VM settings must contain one object.")
                current = shielded[0] if shielded else {}
                previous = previous_shielded[0] if previous_shielded else {}
                for field, label in (
                    ("enable_secure_boot", "Secure Boot"),
                    ("enable_vtpm", "vTPM"),
                    ("enable_integrity_monitoring", "integrity monitoring"),
                ):
                    enabled = planned_boolean(current, field)
                    previously_enabled = planned_boolean(previous, field)
                    if enabled is False:
                        add(
                            "vm_boot_protection_removed"
                            if previously_enabled is True
                            else "vm_boot_protection_disabled",
                            "block" if previously_enabled is True else "review",
                            resource_id,
                            f"Shielded VM {label} is disabled. Review workload compatibility and the protection change separately; this report does not approve the change.",
                        )
                    elif enabled is None:
                        add(
                            "vm_boot_protection_unknown",
                            "review",
                            resource_id,
                            f"The plan does not establish Shielded VM {label}. Review image support and effective settings before provisioning.",
                        )
                accounts = after.get("service_account")
                if accounts is not None and accounts != []:
                    if (
                        not isinstance(accounts, list)
                        or len(accounts) != 1
                        or not isinstance(accounts[0], dict)
                    ):
                        raise TypeError("Service account must contain one object.")
                    email = accounts[0].get("email")
                    if email is not None and not isinstance(email, str):
                        raise TypeError("Service account email must be a string.")
                    add(
                        "identity_permissions_unknown",
                        "review",
                        resource_id,
                        "A service account is attached, but this plan review does not establish its IAM roles or attachment authorization. OAuth scopes do not prove least privilege.",
                    )
            if resource_type in {"aws_instance", "google_compute_instance"}:
                field = (
                    "disable_api_termination"
                    if resource_type == "aws_instance"
                    else "deletion_protection"
                )
                protected = planned_boolean(after, field)
                before = change.get("before")
                if before is not None and not isinstance(before, dict):
                    raise TypeError("Previous resource values must be an object.")
                previously_protected = planned_boolean(before or {}, field)
                if protected is False:
                    if previously_protected is True:
                        add(
                            "vm_protection_removed",
                            "block",
                            resource_id,
                            "This change disables an existing VM deletion protection control. Review the lifecycle intent and data preservation separately.",
                        )
                    else:
                        add(
                            "vm_protection_disabled",
                            "review",
                            resource_id,
                            "VM deletion protection is disabled. Review whether this matches the intended lifecycle; this control does not protect every deletion path or connected disk.",
                        )
                elif protected is None:
                    add(
                        "vm_protection_unknown",
                        "review",
                        resource_id,
                        "The plan does not establish VM deletion protection. Verify the provider setting before provisioning.",
                    )
            if resource_type == "aws_volume_attachment":
                forced = planned_boolean(after, "force_detach")
                if forced is True:
                    add(
                        "forced_disk_detach",
                        "block",
                        resource_id,
                        "The attachment permits forced disk detach, which can damage the filesystem or lose data. Review recovery and data preservation separately.",
                    )
                elif forced is None:
                    add(
                        "disk_detach_unknown",
                        "review",
                        resource_id,
                        "The plan does not establish whether forced disk detach is disabled.",
                    )
            for sources, ports, protocol in network_rules(resource_type, after):
                if not isinstance(sources, list) or not isinstance(ports, list):
                    raise TypeError("Malformed network rule.")
                if (
                    protocol in {"tcp", "6", "-1", "*", "all"}
                    and administrative_ports(ports)
                    and any(public_source(source) for source in sources)
                ):
                    add(
                        "public_admin_access",
                        "block",
                        resource_id,
                        "An inbound rule permits administrative ports from outside private network ranges.",
                    )
            if resource_type == "aws_instance":
                disks = after.get("root_block_device", []) + after.get("ebs_block_device", [])
                if not disks:
                    add(
                        "encryption_unknown",
                        "review",
                        resource_id,
                        "Disk encryption is not established by this plan export.",
                    )
                for disk in disks:
                    if disk.get("encrypted") is False:
                        add(
                            "unencrypted_disk",
                            "block",
                            resource_id,
                            "A planned disk explicitly disables encryption.",
                        )
                    elif disk.get("encrypted") is not True:
                        add(
                            "encryption_unknown",
                            "review",
                            resource_id,
                            "Disk encryption requires account/provider verification.",
                        )
            elif resource_type in {"aws_ebs_volume", "aws_db_instance"}:
                field = "encrypted" if resource_type == "aws_ebs_volume" else "storage_encrypted"
                if after.get(field) is False:
                    add(
                        "unencrypted_storage",
                        "block",
                        resource_id,
                        "Planned storage explicitly disables encryption.",
                    )
                elif after.get(field) is not True:
                    add(
                        "encryption_unknown",
                        "review",
                        resource_id,
                        "Storage encryption is unresolved.",
                    )
                if resource_type == "aws_db_instance":
                    if after.get("publicly_accessible") is True:
                        add(
                            "public_database",
                            "block",
                            resource_id,
                            "The database is publicly accessible.",
                        )
                    if after.get("deletion_protection") is not True:
                        add(
                            "database_protection",
                            "block",
                            resource_id,
                            "Database deletion protection is not established.",
                        )
        except (ValueError, KeyError, TypeError, AttributeError):
            add(
                "unresolved_policy_input",
                "block",
                resource_id,
                "A policy-relevant field is malformed or unsupported; review it manually.",
            )
    return {
        "policy_version": POLICY_VERSION,
        "artifact_sha256": artifact_sha256,
        "status": "blocked"
        if any(item.severity == "block" for item in findings)
        else "manual_review_required",
        "approval_granted": False,
        "actions": dict(sorted(counts.items())),
        "findings": [asdict(item) for item in findings],
        "limitations": "Read-only initial checks. This report does not authorize apply, establish account identity, verify binary-plan integrity, or certify infrastructure security.",
    }


def load_and_review(path: Path) -> dict:
    with path.open("rb") as source:
        raw = source.read(MAX_PLAN_BYTES + 1)
    return review_bytes(raw)


def review_bytes(raw: bytes) -> dict:
    if len(raw) > MAX_PLAN_BYTES:
        raise ValueError("Plan JSON exceeds the 8 MiB review limit.")
    try:
        data = json.loads(raw, object_pairs_hook=unique_object, parse_constant=reject_constant)
    except (ValueError, UnicodeError, RecursionError):
        raise ValueError("Plan file is not valid JSON.") from None
    return review_plan(data, artifact_sha256=hashlib.sha256(raw).hexdigest())


def unique_object(pairs: list[tuple[str, Any]]) -> dict:
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("Duplicate JSON keys are unsupported.")
        result[key] = value
    return result


def reject_constant(value: str):
    raise ValueError("Non-finite JSON numbers are unsupported.")
