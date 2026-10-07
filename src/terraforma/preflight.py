import math
import os
import re
import shutil
import tempfile
from uuid import UUID

from terraforma.artifacts import specification_digest
from terraforma.json_input import strict_json
from terraforma.process import run_bounded
from terraforma.project import ProjectSpecification, compile_project


def target_preflight(
    specification: ProjectSpecification, *, verify_target: bool = False, timeout: float = 30
) -> dict:
    if type(verify_target) is not bool or not math.isfinite(timeout) or not 0 < timeout <= 120:
        raise ValueError("Use a boolean opt-in and a finite timeout from 0 to 120 seconds.")
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
    return report
