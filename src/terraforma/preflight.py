import math
import os
import re
import shutil
import tempfile
from uuid import UUID

from terraforma.artifacts import specification_digest
from terraforma.json_input import strict_json
from terraforma.process import run_bounded
from terraforma.project import ProjectSpecification, compile_project, input_contract


def azure_boot_compatibility(capabilities: list) -> bool | None:
    selected = {}
    for item in capabilities:
        name = str(item.get("name", "")).lower()
        if name not in {"hypervgenerations", "trustedlaunchdisabled"}:
            continue
        if name in selected or not isinstance(item.get("value"), str):
            raise ValueError("Ambiguous or malformed boot capability.")
        selected[name] = item["value"]
    disabled = selected.get("trustedlaunchdisabled")
    if disabled is not None and disabled.lower() not in {"true", "false"}:
        raise ValueError("Unsupported boot capability.")
    generations = selected.get("hypervgenerations")
    if generations is not None:
        generations = [value.strip() for value in generations.split(",")]
        if not generations or any(value not in {"V1", "V2"} for value in generations):
            raise ValueError("Unsupported generation capability.")
    if disabled is not None and disabled.lower() == "true":
        return False
    if generations is None:
        return None
    return "V2" in generations


def machine_report(
    provider: str, data, size: str, location: str, *, require_trusted_launch: bool = False
) -> dict:
    report = {"status": "not_found", "architecture_compatible": None}
    restricted = False
    boot_compatible = None
    if provider == "aws":
        entries = data.get("InstanceTypes") if isinstance(data, dict) else None
        if not isinstance(entries, list) or any(not isinstance(item, dict) for item in entries):
            raise ValueError("Expected instance type metadata.")
        matches = [item for item in entries if item.get("InstanceType") == size]
    elif provider == "azure":
        if not isinstance(data, list) or any(not isinstance(item, dict) for item in data):
            raise ValueError("Expected SKU metadata.")
        matches = [
            item
            for item in data
            if isinstance(item.get("name"), str)
            and item["name"].lower() == size.lower()
            and item.get("resourceType") == "virtualMachines"
        ]
    else:
        if not isinstance(data, dict):
            raise ValueError("Expected machine type metadata.")
        zone = data.get("zone")
        if not isinstance(zone, str) or zone.rstrip("/").split("/")[-1] != location:
            raise ValueError("Machine zone does not match.")
        matches = [data] if data.get("name") == size else []
    if not matches:
        return report
    if len(matches) != 1:
        raise ValueError("Ambiguous machine metadata.")
    machine = matches[0]
    if provider == "aws":
        processor = machine.get("ProcessorInfo")
        if processor is not None and not isinstance(processor, dict):
            raise ValueError("Unsupported processor metadata.")
        architectures = (
            processor.get("SupportedArchitectures") if isinstance(processor, dict) else None
        )
        if architectures is None:
            architectures = []
        if not isinstance(architectures, list) or any(
            value not in {"x86_64", "arm64", "i386", "x86_64_mac", "arm64_mac"}
            for value in architectures
        ):
            raise ValueError("Unsupported architecture metadata.")
        compatible = "x86_64" in architectures if architectures else None
    elif provider == "azure":
        locations = machine.get("locations")
        if not isinstance(locations, list) or any(
            not isinstance(value, str) for value in locations
        ):
            raise ValueError("Unsupported location metadata.")
        if location.lower() not in [value.lower() for value in locations]:
            return report
        capabilities = machine.get("capabilities", [])
        restrictions = machine.get("restrictions", [])
        if not isinstance(capabilities, list) or any(
            not isinstance(item, dict) for item in capabilities
        ):
            raise ValueError("Unsupported capability metadata.")
        if not isinstance(restrictions, list) or any(
            not isinstance(item, dict) or item.get("type") not in {"Location", "Zone"}
            for item in restrictions
        ):
            raise ValueError("Unsupported restriction metadata.")
        architecture = [
            item.get("value")
            for item in capabilities
            if str(item.get("name", "")).lower() == "cpuarchitecturetype"
        ]
        if len(architecture) > 1:
            raise ValueError("Ambiguous architecture metadata.")
        value = architecture[0] if architecture else None
        if value not in {None, "x64", "Arm64", "arm64"}:
            raise ValueError("Unsupported architecture metadata.")
        compatible = value == "x64" if value is not None else None
        restricted = bool(restrictions)
        if require_trusted_launch:
            boot_compatible = azure_boot_compatibility(capabilities)
            report["boot_features_compatible"] = boot_compatible
    else:
        architecture = machine.get("architecture")
        if architecture not in {None, "X86_64", "ARM64", "x86_64", "arm64"}:
            raise ValueError("Unsupported architecture metadata.")
        compatible = architecture in {"X86_64", "x86_64"} if architecture is not None else None
        deprecated = machine.get("deprecated", {})
        if not isinstance(deprecated, dict) or deprecated.get("state") not in {
            None,
            "ACTIVE",
            "DEPRECATED",
            "OBSOLETE",
            "DELETED",
        }:
            raise ValueError("Unsupported deprecation metadata.")
        restricted = deprecated.get("state") not in {None, "ACTIVE"}
    report.update(architecture_compatible=compatible)
    report["status"] = (
        "architecture_incompatible"
        if compatible is False
        else "restricted"
        if restricted
        else "architecture_unknown"
        if compatible is None
        else "boot_features_incompatible"
        if require_trusted_launch and boot_compatible is False
        else "boot_features_unknown"
        if require_trusted_launch and boot_compatible is None
        else "metadata_confirmed"
    )
    return report


