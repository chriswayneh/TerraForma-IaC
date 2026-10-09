import hashlib
import ipaddress
import re
from collections import Counter
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from terraforma.file_input import read_regular_bytes
from terraforma.initialization_review import initialization_findings
from terraforma.json_input import strict_json

MAX_PLAN_BYTES = 8 * 1024 * 1024
MAX_RESOURCES = 2000
POLICY_VERSION = "0.12.0"
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


def metadata_hop_findings(change: dict) -> list[tuple[str, str, str]]:
    options = change["after"].get("metadata_options")
    if options is None or options == []:
        settings = {}
    elif isinstance(options, list) and len(options) == 1 and isinstance(options[0], dict):
        settings = options[0]
    else:
        raise ValueError("Metadata options must contain one object.")
    hops = settings.get("http_put_response_hop_limit")
    if hops is not None and (type(hops) is not int or not 1 <= hops <= 64):
        raise ValueError("Metadata response hops must be a supported integer.")
    unknown = change.get("after_unknown", {})
    if not isinstance(unknown, dict):
        raise TypeError("Unknown metadata controls must be an object.")
    markers = unknown.get("metadata_options", False)
    if type(markers) is bool:
        endpoint_unknown = hops_unknown = markers
    elif isinstance(markers, list) and len(markers) == 1 and isinstance(markers[0], dict):
        endpoint_unknown = markers[0].get("http_endpoint", False)
        hops_unknown = markers[0].get("http_put_response_hop_limit", False)
        if type(endpoint_unknown) is not bool or type(hops_unknown) is not bool:
            raise ValueError("Metadata control markers must be boolean.")
    else:
        raise ValueError("Unknown metadata options have an unsupported shape.")
    if settings.get("http_endpoint") == "disabled" and not endpoint_unknown:
        return []
    if hops is None or hops_unknown or endpoint_unknown or settings.get("http_endpoint") is None:
        return [
            (
                "instance_metadata_hops_unknown",
                "review",
                "The plan does not establish the effective metadata token-response hop limit and endpoint state. Verify account/AMI defaults and workload access before provisioning.",
            )
        ]
    if hops > 1:
        return [
            (
                "instance_metadata_extra_hops",
                "review",
                "Metadata token responses can cross an additional network hop. This can support container networking and expand access to instance credentials; review workload isolation and least-privilege IAM separately.",
            )
        ]
    return []


def gcp_disk_key_findings(resource_type: str, change: dict) -> list[tuple[str, str, str]]:
    vm = resource_type == "google_compute_instance"
    block_name = "boot_disk" if vm else "disk_encryption_key"
    raw_fields = ("disk_encryption_key_raw",) if vm else ("raw_key", "rsa_encrypted_key")
    fields = ("kms_key_self_link", *raw_fields)

    def settings(values):
        if values is None:
            return {}
        if not isinstance(values, dict):
            raise TypeError("Disk resource values must be an object.")
        blocks = values.get(block_name)
        if blocks is None or blocks == []:
            return {}
        if not isinstance(blocks, list) or len(blocks) != 1 or not isinstance(blocks[0], dict):
            raise TypeError("Disk key controls must contain one object.")
        result = blocks[0]
        for field in fields:
            value = result.get(field)
            if value is not None and (not isinstance(value, str) or len(value) > 4096):
                raise ValueError("Disk key controls have unsupported values.")
        return result

    after = settings(change["after"])
    before = settings(change.get("before"))
    unknown = change.get("after_unknown", {})
    if not isinstance(unknown, dict):
        raise TypeError("Unknown disk key controls must be an object.")
    markers = unknown.get(block_name, False)
    if type(markers) is bool:
        unresolved = markers
    elif markers == []:
        unresolved = False
    elif isinstance(markers, list) and len(markers) == 1 and isinstance(markers[0], dict):
        relevant = [markers[0].get(field, False) for field in fields]
        if any(type(marker) is not bool for marker in relevant):
            raise TypeError("Disk key markers must be boolean.")
        unresolved = any(relevant)
    else:
        raise TypeError("Unknown disk key controls have an unsupported shape.")
    findings = []
    if any(values.get(field) for values in (before, after) for field in raw_fields):
        findings.append(
            (
                "inline_disk_key_material",
                "block",
                "The plan contains prior or planned customer-supplied disk key material. Review protected configuration, state and plan handling separately; raw key values are omitted from this report.",
            )
        )
    if unresolved or (vm and not after):
        findings.append(
            (
                "disk_encryption_key_unknown",
                "review",
                "The plan does not establish the disk encryption-key configuration. Verify key ownership, access and recovery separately.",
            )
        )
    else:
        key = after.get("kms_key_self_link") or ""
        previous = before.get("kms_key_self_link") or ""
        if key:
            findings.append(
                (
                    "disk_key_access_unverified",
                    "review",
                    "A disk references a Cloud KMS key. Enabled key versions, compatible location, Compute Engine service-agent permissions and recovery remain unverified; disk retention does not preserve key access.",
                )
            )
        if change.get("before") is not None and key != previous:
            findings.append(
                (
                    "disk_encryption_key_changed",
                    "block",
                    "Disk encryption-key ownership or reference changes require separate migration, access and recovery review. This report does not approve the change or establish an in-place migration.",
                )
            )
    return findings


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


