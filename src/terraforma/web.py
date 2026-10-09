import asyncio
import io
import json
import os
import re
import secrets
import shutil
import zipfile
from pathlib import Path
from typing import Literal
from urllib.parse import urlsplit

from fastapi import FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import FileResponse, JSONResponse, Response
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, ConfigDict, StrictBool, ValidationError
from starlette.concurrency import run_in_threadpool
from starlette.middleware.trustedhost import TrustedHostMiddleware

from terraforma import __version__
from terraforma.ai_engine import AIDiagnosticsEngine, DiagnosticsError, redact_sensitive_text
from terraforma.artifacts import PROJECT_GITIGNORE, checksum_document, project_artifacts
from terraforma.backend import (
    MAX_BACKEND_BYTES,
    backend_error_detail,
    backend_input_contract,
    parse_backend,
    review_backend,
)
from terraforma.catalog import recipe_capabilities, recipe_catalog
from terraforma.cli import readable_error
from terraforma.generator import TerraformGenerator, WizardConfig
from terraforma.guidance import infrastructure_guide
from terraforma.outbound import outbound_guidance
from terraforma.plan_review import MAX_PLAN_BYTES, review_bytes
from terraforma.preflight import target_preflight
from terraforma.project import (
    ProjectInputError,
    ProjectSpecification,
    compile_project,
    input_contract,
    parse_specification,
)
from terraforma.request_limits import RequestSizeLimitMiddleware
from terraforma.sandbox import ValidationSandbox


class ValidationRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    config: WizardConfig | ProjectSpecification
    explain_with_ai: StrictBool = False


class PreflightRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    specification: ProjectSpecification
    verify_target: StrictBool = False
    verify_machine: StrictBool = False
    verify_image: StrictBool = False


