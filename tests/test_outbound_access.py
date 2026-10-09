import json
from unittest.mock import Mock

import hcl2
import pytest
from fastapi.testclient import TestClient

from terraforma.cli import collect_recipe_inputs
from terraforma.generator import WizardConfig
from terraforma.project import ProjectInputError, compile_project, input_contract
from terraforma.web import create_app
from tests.test_custom_images import specification
from tests.test_generator import assert_native_files
from tests.test_preflight_web import headers

pytest_plugins = ["tests.test_generator"]


@pytest.mark.parametrize("provider", ["aws", "azure", "gcp"])
@pytest.mark.parametrize("windows", [False, True])
@pytest.mark.parametrize("existing", [False, True])
def test_terminal_collects_profile_only_for_owned_network(provider, windows, existing, monkeypatch):
    from tests.test_aws_existing_subnet import subnet_spec as aws_spec
    from tests.test_azure_existing_subnet import subnet_spec as azure_spec
    from tests.test_gcp_existing_subnet import subnet_spec as gcp_spec

    spec = (
        {"aws": aws_spec, "azure": azure_spec, "gcp": gcp_spec}[provider](windows=windows)
        if existing
        else specification(provider, windows=windows, custom=False, outbound_access="https_dns")
    )
    fields = {field["label"]: field for field in input_contract(spec.recipe)}
    asked = []

    def prompt(message, **options):
        field = fields[message.rstrip("?:")]
        asked.append(field["name"])
        answer = spec.inputs.get(field["name"], field["default"])
        return Mock(ask=lambda: str(answer) if field["kind"] == "integer" else answer)

    for kind in ("text", "confirm", "select"):
        monkeypatch.setattr(f"terraforma.cli.questionary.{kind}", prompt)
    collected = collect_recipe_inputs(spec.recipe)
    result = compile_project(collected)
    assert ("outbound_access" in asked) is (not existing)
    assert collected.inputs.get("outbound_access", "unrestricted") == (
        "unrestricted" if existing else "https_dns"
    )
    assert result["files"]["main.tf"]


@pytest.mark.parametrize("provider", ["aws", "azure", "gcp"])
@pytest.mark.parametrize("windows", [False, True])
@pytest.mark.parametrize("public", [False, True])
@pytest.mark.parametrize("profile", ["unrestricted", "https_dns"])
def test_outbound_profile_is_collected_exported_and_restored(provider, windows, public, profile):
    spec = specification(
        provider, windows=windows, custom=False, public=public, outbound_access=profile
    )
    project = compile_project(spec)
    defaults = {
        name.strip('"'): value["default"]
        for item in hcl2.loads(project["files"]["variables.tf"])["variable"]
        for name, value in item.items()
        if "default" in value
    }
    value = defaults["outbound_access"]
    assert (json.loads(value) if value.startswith('"') else value) == profile
    field = next(
        field for field in input_contract(spec.recipe) if field["name"] == "outbound_access"
    )
    assert field["visible_when"] == {"use_existing_network": False}
    assert field["choices"] == ["unrestricted", "https_dns"]
    assert field["default"] == "unrestricted"
    assert "outbound_access" in project["files"]["main.tf"]
    with TestClient(create_app(), base_url="http://127.0.0.1") as client:
        response = client.post(
            "/api/projects/import", headers=headers(client), json=project["specification"]
        )
        assert response.status_code == 200
        assert response.json()["files"] == project["files"]
        assert response.json()["target"]["identity_verified"] is False


@pytest.mark.parametrize("provider", ["aws", "azure", "gcp"])
@pytest.mark.parametrize("value", ["private_only", "all", True, 443, "private-marker"])
def test_unsupported_outbound_profile_rejected(provider, value):
    spec = specification(provider, custom=False, outbound_access=value)
    with pytest.raises(ProjectInputError):
        compile_project(spec)


@pytest.mark.parametrize("provider", ["aws", "azure", "gcp"])
def test_restricted_profile_cannot_be_applied_to_separately_managed_network(provider):
    from tests.test_aws_existing_subnet import subnet_spec as aws_spec
    from tests.test_azure_existing_subnet import subnet_spec as azure_spec
    from tests.test_gcp_existing_subnet import subnet_spec as gcp_spec

    spec = {"aws": aws_spec, "azure": azure_spec, "gcp": gcp_spec}[provider]()
    spec.inputs["outbound_access"] = "https_dns"
    with pytest.raises(ProjectInputError, match="outbound_access"):
        compile_project(spec)


@pytest.mark.parametrize("provider", ["aws", "azure", "gcp"])
@pytest.mark.parametrize(
    "workload", ["single_web_server", "load_balanced_tier", "static_site", "secure_database"]
)
def test_other_workloads_do_not_advertise_standalone_outbound_profiles(provider, workload):
    contract = input_contract(
        WizardConfig(provider=provider, project_name="outbound", architecture_type=workload)
    )
    assert not any(field["name"] == "outbound_access" for field in contract)


@pytest.mark.parametrize("provider", ["aws", "azure", "gcp"])
@pytest.mark.parametrize("windows", [False, True])
@pytest.mark.parametrize("public", [False, True])
@pytest.mark.parametrize("profile", ["unrestricted", "https_dns"])
def test_native_outbound_profile(native_directories, provider, windows, public, profile):
    spec = specification(
        provider, windows=windows, custom=False, public=public, outbound_access=profile
    )
    assert_native_files(native_directories[provider], compile_project(spec)["files"])
