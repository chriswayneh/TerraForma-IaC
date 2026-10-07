import asyncio
import io
import os
import secrets
import shutil
import zipfile
from pathlib import Path
from urllib.parse import urlsplit

from fastapi import FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import FileResponse, JSONResponse, Response
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, ConfigDict
from starlette.concurrency import run_in_threadpool
from starlette.middleware.trustedhost import TrustedHostMiddleware

from terraforma import __version__
from terraforma.ai_engine import AIDiagnosticsEngine, DiagnosticsError, redact_sensitive_text
from terraforma.artifacts import checksum_document, project_artifacts
from terraforma.catalog import recipe_capabilities, recipe_catalog
from terraforma.cli import readable_error
from terraforma.generator import TerraformGenerator, WizardConfig
from terraforma.guidance import infrastructure_guide
from terraforma.plan_review import MAX_PLAN_BYTES, review_bytes
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
    explain_with_ai: bool = False


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
    if config.architecture_type == "virtual_machine":
        notes.extend(
            [
                "SSH requires the selected administrator network and its authentication prerequisites. Private access needs a routed path; no VPN or bastion is created.",
                "The VM has no application startup script. Compute, disks, public addresses and outbound NAT can incur charges.",
            ]
        )
        if config.provider == "gcp":
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
    project["required_inputs"] = [
        item for item in project["required_inputs"] if item["name"] not in payload.inputs
    ]
    project["notes"].append(compiled["verification"])
    if payload.recipe.architecture_type == "virtual_machine" and payload.recipe.provider in {
        "aws",
        "gcp",
    }:
        protection = payload.inputs.get("protect_vm", True)
        project["notes"].append(
            "VM deletion protection is "
            + ("enabled" if protection else "disabled")
            + ". To intentionally delete or replace a protected VM, first disable protection and apply that configuration change in your Terraform workflow. Protection is not a backup or protection for every connected resource."
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
        RequestSizeLimitMiddleware, path_limits={"/api/plans/review": MAX_PLAN_BYTES}
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
            project_artifacts(project) if "specification" in project else dict(project["files"])
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
                status_code=409, detail="Another validation is running. Try again when it finishes."
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
