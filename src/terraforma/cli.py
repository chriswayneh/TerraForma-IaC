import asyncio
import json
import re
import textwrap
import webbrowser
from pathlib import Path

import click
import questionary
from pydantic import ValidationError

from terraforma import __version__
from terraforma.ai_engine import AIDiagnosticsEngine, DiagnosticsError, redact_sensitive_text
from terraforma.artifacts import checksum_document, project_artifacts, verify_project
from terraforma.catalog import recipe_capabilities, recipe_catalog
from terraforma.generator import WizardConfig, project_destination, write_configuration
from terraforma.network_inputs import usable_vm_address, vm_subnet
from terraforma.plan_review import load_and_review
from terraforma.preflight import target_preflight
from terraforma.project import (
    ProjectInputError,
    ProjectSpecification,
    compile_project,
    input_contract,
    load_specification,
    validate_answer,
)
from terraforma.readiness import local_readiness
from terraforma.sandbox import ValidationSandbox


@click.group()
@click.version_option(__version__)
def main():
    """Generate Terraform and explain local validation failures."""


def ask(prompt):
    answer = prompt.ask()
    if answer is None:
        raise click.Abort()
    return answer


@main.command("doctor")
@click.option("--json-output", is_flag=True, help="Print local availability as JSON.")
@click.option(
    "--require",
    "required_capability",
    type=click.Choice(["generation", "web", "validation", "plan_review"]),
    default="generation",
    show_default=True,
    help="Exit with status 1 when this local capability has missing dependencies.",
)
def doctor_command(json_output: bool, required_capability: str):
    """Check local dependencies without running tools or reading credentials."""
    report = local_readiness()
    if json_output:
        click.echo(json.dumps(report, indent=2))
    else:
        click.echo("Local dependency availability:")
        click.echo("Python 3.11+: " + ("available" if report["python_supported"] else "missing"))
        for name, available in {**report["packages"], **report["tools"]}.items():
            click.echo(f"- {name}: {'available' if available else 'missing'}")
        click.echo("\nCapabilities:")
        for name, available in report["capabilities"].items():
            click.echo(
                f"- {name.replace('_', ' ')}: {'available' if available else 'missing dependencies'}"
            )
        if not all(report["tools"].values()):
            click.echo(
                "Install the missing Terraform/TFLint tools and add them to PATH for validation."
            )
        if not all(report["packages"][name] for name in ("fastapi", "uvicorn")):
            click.echo(
                'From the repository root, install web dependencies: python -m pip install -e ".[web]"'
            )
        click.echo("\n" + report["limitations"])
    if not report["capabilities"][required_capability]:
        raise click.exceptions.Exit(1)


@main.command("preflight")
@click.option(
    "--spec",
    "specification_path",
    required=True,
    type=click.Path(exists=True, dir_okay=False, path_type=Path),
)
@click.option(
    "--verify-target",
    is_flag=True,
    help="Contact the cloud using the installed CLI's existing credentials for a read-only target check.",
)
@click.option(
    "--verify-machine",
    is_flag=True,
    help="Also inspect VM size/architecture metadata after confirming the target; requires --verify-target.",
)
@click.option(
    "--timeout", type=click.FloatRange(min=0, max=120, min_open=True), default=30, show_default=True
)
@click.option(
    "--json-output", is_flag=True, help="Print the bounded target report without raw CLI values."
)
def preflight_command(
    specification_path: Path,
    verify_target: bool,
    verify_machine: bool,
    timeout: float,
    json_output: bool,
):
    """Inspect a saved project; opt in explicitly to cloud target checks."""
    if verify_machine and not verify_target:
        raise click.UsageError("--verify-machine requires --verify-target.")
    try:
        report = target_preflight(
            load_specification(specification_path),
            verify_target=verify_target,
            verify_machine=verify_machine,
            timeout=timeout,
        )
    except (OSError, ValueError, TypeError, RecursionError):
        raise click.ClickException(
            "A supported, valid project specification and timeout are required; input values are omitted."
        ) from None
    if json_output:
        click.echo(json.dumps(report, indent=2))
    else:
        click.echo(f"{report['provider']}: {report['status']}")
        click.echo(report["message"])
        if verify_machine:
            click.echo(f"VM size metadata: {report['machine_check']['status']}")
        click.echo(report["limitations"])
    if report["status"] not in {"not_checked", "target_confirmed"}:
        raise click.exceptions.Exit(1)
    if verify_machine and report["machine_check"]["status"] not in {
        "metadata_confirmed",
        "not_applicable",
    }:
        raise click.exceptions.Exit(1)


