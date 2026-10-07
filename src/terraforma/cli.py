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
from terraforma.generator import TerraformGenerator, WizardConfig, write_configuration
from terraforma.plan_review import load_and_review
from terraforma.project import compile_project, input_contract, load_specification
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
                questionary.Choice("A single web server", value="single_web_server"),
                questionary.Choice(
                    "Two web servers behind a load balancer", value="load_balanced_tier"
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
        directory = write_configuration(
            TerraformGenerator(config).generate(), target_dir or Path.cwd() / name
        )
    except (OSError, ValueError, ValidationError) as error:
        raise click.ClickException(str(error)) from error
    click.secho(f"Created main.tf, variables.tf, and outputs.tf in {directory}", fg="green")
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
    except ValidationError:
        raise click.ClickException(
            "Project specification does not match the supported schema; input values are omitted from this error."
        ) from None
    except (OSError, ValueError, TypeError, RecursionError):
        raise click.ClickException(
            "Project inputs are incomplete or invalid. Run project-inputs to inspect the required fields; values are omitted from this error."
        ) from None
    try:
        directory = write_configuration(result["files"], target_dir)
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
