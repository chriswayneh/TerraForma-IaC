import itertools

import hcl2
import pytest
from fastapi.testclient import TestClient

from terraforma.generator import WizardConfig
from terraforma.project import ProjectInputError, compile_project, input_contract
from terraforma.web import create_app
from tests.hcl_text import unaligned
from tests.test_gcp_scheduling import specification


@pytest.mark.parametrize(
    "windows,public,method",
    list(itertools.product([False, True], [False, True], ["administrator_network", "iap_tunnel"])),
)
def test_gcp_access_choice_binds_only_one_administrator_port(windows, public, method):
    spec = specification(windows, admin_access_method=method)
    spec.recipe.is_public = public
    if public and method == "administrator_network":
        spec.inputs["allowed_cidr"] = "10.0.0.0/16"
    result = compile_project(spec)
    main = hcl2.loads(result["files"]["main.tf"])
    rule = next(
        item['"google_compute_firewall"']['"this"']
        for item in main["resource"]
        if '"this"' in item.get('"google_compute_firewall"', {})
    )
    assert rule["direction"] == '"INGRESS"' and rule["disabled"] is False
    assert rule["source_ranges"] == (
        '${var.admin_access_method == "iap_tunnel" ? ["35.235.240.0/20"] : [var.allowed_cidr]}'
    )
    assert rule["target_tags"] == ['"terraforma-web"']
    assert len(rule["allow"]) == 1
    assert rule["allow"][0]["protocol"] == '"tcp"'
    assert rule["allow"][0]["ports"] == ['"3389"' if windows else '"22"']
    assert not any("iam" in next(iter(item)) for item in main["resource"])
    summary = {item["name"]: item for item in result["choice_summary"]}
    assert summary["admin_access_method"]["value"] == method
    assert ("allowed_cidr" in summary) is (method == "administrator_network")
    assert f'default = "{method}"' in unaligned(result["files"]["variables.tf"])


@pytest.mark.parametrize("windows", [False, True])
def test_older_gcp_manifest_keeps_direct_access_with_private_network_default(windows):
    spec = specification(windows)
    contract = {item["name"]: item for item in input_contract(spec.recipe)}
    assert contract["admin_access_method"]["default"] == "administrator_network"
    assert contract["allowed_cidr"]["visible_when"] == {
        "admin_access_method": "administrator_network"
    }
    assert contract["allowed_cidr"]["default"] == "10.0.0.0/16"
    assert "does not grant access" in contract["admin_access_method"]["description"]
    assert compile_project(spec)["files"]["main.tf"]


@pytest.mark.parametrize("windows", [False, True])
@pytest.mark.parametrize("value", ["iap", "IAP_TUNNEL", True])
def test_invalid_access_choice_is_rejected_before_generation(windows, value):
    with pytest.raises(ProjectInputError) as error:
        compile_project(specification(windows, admin_access_method=value))
    assert error.value.field == "admin_access_method"


@pytest.mark.parametrize("windows", [False, True])
def test_api_import_preserves_iap_choice_and_generates_without_an_admin_cidr(windows):
    spec = specification(windows, admin_access_method="iap_tunnel")
    spec.recipe.is_public = True
    with TestClient(create_app(), base_url="http://127.0.0.1") as client:
        headers = {"X-TerraForma-Token": client.get("/api/session").json()["token"]}
        imported = client.post("/api/projects/import", json=spec.model_dump(), headers=headers)
        assert imported.status_code == 200, imported.text
        generated = client.post("/api/generate", json=spec.model_dump(), headers=headers)
        assert generated.status_code == 200, generated.text
    assert generated.json()["specification"]["inputs"]["admin_access_method"] == "iap_tunnel"
    assert "allowed_cidr" not in {item["name"] for item in generated.json()["required_inputs"]}
    assert generated.json()["guide"]["route"][0] == "Authorized Google IAP tunnel"
    access = next(
        component
        for component in generated.json()["guide"]["components"]
        if component["name"] == "Administrator access"
    )
    assert "grants no access" in access["explanation"]


@pytest.mark.parametrize(
    "provider,workload",
    [
        ("aws", "virtual_machine"),
        ("azure", "windows_virtual_machine"),
        ("gcp", "single_web_server"),
        ("gcp", "static_site"),
        ("gcp", "secure_database"),
    ],
)
def test_other_recipes_do_not_offer_iap(provider, workload):
    recipe = WizardConfig(provider=provider, architecture_type=workload, project_name="demo")
    assert "admin_access_method" not in {item["name"] for item in input_contract(recipe)}