def collect_recipe_inputs(config: WizardConfig) -> ProjectSpecification:
    inputs = {}
    references = {}
    click.echo("Recipe defaults and limits:")
    for choice in recipe_capabilities(config)["fixed_choices"]:
        click.echo(f"- {choice}")
    for definition in input_contract(config):
        if not definition["editable"]:
            continue
        if definition.get("visible_when") and any(
            inputs.get(name) != expected for name, expected in definition["visible_when"].items()
        ):
            continue
        if definition["sensitive"]:
            references[definition["name"]] = definition["environment_variable"]
            click.echo(
                f"{definition['label']}: supply {definition['environment_variable']} externally before planning."
            )
            continue
        if definition["name"] == "private_ip_address":
            subnet = vm_subnet(config.provider, inputs["network_cidr"], config.is_public)
            first, excluded_last = (2, 2) if config.provider == "gcp" else (4, 1)
            click.echo(
                f"Usable private addresses: {subnet[first]} through {subnet[subnet.num_addresses - excluded_last - 1]} in {subnet}. Address availability is not checked."
            )

        def valid(text, definition=definition):
            try:
                value = int(text) if definition["kind"] == "integer" else text
                validate_answer(definition, value)
                if definition["name"] in {"boot_disk_iops", "data_disk_iops"}:
                    prefix = definition["name"].removesuffix("_iops")
                    if value > inputs[f"{prefix}_size_gb"] * 500:
                        return "Use no more than 500 IOPS per GiB of the selected gp3 disk size."
                if definition["name"] in {"boot_disk_throughput", "data_disk_throughput"}:
                    prefix = definition["name"].removesuffix("_throughput")
                    if value * 4 > inputs[f"{prefix}_iops"]:
                        return (
                            "Use throughput no greater than one quarter of the selected gp3 IOPS."
                        )
                if (
                    definition["name"] == "private_ip_address"
                    and value
                    and not usable_vm_address(
                        config.provider, inputs["network_cidr"], config.is_public, value
                    )
                ):
                    return (
                        "Choose a usable address in the displayed subnet range, or leave it blank."
                    )
                return True
            except ProjectInputError as error:
                return str(error)
            except (ValueError, TypeError):
                return "Enter a valid value for this field; review its description and supported range."

        click.echo(definition["description"])
        if definition["kind"] == "integer":
            click.echo(f"Whole number: {definition['minimum']}–{definition['maximum']}.")
        if definition["kind"] == "boolean":
            answer = ask(
                questionary.confirm(definition["label"] + "?", default=definition["default"])
            )
        elif definition["choices"]:
            answer = ask(
                questionary.select(
                    definition["label"] + ":",
                    choices=definition["choices"],
                    default=definition["default"],
                )
            )
        else:
            answer = ask(
                questionary.text(
                    definition["label"] + ":",
                    default=str(definition["default"]) if definition["default"] is not None else "",
                    multiline=definition["kind"] == "multiline",
                    validate=valid,
                )
            )
        inputs[definition["name"]] = int(answer) if definition["kind"] == "integer" else answer
    return ProjectSpecification(recipe=config, inputs=inputs, secret_references=references)


@main.command("catalog")
@click.option("--json-output", is_flag=True, help="Print capability metadata as JSON.")
def catalog_command(json_output: bool):
    """List supported recipes and their fixed choices and limitations."""
    recipes = recipe_catalog()
    if json_output:
        click.echo(json.dumps({"recipes": recipes}, indent=2))
        return
    for recipe in recipes:
        click.secho(f"{recipe['id']} — {recipe['name']}", fg="cyan")
        for choice in recipe["fixed_choices"]:
            click.echo(f"  {choice}")
        click.echo("  Unsupported: " + ", ".join(recipe["unsupported"]))
    click.echo("Generation is offline. Account capabilities and deployment remain unverified.")