def known_marker(value: Any) -> bool:
    if value is False:
        return True
    if isinstance(value, dict):
        return all(isinstance(key, str) and known_marker(item) for key, item in value.items())
    if isinstance(value, list):
        return all(known_marker(item) for item in value)
    return False


def iap_admin_rule(change: dict, sources: list, ports: list, protocol: str) -> bool:
    after = change["after"]
    unknown = change.get("after_unknown", {})
    fields = (
        "source_ranges",
        "source_tags",
        "source_service_accounts",
        "target_tags",
        "target_service_accounts",
        "allow",
        "direction",
        "disabled",
    )
    if not isinstance(unknown, dict) or any(
        not known_marker(unknown.get(field, False)) for field in fields
    ):
        return False
    targets = after.get("target_tags")
    rules = after.get("allow")
    return (
        after.get("direction") == "INGRESS"
        and after.get("disabled") is False
        and sources == ["35.235.240.0/20"]
        and ports in (["22"], ["3389"])
        and protocol == "tcp"
        and isinstance(rules, list)
        and len(rules) == 1
        and rules[0].get("protocol") == "tcp"
        and isinstance(targets, list)
        and len(targets) == 1
        and isinstance(targets[0], str)
        and re.fullmatch(r"[a-z](?:[-a-z0-9]{0,61}[a-z0-9])?", targets[0]) is not None
        and after.get("source_tags", []) == []
        and after.get("source_service_accounts", []) == []
        and after.get("target_service_accounts", []) == []
    )


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
    "azurerm_linux_virtual_machine",
    "azurerm_windows_virtual_machine",
    "aws_instance",
    "aws_ebs_volume",
    "aws_volume_attachment",
    "aws_db_instance",
    "azurerm_managed_disk",
    "google_compute_instance",
    "google_compute_instance_template",
    "google_compute_disk",
}


def metadata_boolean(metadata, field: str) -> bool | None:
    if metadata is None:
        return None
    if not isinstance(metadata, dict):
        raise TypeError("Metadata must be an object.")
    value = metadata.get(field)
    if value is None:
        return None
    if not isinstance(value, str):
        raise TypeError("Metadata control must be a string.")
    if value.lower() in {"true", "y", "yes", "1"}:
        return True
    if value.lower() in {"false", "n", "no", "0"}:
        return False
    raise ValueError("Unsupported metadata control.")


def planned_boolean(values: dict, field: str) -> bool | None:
    value = values.get(field)
    if value is not None and not isinstance(value, bool):
        raise TypeError("Policy control must be boolean.")
    return value


