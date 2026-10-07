import json
from importlib.metadata import PackageNotFoundError
from types import SimpleNamespace

import pytest
from click.testing import CliRunner

from terraforma.cli import main
from terraforma.readiness import local_readiness


def availability(monkeypatch, *, missing_packages=(), missing_tools=()):
    def package(name):
        if name in missing_packages:
            raise PackageNotFoundError(name)
        return object()

    monkeypatch.setattr("terraforma.readiness.distribution", package)
    monkeypatch.setattr(
        "terraforma.readiness.shutil.which",
        lambda name: None if name in missing_tools else "C:/private-machine-location/tool.exe",
    )


@pytest.mark.parametrize("missing", [(), ("terraform",), ("tflint",), ("terraform", "tflint")])
def test_native_dependencies_only_gate_validation(monkeypatch, missing):
    availability(monkeypatch, missing_tools=missing)
    report = local_readiness()
    assert report["capabilities"] == {
        "generation": True,
        "web": True,
        "validation": not bool(missing),
        "plan_review": True,
    }
    assert "private-machine-location" not in json.dumps(report)


@pytest.mark.parametrize("missing", ["fastapi", "uvicorn"])
def test_web_packages_only_gate_web(monkeypatch, missing):
    availability(monkeypatch, missing_packages=(missing,))
    report = local_readiness()
    assert report["capabilities"]["web"] is False
    assert all(report["capabilities"][name] for name in ("generation", "validation", "plan_review"))


def test_base_package_or_unsupported_python_gates_all_capabilities(monkeypatch):
    availability(monkeypatch, missing_packages=("pydantic",))
    assert not any(local_readiness()["capabilities"].values())
    availability(monkeypatch)
    monkeypatch.setattr("terraforma.readiness.sys", SimpleNamespace(version_info=(3, 10)))
    assert not any(local_readiness()["capabilities"].values())


@pytest.mark.parametrize("required,exit_code", [("generation", 0), ("validation", 1)])
def test_cli_exit_for_selected_capability_and_private_environment(monkeypatch, required, exit_code):
    availability(monkeypatch, missing_tools=("terraform",))
    monkeypatch.setenv("OPENAI_API_KEY", "private-key-marker")
    monkeypatch.setenv("AWS_SECRET_ACCESS_KEY", "private-credential-marker")
    result = CliRunner().invoke(main, ["doctor", "--require", required, "--json-output"])
    assert result.exit_code == exit_code
    assert json.loads(result.output)["tools"]["terraform"] is False
    assert not any(
        marker in result.output
        for marker in (
            "private-key-marker",
            "private-credential-marker",
            "private-machine-location",
        )
    )


def test_text_report_explains_missing_dependencies(monkeypatch):
    availability(monkeypatch, missing_packages=("uvicorn",), missing_tools=("tflint",))
    result = CliRunner().invoke(main, ["doctor", "--require", "web"])
    assert result.exit_code == 1
    assert "tflint: missing" in result.output
    assert 'python -m pip install -e ".[web]"' in result.output
    assert "No tools are executed and no credentials are read." in result.output