@main.command()
@click.option(
    "--dir",
    "target_dir",
    type=click.Path(file_okay=False, path_type=Path),
    default=None,
    help="Directory for new Terraform files; defaults to ./<project-name>.",
)
def wizard(target_dir: Path | None):
    """Create infrastructure files with a guided questionnaire."""
    click.secho("TerraForma-IaC infrastructure wizard", fg="cyan", bold=True)
    if target_dir is not None:
        try:
            project_destination(target_dir)
        except (ValueError, OSError):
            raise click.ClickException(
                "Choose a fresh, writable project directory without existing Terraform or generated artifacts."
            ) from None
    provider = ask(questionary.select("Which cloud provider?", choices=["aws", "azure", "gcp"]))
    name = ask(
        questionary.text(
            "Project name (3–20 lowercase letters, digits, or hyphens):",
            validate=lambda text: (
                bool(re.fullmatch(r"[a-z][a-z0-9-]{1,18}[a-z0-9]", text))
                or "Start with a letter, end with a letter or digit, and use 3–20 characters."
            ),
        )
    )
    architecture = ask(
        questionary.select(
            "What would you like to create?",
            choices=[
                questionary.Choice(
                    "A Linux virtual machine with restricted SSH", value="virtual_machine"
                ),
                questionary.Choice(
                    "A Windows Server 2022 VM with restricted RDP",
                    value="windows_virtual_machine",
                ),
                questionary.Choice("A single web server", value="single_web_server"),
                questionary.Choice(
                    "A web VM tier behind a load balancer", value="load_balanced_tier"
                ),
                questionary.Choice(
                    "A highly available PostgreSQL database", value="secure_database"
                ),
                questionary.Choice(
                    "A static website stored in object storage", value="static_site"
                ),
            ],
        )
    )
    public = ask(questionary.confirm("Allow access from the public internet?", default=False))
    encryption = ask(
        questionary.confirm(
            "Enable storage encryption (provider defaults still apply)?", default=True
        )
    )
    if provider == "azure":
        click.echo(
            "Azure encrypts storage by default. For compute, this option also enables encryption at host, which requires subscription support."
        )
    elif provider == "gcp" or architecture == "static_site":
        click.echo(
            "This cloud service enforces encryption at rest even when this option is disabled."
        )
    if architecture == "secure_database":
        click.echo(
            "Database passwords are required variables. Databases have backups and deletion protection."
        )
    elif architecture != "static_site":
        click.echo(
            "The template serves HTTP. Add TLS before using it for sensitive traffic. NAT gateways and load balancers can incur ongoing charges."
        )
    click.echo(
        "Generation creates files only. Review credentials, required variables, pricing, and a Terraform plan before deploying."
    )
    try:
        config = WizardConfig(
            provider=provider,
            project_name=name,
            architecture_type=architecture,
            is_public=public,
            enable_encryption=encryption,
        )
        specification = collect_recipe_inputs(config)
        project = compile_project(specification)
    except ProjectInputError as error:
        raise click.ClickException(str(error)) from None
    except (ValueError, TypeError, ValidationError):
        raise click.ClickException(
            "Project inputs are invalid or incompatible. Review the recipe's input contract; values are omitted from this error."
        ) from None
    try:
        artifacts = project_artifacts(project)
        artifacts["SHA256SUMS.txt"] = checksum_document(artifacts)
        directory = write_configuration(artifacts, target_dir or Path.cwd() / name)
    except (OSError, ValueError):
        raise click.ClickException(
            "Unable to write project files. Choose a fresh, writable project directory."
        ) from None
    click.secho(f"Created main.tf, variables.tf, and outputs.tf in {directory}", fg="green")
    click.echo(
        "Saved the non-secret project specification, generation receipt, and checksums alongside them."
    )
    click.echo(project["verification"])
    click.echo(f'Validate with: terraforma run --dir "{directory}"')


def warning_card(title: str, explanation: str, fix: str = "") -> None:
    click.secho("\n" + "=" * 72, fg="yellow")
    click.secho(title, fg="yellow", bold=True)
    clean = ValidationSandbox._clean(redact_sensitive_text(explanation))
    click.echo(textwrap.fill(clean, width=72) if "\n" not in clean else clean)
    if fix:
        click.secho("\nSuggested fix (review before editing):", fg="yellow", bold=True)
        click.echo(ValidationSandbox._clean(redact_sensitive_text(fix)))
    click.secho("=" * 72, fg="yellow")