def azure_disk_access_findings(change: dict) -> list[tuple[str, str, str]]:
    after = change["after"]
    before = change.get("before")
    unknown = change.get("after_unknown", {})
    if before is not None and not isinstance(before, dict):
        raise TypeError("Previous disk values must be an object.")
    if not isinstance(unknown, dict):
        raise TypeError("Unknown disk values must be an object.")
    for values in (before or {}, after):
        policy = values.get("network_access_policy")
        if policy is not None and (
            not isinstance(policy, str) or policy not in {"DenyAll", "AllowPrivate", "AllowAll"}
        ):
            raise ValueError("Unsupported disk network access policy.")
        planned_boolean(values, "public_network_access_enabled")
    for field in ("network_access_policy", "public_network_access_enabled"):
        if not isinstance(unknown.get(field, False), bool):
            raise TypeError("Unknown disk access markers must be boolean.")
    policy = None if unknown.get("network_access_policy") else after.get("network_access_policy")
    public = (
        None
        if unknown.get("public_network_access_enabled")
        else planned_boolean(after, "public_network_access_enabled")
    )
    findings = []
    if policy == "AllowAll":
        findings.append(
            (
                "managed_disk_export_unrestricted",
                "block",
                "The managed disk permits unrestricted remote import/export. Restrict its network access before provisioning; this review does not establish export authorization or effective connectivity.",
            )
        )
    elif policy == "AllowPrivate":
        removed = (before or {}).get("network_access_policy") == "DenyAll"
        findings.append(
            (
                "managed_disk_export_protection_removed"
                if removed
                else "managed_disk_private_export",
                "block" if removed else "review",
                "The managed disk permits private remote import/export. Review the change from disabled export when applicable, its disk access binding, private endpoint, permissions and recovery workflow separately.",
            )
        )
    elif policy is None:
        findings.append(
            (
                "managed_disk_export_unknown",
                "review",
                "The plan does not establish the managed disk remote import/export network policy.",
            )
        )
    if public is True:
        findings.append(
            (
                "managed_disk_public_network",
                "block",
                "The managed disk enables public network access for permitted import/export operations. Disable this setting; other policy settings may restrict effective access but do not resolve this finding.",
            )
        )
    elif public is None:
        findings.append(
            (
                "managed_disk_public_network_unknown",
                "review",
                "The plan does not establish whether managed disk public network access is disabled.",
            )
        )
    return findings


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
        try:
            for code, severity, message in initialization_findings(resource_type, change):
                add(code, severity, resource_id, message)
        except (ValueError, KeyError, TypeError):
            add(
                "unresolved_policy_input",
                "block",
                resource_id,
                "An initialization-relevant field is malformed or unsupported; review it manually.",
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
            if resource_type == "azurerm_managed_disk":
                for code, severity, message in azure_disk_access_findings(change):
                    add(code, severity, resource_id, message)
            if resource_type in {"google_compute_instance", "google_compute_instance_template"}:
                enabled = metadata_boolean(after.get("metadata"), "serial-port-enable")
                before = change.get("before")
                if before is not None and not isinstance(before, dict):
                    raise TypeError("Previous resource values must be an object.")
                previously_enabled = metadata_boolean(
                    (before or {}).get("metadata"), "serial-port-enable"
                )
                if enabled is True:
                    add(
                        "interactive_serial_console",
                        "block",
                        resource_id,
                        "Interactive serial console access is enabled. Ordinary VM firewall/IP allowlists do not restrict this access path; review cloud IAM, keys and organization controls separately.",
                    )
                elif enabled is None:
                    add(
                        "serial_console_unknown",
                        "review",
                        resource_id,
                        "The plan does not establish that interactive serial console access is disabled. Instance metadata can inherit project settings; verify effective access controls.",
                    )
                    if previously_enabled is False:
                        add(
                            "serial_console_protection_removed",
                            "block",
                            resource_id,
                            "This change removes an explicit serial-console disable setting. Project inheritance can enable access; review the protection change separately.",
                        )
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
                for code, severity, message in metadata_hop_findings(change):
                    add(code, severity, resource_id, message)
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
            elif resource_type in {
                "azurerm_linux_virtual_machine",
                "azurerm_windows_virtual_machine",
            }:
                before = change.get("before")
                if before is not None and not isinstance(before, dict):
                    raise TypeError("Previous resource values must be an object.")
                for field, label in (
                    ("secure_boot_enabled", "Secure Boot"),
                    ("vtpm_enabled", "vTPM"),
                ):
                    enabled = planned_boolean(after, field)
                    previously_enabled = planned_boolean(before or {}, field)
                    if enabled is False:
                        add(
                            "vm_boot_protection_removed"
                            if previously_enabled is True
                            else "vm_boot_protection_disabled",
                            "block" if previously_enabled is True else "review",
                            resource_id,
                            f"Azure VM {label} is disabled. Review workload compatibility and the protection change separately; this report does not approve the change.",
                        )
                    elif enabled is None:
                        add(
                            "vm_boot_protection_unknown",
                            "review",
                            resource_id,
                            f"The plan does not establish Azure VM {label}. Verify Trusted Launch support and effective settings before provisioning.",
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
                    if resource_type == "google_compute_firewall" and iap_admin_rule(
                        change, sources, ports, protocol
                    ):
                        add(
                            "iap_admin_ingress",
                            "review",
                            resource_id,
                            "A narrowly targeted rule uses Google's IAP proxy source for one administrator port. Review tunnel IAM, guest authentication and target scope; access is not approved.",
                        )
                    else:
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
            if resource_type in {"google_compute_instance", "google_compute_disk"}:
                for code, severity, message in gcp_disk_key_findings(resource_type, change):
                    add(code, severity, resource_id, message)
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
    raw = read_regular_bytes(path, MAX_PLAN_BYTES)
    return review_bytes(raw)


def review_bytes(raw: bytes) -> dict:
    if len(raw) > MAX_PLAN_BYTES:
        raise ValueError("Plan JSON exceeds the 8 MiB review limit.")
    try:
        data = strict_json(raw)
    except (ValueError, UnicodeError, RecursionError):
        raise ValueError("Plan file is not valid JSON.") from None
    return review_plan(data, artifact_sha256=hashlib.sha256(raw).hexdigest())