def inspect_machine(specification, executable, environment, timeout):
    provider = specification.recipe.provider
    values = {item["name"]: item["default"] for item in input_contract(specification.recipe)}
    values.update(specification.inputs)
    if provider == "aws":
        size, location = values["instance_type"], values["region"]
        arguments = [
            executable,
            "ec2",
            "describe-instance-types",
            "--instance-types",
            size,
            "--region",
            location,
            "--output",
            "json",
            "--no-cli-pager",
            "--no-paginate",
        ]
    elif provider == "azure":
        size, location = values["vm_size"], values["location"]
        arguments = [
            executable,
            "vm",
            "list-skus",
            "--location",
            location,
            "--size",
            size,
            "--resource-type",
            "virtualMachines",
            "--subscription",
            str(UUID(values["subscription_id"])),
            "--all",
            "--output",
            "json",
            "--only-show-errors",
        ]
    else:
        size, location = values["machine_type"], values["zone"]
        arguments = [
            executable,
            "compute",
            "machine-types",
            "describe",
            size,
            "--zone",
            location,
            "--project",
            values["gcp_project_id"],
            "--format=json",
            "--quiet",
        ]
    try:
        with tempfile.TemporaryDirectory(prefix="terraforma_machine_") as directory:
            result = run_bounded(
                arguments, cwd=directory, env=environment, timeout=timeout, stream_limit=128 * 1024
            )
    except OSError:
        return {"status": "failed", "architecture_compatible": None}
    if result.failure or result.returncode != 0:
        return {"status": "failed", "architecture_compatible": None}
    try:
        return machine_report(
            provider,
            strict_json(result.stdout),
            size,
            location,
            require_trusted_launch=(
                provider == "azure" and specification.recipe.architecture_type == "virtual_machine"
            ),
        )
    except (ValueError, TypeError, RecursionError):
        return {"status": "invalid_response", "architecture_compatible": None}