def readable_error(raw_output: str) -> str:
    prefix, separator, body = raw_output.partition("\n")
    if not separator:
        return raw_output
    try:
        data = json.loads(body)
        diagnostics = data.get("diagnostics", data.get("issues", []))
        messages = []
        for diagnostic in diagnostics:
            location = diagnostic.get("range", {})
            filename = location.get("filename", "")
            line = location.get("start", {}).get("line")
            title = diagnostic.get("summary", diagnostic.get("message", "Validation issue"))
            detail = diagnostic.get("detail", "")
            label = f"{filename}:{line}: " if filename and line else ""
            messages.append(f"{label}{title}" + (f"\n{detail}" if detail else ""))
        return prefix + "\n" + "\n\n".join(messages) if messages else raw_output
    except (ValueError, TypeError, AttributeError):
        return raw_output


@main.command()
@click.option(
    "--dir",
    "target_dir",
    type=click.Path(exists=True, file_okay=False, readable=True, path_type=Path),
    default=".",
    show_default=True,
)
@click.option(
    "--ai/--no-ai",
    default=False,
    help="Explain failures through OpenAI when OPENAI_API_KEY is set; logs are redacted before transmission.",
)
@click.option(
    "--timeout",
    type=click.FloatRange(min=1, max=600),
    default=120,
    show_default=True,
    help="Maximum seconds per validation command.",
)
def run(target_dir: Path, ai: bool, timeout: float):
    """Validate a temporary copy using Terraform and TFLint; never apply."""
    click.echo(f"Validating {target_dir.resolve()}")
    try:
        results = ValidationSandbox(target_dir=target_dir, timeout=timeout).validate()
    except (OSError, ValueError, RuntimeError) as error:
        raise click.ClickException(str(error)) from error
    if results["is_valid"]:
        click.secho("Terraform validation and TFLint passed.", fg="green", bold=True)
        return
    for error in results["errors"]:
        warning_card(f"Validation failed: {error['tool']}", readable_error(error["raw_output"]))
    if ai:
        try:
            click.echo("Requesting an AI explanation of redacted validation logs...")
            suggestion = asyncio.run(AIDiagnosticsEngine().diagnose(results["logs"]))
            warning_card(
                "AI explanation", suggestion["friendly_explanation"], suggestion["recommended_fix"]
            )
        except DiagnosticsError as error:
            warning_card("AI explanation unavailable", str(error))
    raise click.exceptions.Exit(1)


@main.command("review-plan")
@click.option(
    "--file",
    "plan_file",
    required=True,
    type=click.Path(exists=True, dir_okay=False, path_type=Path),
)
@click.option(
    "--json-output", is_flag=True, help="Print the report as JSON without raw plan values."
)
def review_plan_command(plan_file: Path, json_output: bool):
    """Review a Terraform show -json export locally without executing infrastructure."""
    try:
        report = load_and_review(plan_file)
    except (OSError, ValueError, TypeError, RecursionError):
        raise click.ClickException(
            "Unable to review the file: use a readable, valid Terraform plan JSON export within the documented limits."
        ) from None
    if json_output:
        click.echo(json.dumps(report, indent=2))
    else:
        click.secho(f"Plan review: {report['status']}", fg="yellow", bold=True)
        click.echo(f"Policy {report['policy_version']} | JSON SHA256 {report['artifact_sha256']}")
        click.echo("Actions: " + json.dumps(report["actions"], sort_keys=True))
        for finding in report["findings"][:100]:
            click.echo(
                f"[{finding['severity']}] {finding['resource_id']} · {finding['code']}: {finding['message']}"
            )
        if len(report["findings"]) > 100:
            click.echo(
                "Further findings omitted from console output; use --json-output for the complete report."
            )
        click.echo(report["limitations"])
    if report["status"] == "blocked":
        raise click.exceptions.Exit(1)


@main.command("project-inputs")
@click.option("--spec", required=True, type=click.Path(exists=True, dir_okay=False, path_type=Path))
def project_inputs(spec: Path):
    """List every declared variable for a versioned project recipe."""
    try:
        specification = load_specification(spec)
        contract = input_contract(specification.recipe)
    except (OSError, ValueError, TypeError, RecursionError):
        raise click.ClickException("Unable to read a supported project specification.") from None
    click.echo(json.dumps(contract, indent=2))