class BackendChoice(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    backend: Literal["s3", "azurerm", "gcs"]


def generate_project(config: WizardConfig) -> dict:
    generator = TerraformGenerator(config)
    files = generator.generate()
    inputs = [
        {
            "name": variable.labels[0],
            "description": variable.attributes["description"],
            "sensitive": variable.attributes.get("sensitive", False),
        }
        for variable in generator.variables
        if "default" not in variable.attributes
    ]
    notes = ["Review the Terraform plan and your cloud account before deployment."]
    if config.architecture_type in {"virtual_machine", "windows_virtual_machine"}:
        notes.extend(
            [
                "RDP uses the selected administrator network or IAP tunnel with separate Windows account/password setup through Google Cloud after provisioning. Terraform does not create that account. Direct private access needs routing; IAP needs tunnel IAM and guest authentication. Review Windows activation prerequisites."
                if config.architecture_type == "windows_virtual_machine"
                and config.provider == "gcp"
                else "RDP requires the selected administrator network and externally supplied TF_VAR_admin_password. AzureRM retains the password in Terraform state and saved plans; protect their storage/access before use. This generator does not configure a protected backend. Private access needs a routed path."
                if config.architecture_type == "windows_virtual_machine"
                and config.provider == "azure"
                else "RDP requires the selected administrator network and an Administrator password recovered separately with your RSA private key through EC2. TerraForma does not collect or decrypt it. Private access needs a routed path."
                if config.architecture_type == "windows_virtual_machine"
                else "SSH requires the selected administrator network and its authentication prerequisites. Private access needs a routed path; no VPN or bastion is created.",
                "The VM has no application startup script. Compute, disks, public addresses and outbound NAT can incur charges.",
            ]
        )
        if config.provider == "gcp" and config.architecture_type == "virtual_machine":
            notes.append(
                "Google OS Login needs an appropriate IAM role. Organization policy and login prerequisites remain unverified offline."
            )
    if config.architecture_type in {"single_web_server", "load_balanced_tier"}:
        notes.extend(
            [
                "The web server runs nginx and serves HTTP. Add TLS for sensitive traffic.",
                "Compute and outbound NAT can incur ongoing charges even when the site is idle.",
            ]
        )
    if config.architecture_type == "secure_database":
        notes.append(
            "This managed PostgreSQL database includes a standby, backups, and deletion protection. It can incur ongoing charges."
        )
    if config.architecture_type == "static_site" and not config.is_public:
        notes.append(
            "Private mode creates authenticated website objects; it does not expose a public website."
        )
    if config.provider == "azure":
        notes.append(
            "Azure encrypts storage by default. Compute encryption at host requires a supported subscription and VM size."
        )
    if config.provider == "gcp" or config.architecture_type == "static_site":
        notes.append("This service always encrypts stored data using provider-managed keys.")
    return {
        "files": files,
        "required_inputs": inputs,
        "notes": notes,
        "guide": infrastructure_guide(config),
        "capabilities": recipe_capabilities(config),
    }


def configured_project(payload: WizardConfig | ProjectSpecification) -> dict:
    if isinstance(payload, WizardConfig):
        return generate_project(payload)
    try:
        compiled = compile_project(payload)
    except ProjectInputError:
        raise
    except (ValueError, TypeError):
        raise HTTPException(
            status_code=422,
            detail="Project inputs are incomplete or invalid. Check the input contract; secret values must be supplied externally.",
        ) from None
    project = generate_project(payload.recipe)
    project["files"] = compiled["files"]
    project["specification"] = compiled["specification"]
    project["target"] = compiled["target"]
    project["receipt"] = compiled["receipt"]
    project["choice_summary"] = compiled["choice_summary"]
    iap_access = (
        payload.recipe.provider == "gcp"
        and payload.recipe.architecture_type in {"virtual_machine", "windows_virtual_machine"}
        and payload.inputs.get("admin_access_method") == "iap_tunnel"
    )
    project["required_inputs"] = [
        item
        for item in project["required_inputs"]
        if item["name"] not in payload.inputs
        and not (iap_access and item["name"] == "allowed_cidr")
    ]
    if iap_access and not payload.inputs.get("use_existing_network", False):
        project["guide"]["route"][0] = "Authorized Google IAP tunnel"
        project["guide"]["components"][-1]["explanation"] = (
            "The administrator firewall accepts one TCP port from Google's IAP IPv4 proxy range. "
            "Review tunnel IAM, guest authentication and other firewall rules separately. "
            "TerraForma grants no access and opens no connection."
        )
        project["notes"].append(
            "IAP tunnel access requires separate IAM and guest authentication. "
            "The targeted proxy firewall rule requires manual plan review; no access is approved."
        )
    project["notes"].append(compiled["verification"])
    if payload.inputs.get("use_custom_image", False):
        for component in project["guide"]["components"]:
            if component["name"] in {
                "Amazon EC2",
                "Azure virtual machines",
                "Google Compute Engine",
            }:
                component["explanation"] = (
                    "One VM uses the declared existing custom image, selected machine size and boot disk. Image provenance, guest agents, OS family, licensing, boot compatibility and administrator access remain unverified."
                )
    if payload.inputs.get("enable_initialization", False):
        project["notes"] = [
            note.replace("The VM has no application startup script. ", "")
            for note in project["notes"]
        ]
        for component in project["guide"]["components"]:
            component["explanation"] = (
                component["explanation"]
                .replace("Application initialization is optional; ", "")
                .replace(
                    "Application initialization is left for your workload setup.",
                    "A reviewed initialization script is included; guest execution remains unverified.",
                )
            )
        project["guide"]["components"].append(
            {
                "name": "Reviewed initialization script",
                "explanation": "The supplied script is included for elevated guest execution on a future deployment. Generation never runs it locally. Guest-agent support, script safety, dependencies and successful execution remain unverified. Review repeat execution and replacement behavior before deployment.",
            }
        )
        project["notes"].append(
            "Initialization content is stored in exports and generated configuration, and can reach Terraform state and guest metadata/extension settings. Base64 is not encryption. Keep secrets external and review the exact script before deployment."
        )
    if payload.inputs.get("use_existing_network", False):
        azure_attachment = payload.recipe.provider == "azure"
        aws_attachment = payload.recipe.provider == "aws"
        project["guide"]["components"][0] = {
            "name": "Existing Azure subnet"
            if azure_attachment
            else "Existing AWS subnet"
            if aws_attachment
            else "Existing Google Cloud subnet",
            "explanation": "The new VM NIC attaches to the declared existing subnet with an existing subnet NSG. No VNet, subnet, NSG, NSG association or NAT infrastructure is managed in this mode. Existing policies, routing and egress remain independently managed and unverified."
            if azure_attachment
            else "The VM attaches to the existing subnet and one reviewed security group. No VPC, subnet, security group, route, internet gateway or NAT is managed in this mode. Existing rules, network ACLs and egress remain independently managed and unverified."
            if aws_attachment
            else "The VM attaches to the declared existing subnet. No VPC, subnet, firewall, route, router, NAT or Compute API enablement is managed in this mode. Existing policies, routing and egress remain independently managed and unverified.",
        }
        for component in project["guide"]["components"]:
            if component["name"] == "Administrator access":
                component["explanation"] = (
                    "Administrator access depends on existing NSGs, routing and guest authentication. The supplied administrator CIDR is a declaration only; this mode creates no access rule, NSG association, role grant or connection. Windows activation must also be provided by the existing network."
                    if azure_attachment
                    else "Administrator access depends on the existing security group, network ACLs, routing and guest authentication. The supplied administrator CIDR is a declaration only; this mode creates no access rule, IAM grant or connection. Review Windows activation connectivity separately."
                    if aws_attachment
                    else "Administrator access depends on existing firewall policies, routing and guest authentication. The selected CIDR or IAP path is a declaration only; this mode creates no access rule, target network tag, IAM grant or connection. Windows activation must also be provided by the existing network."
                )
        project["guide"]["route"][1] = "Existing access rules (separate review)"
        project["guide"]["route"][0] = (
            "Existing IAP setup (unverified)"
            if iap_access
            else "Existing administrator routing (unverified)"
        )
        project["notes"].append(
            "Existing Azure subnet mode leaves network infrastructure separately managed. Metadata guards check subscription, region, one declared IPv4 prefix and a subnet NSG; they do not check delegation, effective rules, available addresses, egress or attachment permissions. Review administrator access and Windows activation separately."
            if azure_attachment
            else "Existing AWS subnet mode leaves network infrastructure separately managed. Metadata guards check account ownership, subnet CIDR and zone, IPv4-only/non-Outposts status and security-group VPC/account compatibility. Effective rules, network ACLs, egress, attachment permissions and IP availability remain unverified."
            if aws_attachment
            else "Existing subnet mode leaves network infrastructure and Compute API enablement separately managed. Review inherited rules, egress, administrator access and Windows activation. No existing network tag is attached automatically; generation does not verify effective access."
        )
    if payload.recipe.architecture_type in {
        "virtual_machine",
        "windows_virtual_machine",
    } and payload.inputs.get("enable_workload_identity", False):
        project["guide"]["components"].append(
            {
                "name": "Workload identity",
                "explanation": {
                    "aws": "The VM uses the supplied existing IAM instance profile. Review its role permissions, EC2 trust and pass-role authorization; the recipe creates no IAM role or policy grant.",
                    "azure": "The VM attaches the supplied existing user-assigned managed identity. Its lifecycle remains independent of the VM; effective privileges and attachment authorization require separate review. No identity or role assignment is created."
                    if payload.inputs.get("workload_identity_type") == "existing_user_assigned"
                    else "A system-assigned managed identity is created with the VM. Its principal ID is exported, but no role assignments are granted; deletion of the VM removes this identity.",
                    "gcp": "The VM uses the supplied user-managed service account and cloud-platform OAuth scope. Actual access depends on existing IAM roles; this recipe creates no key or IAM grant. Service account changes require a stopped VM, and automatic stopping is disabled.",
                }[payload.recipe.provider],
            }
        )
        project["notes"].append(
            "Review workload identity permissions and attachment authorization separately. An identity reference is not a credential or a verification of least privilege. No role grants or credential keys are created by this recipe."
        )
    if payload.recipe.architecture_type in {
        "virtual_machine",
        "windows_virtual_machine",
    } and payload.inputs.get("enable_data_disk", False):
        project["guide"]["components"].append(
            {
                "name": {
                    "aws": "Amazon EBS data disk",
                    "azure": "Azure managed data disk",
                    "gcp": "Google persistent data disk",
                }[payload.recipe.provider],
                "explanation": "One empty disk is attached for your workload data. Identify the actual device and arrange formatting, mounting, backups and recovery separately; attachment alone does not make a mounted filesystem.",
            }
        )
        project["notes"].append(
            "One new empty data disk is attached and adds storage cost. Identify the actual device before formatting or mounting it. This project does not configure backups, recovery or retention; Terraform teardown can delete the disk."
        )
        if payload.recipe.provider == "aws":
            project["notes"].append(
                "AWS data disk attachment changes may stop the VM before detaching. Forced detach is disabled. Identify the disk in Windows Disk Management before initializing it."
                if payload.recipe.architecture_type == "windows_virtual_machine"
                else "AWS data disk attachment changes may stop the VM before detaching. Forced detach is disabled. Nitro instances can expose a different Linux device name than /dev/sdf."
            )
    if payload.recipe.architecture_type in {
        "virtual_machine",
        "windows_virtual_machine",
    } and payload.recipe.provider in {
        "aws",
        "gcp",
    }:
        protection = payload.inputs.get("protect_vm", True)
        if payload.inputs.get("delete_boot_disk_with_vm", True) is False:
            project["notes"].append(
                "Boot disk retention is requested. Storage charges continue; recovery, "
                "reattachment and cleanup remain separate. This does not retain data disks, "
                "keys or other project resources. "
                + (
                    "Preserve the AWS KMS key separately before teardown; key deletion can make retained encrypted disks unreadable."
                    if payload.recipe.provider == "aws" and payload.recipe.enable_encryption
                    else "A retained GCP boot disk can conflict with replacement disk naming; review recovery and naming before replacement."
                    if payload.recipe.provider == "gcp"
                    else "Retention does not create backups or verify recovery."
                )
            )
        project["notes"].append(
            "VM deletion protection is "
            + ("enabled" if protection else "disabled")
            + ". To intentionally delete or replace a protected VM, first disable protection and apply that configuration change in your Terraform workflow. Protection is not a backup or protection for every connected resource."
        )
    if (
        payload.recipe.provider == "azure"
        and payload.recipe.architecture_type == "windows_virtual_machine"
    ):
        project["notes"].append(
            "Azure Windows uses the refreshed windowsserver2022 offer, excluding deprecated "
            ".NET 6 packages. Regenerating an older WindowsServer-offer project can replace "
            "the VM and delete boot data. Verify the new offer's image version, application "
            "dependencies and backups before planning; old pins are not translated."
        )
    if payload.recipe.provider == "gcp" and payload.inputs.get("use_customer_managed_disk_key"):
        project["notes"].append(
            "Disk encryption references an existing Cloud KMS key. Confirm its compatible location, "
            "enabled state and Compute Engine service-agent access separately. No key or IAM grant "
            "is managed here. Disk retention does not preserve key availability; revocation can "
            "prevent boot, attachment and recovery. Changing encryption can replace disks and delete data."
        )
    if (
        payload.recipe.architecture_type == "windows_virtual_machine"
        and payload.inputs.get("os_image") == "windows-server-2022-core"
    ):
        project["notes"].append(
            "Windows Server Core omits the standard desktop. Verify application and "
            "administration-tool compatibility. Switching between Core and desktop images "
            "requires VM replacement; review backups and boot-disk/key lifecycle first."
        )
    if payload.recipe.architecture_type in {"virtual_machine", "windows_virtual_machine"}:
        explanation = outbound_guidance(payload.inputs)
        project["notes"].append(explanation)
        project["guide"]["components"].append(
            {"name": "Outbound network profile", "explanation": explanation}
        )
    return project


def create_app() -> FastAPI:
    app = FastAPI(
        title="TerraForma-IaC local workspace",
        version=__version__,
        docs_url=None,
        redoc_url=None,
        openapi_url=None,
    )
    app.add_middleware(TrustedHostMiddleware, allowed_hosts=["127.0.0.1", "localhost", "[::1]"])
    app.add_middleware(
        RequestSizeLimitMiddleware,
        path_limits={
            "/api/plans/review": MAX_PLAN_BYTES,
            "/api/backends/check": MAX_BACKEND_BYTES,
            "/api/backends/download": MAX_BACKEND_BYTES,
            "/api/backends/import": MAX_BACKEND_BYTES,
        },
    )
    token = secrets.token_urlsafe(32)
    validation_lock = asyncio.Lock()
    plan_review_lock = asyncio.Lock()
    static = Path(__file__).parent / "static"

    @app.exception_handler(RequestValidationError)
    async def invalid_request(request: Request, error: RequestValidationError):
        return JSONResponse(
            status_code=422,
            content={
                "detail": "Request does not match the supported schema. Check the selected recipe and input contract; input values are omitted from this error."
            },
        )

    @app.exception_handler(ProjectInputError)
    async def invalid_project_input(request: Request, error: ProjectInputError):
        return JSONResponse(status_code=422, content={"detail": str(error), "field": error.field})

    @app.post("/api/input-contract")
    async def recipe_inputs(config: WizardConfig):
        return {
            "schema_version": 1,
            "template_version": ProjectSpecification.model_fields["template_version"].default,
            "inputs": input_contract(config),
            "capabilities": recipe_capabilities(config),
        }

    @app.get("/api/catalog")
    async def catalog():
        return {"recipes": recipe_catalog()}

    @app.post("/api/backends/input-contract")
    async def backend_inputs(payload: BackendChoice):
        return {"schema_version": 1, "inputs": backend_input_contract(payload.backend)}

    @app.post("/api/backends/import")
    async def backend_import(request: Request):
        try:
            intent = parse_backend(await request.body())
        except (ValueError, TypeError, RecursionError):
            raise HTTPException(
                status_code=422,
                detail="Backend input file is invalid or unsupported. Choose a non-secret backend intent; values are omitted.",
            ) from None
        return {
            "intent": intent.model_dump(),
            "inputs": backend_input_contract(intent.backend),
            "backend_configured": False,
            "identity_verified": False,
            "approval_granted": False,
        }

    @app.post("/api/backends/check")
    async def backend_check(request: Request):
        try:
            return review_backend(await request.body())
        except ValidationError as error:
            return JSONResponse(status_code=422, content=backend_error_detail(error))
        except (ValueError, TypeError, RecursionError):
            raise HTTPException(
                status_code=422,
                detail="Backend inputs are invalid or unsupported. Use non-secret references in the documented format; values are omitted.",
            ) from None

    @app.post("/api/backends/download")
    async def backend_download(request: Request):
        try:
            intent = parse_backend(await request.body())
        except ValidationError as error:
            return JSONResponse(status_code=422, content=backend_error_detail(error))
        except (ValueError, TypeError, RecursionError):
            raise HTTPException(
                status_code=422,
                detail="Backend inputs are invalid or unsupported; values are omitted.",
            ) from None
        return Response(
            json.dumps(intent.model_dump(), indent=2) + "\n",
            media_type="application/json",
            headers={"Content-Disposition": 'attachment; filename="terraforma.backend.json"'},
        )

    @app.post("/api/projects/import")
    async def project_import(request: Request):
        try:
            specification = parse_specification(await request.body())
            return configured_project(specification)
        except ProjectInputError:
            raise
        except (ValueError, TypeError, RecursionError):
            raise HTTPException(
                status_code=422,
                detail="Project file is invalid, incomplete, or uses an unsupported version. Input values are omitted from this error.",
            ) from None

    @app.post("/api/plans/review")
    async def plan_review(request: Request):
        if plan_review_lock.locked():
            raise HTTPException(
                status_code=409,
                detail="Another plan review is running. Try again when it finishes.",
            )
        async with plan_review_lock:
            raw = await request.body()
            try:
                return await run_in_threadpool(review_bytes, raw)
            except (ValueError, TypeError, RecursionError):
                raise HTTPException(
                    status_code=422,
                    detail="This file is not a supported Terraform plan JSON export. Plan values are omitted from this error.",
                ) from None

    @app.post("/api/projects/preflight")
    async def project_preflight(payload: PreflightRequest):
        if validation_lock.locked():
            raise HTTPException(
                status_code=409,
                detail="Another local tool check is running. Try again when it finishes.",
            )
        async with validation_lock:
            try:
                return await run_in_threadpool(
                    target_preflight,
                    payload.specification,
                    verify_target=payload.verify_target,
                    verify_machine=payload.verify_machine,
                    verify_image=payload.verify_image,
                    timeout=30,
                )
            except ProjectInputError:
                raise
            except (OSError, ValueError, TypeError, RecursionError):
                raise HTTPException(
                    status_code=422,
                    detail="Unable to check this project specification; input and command values are omitted.",
                ) from None

    @app.post("/api/projects/compile")
    async def project_compile(specification: ProjectSpecification):
        try:
            return compile_project(specification)
        except ProjectInputError:
            raise
        except (ValueError, TypeError):
            raise HTTPException(
                status_code=422,
                detail="Project inputs are incomplete or invalid; inspect the input contract. Secret values must be supplied externally.",
            ) from None

    @app.middleware("http")
    async def local_request_guard(request: Request, call_next):
        if request.method not in {"GET", "HEAD"}:
            origin = request.headers.get("origin")
            if origin:
                try:
                    parsed = urlsplit(origin)
                    same_origin = (
                        parsed.netloc == request.url.netloc and parsed.scheme == request.url.scheme
                    )
                except ValueError:
                    same_origin = False
                if not same_origin:
                    return Response("Cross-origin requests are not allowed.", status_code=403)
            if not secrets.compare_digest(
                request.headers.get("x-terraforma-token", "").encode("utf-8"), token.encode("ascii")
            ):
                return Response("Open the local app to start a new session.", status_code=403)
        response = await call_next(request)
        response.headers.update(
            {
                "Content-Security-Policy": "default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' data:; connect-src 'self'; object-src 'none'; base-uri 'none'; frame-ancestors 'none'; form-action 'self'",
                "X-Content-Type-Options": "nosniff",
                "Referrer-Policy": "no-referrer",
                "Cache-Control": "no-store",
            }
        )
        return response

    @app.get("/")
    async def index():
        return FileResponse(static / "index.html")

    @app.get("/api/session")
    async def session():
        return {
            "token": token,
            "version": __version__,
            "tools": {name: bool(shutil.which(name)) for name in ("terraform", "tflint")},
            "ai_available": bool(os.environ.get("OPENAI_API_KEY", "").strip()),
        }

    @app.post("/api/generate")
    async def generate(config: WizardConfig | ProjectSpecification):
        return configured_project(config)

    @app.post("/api/download")
    async def download(config: WizardConfig | ProjectSpecification):
        project = configured_project(config)
        recipe = config.recipe if isinstance(config, ProjectSpecification) else config
        stream = io.BytesIO()
        instructions = [
            f"# {recipe.project_name}",
            "",
            "Generated with TerraForma-IaC.",
            "",
            "## Required inputs",
            "",
        ]
        instructions.extend(
            f"- {item['name']}: {item['description']}" for item in project["required_inputs"]
        )
        if not project["required_inputs"]:
            instructions.append(
                "No additional required Terraform variables. Configure your cloud credentials separately."
            )
        if "target" in project:
            instructions.extend(
                [
                    "",
                    "## Target account",
                    "",
                    f"{project['target']['provider']}: {project['target']['account_reference']}. Environment label: {project['target']['environment']}. Identity remains unverified offline.",
                ]
            )
        instructions.extend(["", "## What the configuration creates", ""])
        if project.get("choice_summary"):
            instructions.extend(["Your configuration choices:", ""])
            for choice in project["choice_summary"]:
                label = choice["label"].replace("|", "\\|")
                value = re.sub(r"([\\`*_{}\[\]()#+.!|<>~-])", r"\\\1", choice["value"])
                instructions.append(f"- {label}: {value} ({choice['source']}).")
            instructions.append("")
        for component in project["guide"]["components"]:
            instructions.append(f"- {component['name']}: {component['explanation']}")
        instructions.extend(["", "## Recipe defaults and limits", ""])
        instructions.extend(f"- {choice}" for choice in project["capabilities"]["fixed_choices"])
        instructions.append(
            "Unsupported: " + ", ".join(project["capabilities"]["unsupported"]) + "."
        )
        instructions.extend(
            [
                "",
                "## Review before deploying",
                "",
                *project["notes"],
                "",
                "Run `terraform init` and `terraform plan` after reviewing the configuration and supplying required values. Secure state storage; sensitive variables can still appear in state.",
                "The included .gitignore excludes common state, variable, plan and credential filenames. Keep .terraform.lock.hcl in version control for reproducible provider selections. Ignore rules do not protect already tracked files, force-added files or custom artifact names; review git status before committing.",
            ]
        )
        if "receipt" in project:
            instructions.extend(
                [
                    "",
                    "## Compare exported files",
                    "",
                    "Run `terraforma verify-project --dir .` with the matching development CLI to compare Terraform files and the saved questionnaire to the unsigned generation receipt. Matching hashes do not authenticate the receipt or authorize deployment.",
                ]
            )
        artifacts = (
            project_artifacts(project)
            if "specification" in project
            else {**project["files"], ".gitignore": PROJECT_GITIGNORE}
        )
        artifacts["README.md"] = "\n".join(instructions) + "\n"
        artifacts["SHA256SUMS.txt"] = checksum_document(artifacts)
        with zipfile.ZipFile(stream, "w", compression=zipfile.ZIP_DEFLATED) as archive:
            for name, text in artifacts.items():
                archive.writestr(name, text)
        return Response(
            stream.getvalue(),
            media_type="application/zip",
            headers={"Content-Disposition": f'attachment; filename="{recipe.project_name}.zip"'},
        )

    @app.post("/api/validate")
    async def validate(payload: ValidationRequest):
        if validation_lock.locked():
            raise HTTPException(
                status_code=409,
                detail="Another local tool check is running. Try again when it finishes.",
            )
        async with validation_lock:
            project = configured_project(payload.config)
            try:
                result = await run_in_threadpool(
                    ValidationSandbox(generated_files=project["files"]).validate
                )
            except (OSError, ValueError, RuntimeError) as error:
                raise HTTPException(
                    status_code=500,
                    detail="The validation workspace could not be prepared. Check local disk space and tool permissions.",
                ) from error
            errors = [
                {
                    "tool": item["tool"],
                    "message": redact_sensitive_text(
                        ValidationSandbox._clean(readable_error(item["raw_output"]))
                    ),
                }
                for item in result["errors"]
            ]
            response = {
                "is_valid": result["is_valid"],
                "errors": errors,
                "suggestion": None,
                "ai_error": None,
            }
            if not result["is_valid"] and payload.explain_with_ai:
                try:
                    response["suggestion"] = await AIDiagnosticsEngine().diagnose(result["logs"])
                except DiagnosticsError as error:
                    response["ai_error"] = str(error)
            return response

    app.mount("/static", StaticFiles(directory=static), name="static")
    return app