def target_preflight(
    specification: ProjectSpecification,
    *,
    verify_target: bool = False,
    verify_machine: bool = False,
    timeout: float = 30,
) -> dict:
    if (
        type(verify_target) is not bool
        or type(verify_machine) is not bool
        or type(timeout) not in {int, float}
        or not math.isfinite(timeout)
        or not 0 < timeout <= 120
    ):
        raise ValueError("Use a boolean opt-in and a finite timeout from 0 to 120 seconds.")
    if verify_machine and not verify_target:
        raise ValueError("VM metadata checks require target-check consent.")
    project = compile_project(specification)
    provider = project["target"]["provider"]
    expected = project["target"]["account_reference"]
    tool = {"aws": "aws", "azure": "az", "gcp": "gcloud"}[provider]
    report = {
        "schema_version": 1,
        "provider": provider,
        "specification_sha256": specification_digest(project["specification"]),
        "check": {
            "aws": "caller_account",
            "azure": "subscription_metadata",
            "gcp": "project_metadata",
        }[provider],
        "status": "not_checked",
        "target_matches": None,
        "target_state_acceptable": None,
        "deployment_readiness_verified": False,
        "approval_granted": False,
        "machine_check": {"status": "not_checked", "architecture_compatible": None},
        "message": "Account checks are off. Use --verify-target to run a bounded cloud CLI read with its existing credentials.",
        "limitations": "Trusted configured cloud CLI output only. No verification of Terraform credential equivalence, principal permissions, endpoint trust, region/image/SKU availability, quotas, network reachability or deployment readiness. CLI authentication may refresh its local credential cache. This report does not authorize provisioning.",
    }
    if not verify_target:
        return report
    executable = shutil.which(tool)
    if executable is None:
        report.update(
            status="unavailable",
            message=f"Install the official {tool} CLI on PATH and authenticate it separately.",
        )
        return report
    if provider == "aws":
        arguments = [
            executable,
            "sts",
            "get-caller-identity",
            "--output",
            "json",
            "--no-cli-pager",
            "--endpoint-url",
            "https://sts.amazonaws.com",
            "--region",
            "us-east-1",
        ]
    elif provider == "azure":
        arguments = [
            executable,
            "rest",
            "--method",
            "GET",
            "--url",
            f"/subscriptions/{UUID(expected)}?api-version=2022-12-01",
            "--output",
            "json",
            "--only-show-errors",
        ]
    else:
        arguments = [executable, "projects", "describe", expected, "--format=json", "--quiet"]
    environment = {
        name: value
        for name, value in os.environ.items()
        if not name.startswith(("OPENAI_", "TF_VAR_", "TF_CLI_ARGS"))
    }
    environment.update(
        AWS_PAGER="",
        AWS_CLI_AUTO_PROMPT="off",
        AZURE_EXTENSION_USE_DYNAMIC_INSTALL="no",
        AZURE_CORE_COLLECT_TELEMETRY="no",
        CLOUDSDK_CORE_DISABLE_PROMPTS="1",
        CLOUDSDK_CORE_DISABLE_USAGE_REPORTING="true",
    )
    try:
        with tempfile.TemporaryDirectory(prefix="terraforma_preflight_") as directory:
            result = run_bounded(
                arguments, cwd=directory, env=environment, timeout=timeout, stream_limit=128 * 1024
            )
    except OSError:
        report.update(
            status="failed",
            message="Unable to run the cloud CLI. Check its installation and authentication separately; command details are omitted.",
        )
        return report
    if result.failure or result.returncode != 0:
        report.update(
            status="failed",
            message="The cloud CLI check failed or exceeded its limits. Check authentication and target access separately; raw diagnostics are omitted.",
        )
        return report
    try:
        data = strict_json(result.stdout)
        if not isinstance(data, dict):
            raise TypeError("Expected an object.")
        field = {"aws": "Account", "azure": "subscriptionId", "gcp": "projectId"}[provider]
        observed = data.get(field)
        if not isinstance(observed, str):
            raise TypeError("Expected a target identifier.")
        if provider == "aws":
            if not re.fullmatch(r"[0-9]{12}", observed):
                raise ValueError("Invalid account identifier.")
            matches = observed == expected
            acceptable = None
        elif provider == "azure":
            matches = UUID(observed) == UUID(expected)
            state = data.get("state")
            if state not in {"Enabled", "Warned", "PastDue", "Disabled", "Deleted"}:
                raise ValueError("Unsupported subscription state.")
            acceptable = state == "Enabled"
        else:
            if not re.fullmatch(r"[a-z][a-z0-9\-]{4,28}[a-z0-9]", observed):
                raise ValueError("Invalid project identifier.")
            matches = observed == expected
            state = data.get("lifecycleState")
            if state not in {"ACTIVE", "DELETE_REQUESTED", "DELETE_IN_PROGRESS"}:
                raise ValueError("Unsupported project state.")
            acceptable = state == "ACTIVE"
    except (ValueError, TypeError, RecursionError):
        report.update(
            status="invalid_response",
            message="The cloud CLI returned unsupported or ambiguous target metadata; values are omitted.",
        )
        return report
    report.update(target_matches=matches, target_state_acceptable=acceptable)
    if not matches:
        report.update(
            status="target_mismatch",
            message="The reported account, subscription or project does not match this questionnaire. Check the CLI's selected credentials and configuration.",
        )
    elif acceptable is False:
        report.update(
            status="target_not_ready",
            message="The matching target is not in the required Enabled/ACTIVE state. Resolve its state before planning.",
        )
    else:
        report.update(
            status="target_confirmed",
            message="The cloud CLI reports the requested target. Resource permissions and deployment readiness remain unverified.",
        )
        if verify_machine:
            report["machine_check"] = (
                inspect_machine(specification, executable, environment, timeout)
                if specification.recipe.architecture_type
                in {"virtual_machine", "single_web_server", "load_balanced_tier"}
                else {"status": "not_applicable", "architecture_compatible": None}
            )
    return report