@main.command("generate")
@click.option("--spec", required=True, type=click.Path(exists=True, dir_okay=False, path_type=Path))
@click.option(
    "--dir", "target_dir", required=True, type=click.Path(file_okay=False, path_type=Path)
)
def generate_specification(spec: Path, target_dir: Path):
    """Generate Terraform from a project specification with complete non-secret inputs."""
    try:
        specification = load_specification(spec)
        result = compile_project(specification)
    except ProjectInputError as error:
        raise click.ClickException(str(error)) from None
    except ValidationError:
        raise click.ClickException(
            "Project specification does not match the supported schema; input values are omitted from this error."
        ) from None
    except (OSError, ValueError, TypeError, RecursionError):
        raise click.ClickException(
            "Project inputs are incomplete or invalid. Run project-inputs to inspect the required fields; values are omitted from this error."
        ) from None
    try:
        artifacts = project_artifacts(result)
        artifacts["SHA256SUMS.txt"] = checksum_document(artifacts)
        directory = write_configuration(artifacts, target_dir)
    except (OSError, ValueError):
        raise click.ClickException(
            "Unable to write Terraform files. Choose a new writable project directory."
        ) from None
    click.echo(f"Created Terraform files in {directory}")
    for name in result["required_secret_environment_variables"]:
        click.echo(
            f"Supply {name} through your environment before planning; its value was not collected or saved."
        )
    click.echo(result["verification"])


@main.command("describe")
@click.option("--spec", required=True, type=click.Path(exists=True, dir_okay=False, path_type=Path))
@click.option("--json-output", is_flag=True, help="Print the configuration summary as JSON.")
def describe_project(spec: Path, json_output: bool):
    """Explain selected configuration answers and defaults without executing Terraform."""
    try:
        specification = load_specification(spec)
        result = compile_project(specification)
    except ProjectInputError as error:
        raise click.ClickException(str(error)) from None
    except (OSError, ValueError, TypeError, RecursionError):
        raise click.ClickException(
            "Unable to describe a supported, complete project specification; input values are omitted from this error."
        ) from None
    summary = {
        "target": result["target"],
        "choices": result["choice_summary"],
        "verification": result["verification"],
    }
    if json_output:
        click.echo(json.dumps(summary, indent=2))
        return
    click.echo(f"Configuration choices for {specification.recipe.project_name}")
    for choice in summary["choices"]:
        click.echo(f"{choice['label']}: {choice['value']} ({choice['source']})")
    click.echo(summary["verification"])


@main.command("verify-project")
@click.option(
    "--dir",
    "directory",
    required=True,
    type=click.Path(exists=True, file_okay=False, path_type=Path),
)
@click.option("--json-output", is_flag=True, help="Print the artifact comparison report as JSON.")
def verify_project_command(directory: Path, json_output: bool):
    """Compare generated files to an unsigned local generation receipt."""
    try:
        report = verify_project(directory)
    except (OSError, ValueError, TypeError, RecursionError):
        raise click.ClickException(
            "A supported, readable generation receipt is required; receipt values are omitted from this error."
        ) from None
    if json_output:
        click.echo(json.dumps(report, indent=2))
    else:
        for item in report["files"]:
            click.echo(f"{item['file']}: {item['status']}")
        click.echo(f"Questionnaire metadata: {report['specification_status']}")
        click.echo(report["limitations"])
    if report["status"] != "matches_receipt":
        raise click.exceptions.Exit(1)


@main.command()
@click.option("--port", type=click.IntRange(1024, 65535), default=8765, show_default=True)
@click.option("--open-browser", is_flag=True, help="Open the workspace in your default browser.")
def serve(port: int, open_browser: bool):
    """Start the lightweight web UI on this computer."""
    try:
        import uvicorn

        from terraforma.web import create_app
    except ImportError as error:
        raise click.ClickException(
            'Install the web UI with: python -m pip install -e ".[web]"'
        ) from error
    url = f"http://127.0.0.1:{port}"
    click.secho(f"TerraForma-IaC local workspace: {url}", fg="cyan", bold=True)
    click.echo("Press Ctrl+C to stop.")
    if open_browser:
        import threading

        timer = threading.Timer(1, webbrowser.open, args=[url])
        timer.daemon = True
        timer.start()
    uvicorn.run(
        create_app(),
        host="127.0.0.1",
        port=port,
        proxy_headers=False,
        access_log=False,
        log_level="warning",
    )


if __name__ == "__main__":
    main()
