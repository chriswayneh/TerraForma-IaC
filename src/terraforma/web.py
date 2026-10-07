import asyncio
import io
import os
import secrets
import shutil
import zipfile
from pathlib import Path
from urllib.parse import urlsplit

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, Response
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, ConfigDict
from starlette.concurrency import run_in_threadpool
from starlette.middleware.trustedhost import TrustedHostMiddleware

from terraforma import __version__
from terraforma.ai_engine import AIDiagnosticsEngine, DiagnosticsError, redact_sensitive_text
from terraforma.cli import readable_error
from terraforma.generator import TerraformGenerator, WizardConfig
from terraforma.guidance import infrastructure_guide
from terraforma.request_limits import RequestSizeLimitMiddleware
from terraforma.sandbox import ValidationSandbox


class ValidationRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    config: WizardConfig
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
    }


def create_app() -> FastAPI:
    app = FastAPI(
        title="TerraForma-IaC local workspace",
        version=__version__,
        docs_url=None,
        redoc_url=None,
        openapi_url=None,
    )
    app.add_middleware(TrustedHostMiddleware, allowed_hosts=["127.0.0.1", "localhost", "[::1]"])
    app.add_middleware(RequestSizeLimitMiddleware)
    token = secrets.token_urlsafe(32)
    validation_lock = asyncio.Lock()
    static = Path(__file__).parent / "static"

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
    async def generate(config: WizardConfig):
        return generate_project(config)

    @app.post("/api/download")
    async def download(config: WizardConfig):
        project = generate_project(config)
        stream = io.BytesIO()
        instructions = [
            f"# {config.project_name}",
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
        instructions.extend(["", "## What the configuration creates", ""])
        for component in project["guide"]["components"]:
            instructions.append(f"- {component['name']}: {component['explanation']}")
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
        with zipfile.ZipFile(stream, "w", compression=zipfile.ZIP_DEFLATED) as archive:
            for name, text in project["files"].items():
                archive.writestr(name, text)
            archive.writestr("README.md", "\n".join(instructions) + "\n")
        return Response(
            stream.getvalue(),
            media_type="application/zip",
            headers={"Content-Disposition": f'attachment; filename="{config.project_name}.zip"'},
        )

    @app.post("/api/validate")
    async def validate(payload: ValidationRequest):
        if validation_lock.locked():
            raise HTTPException(
                status_code=409, detail="Another validation is running. Try again when it finishes."
            )
        async with validation_lock:
            project = generate_project(payload.config)
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
                    "message": redact_sensitive_text(readable_error(item["raw_output"])),
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
