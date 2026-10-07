import shutil
import sys
from importlib.metadata import PackageNotFoundError, distribution

BASE_PACKAGES = ("click", "questionary", "httpx", "pydantic")
WEB_PACKAGES = ("fastapi", "uvicorn")


def local_readiness() -> dict:
    packages = {}
    for name in (*BASE_PACKAGES, *WEB_PACKAGES):
        try:
            distribution(name)
        except PackageNotFoundError:
            packages[name] = False
        else:
            packages[name] = True
    tools = {name: shutil.which(name) is not None for name in ("terraform", "tflint")}
    python_supported = sys.version_info >= (3, 11)
    base_ready = python_supported and all(packages[name] for name in BASE_PACKAGES)
    return {
        "schema_version": 1,
        "python_supported": python_supported,
        "packages": packages,
        "tools": tools,
        "capabilities": {
            "generation": base_ready,
            "web": base_ready and all(packages[name] for name in WEB_PACKAGES),
            "validation": base_ready and all(tools.values()),
            "plan_review": base_ready,
        },
        "limitations": "Local availability only. Package metadata and PATH discovery do not verify executable trust, working imports, provider installation, cloud identity or account capabilities. No tools are executed and no credentials are read.",
    }
