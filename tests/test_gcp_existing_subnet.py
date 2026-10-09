import io
import json
import shutil
import subprocess
import zipfile
from unittest.mock import Mock

import hcl2
import pytest
from fastapi.testclient import TestClient

from terraforma.cli import collect_recipe_inputs
from terraforma.project import ProjectInputError, compile_project, input_contract
from terraforma.web import create_app
from tests.test_custom_images import specification
from tests.test_generator import assert_native_files

pytest_plugins = ["tests.test_generator"]

SUBNET = "projects/example-project/regions/us-central1/subnetworks/vm-network"


def subnet_spec(windows=False, public=False, custom=False, iap=False, **changes):
    spec = specification("gcp", windows, custom, public)
    spec.inputs.update(
        use_existing_network=True,
        existing_subnetwork_resource=SUBNET,
        confirm_existing_network_review=True,
        network_cidr="10.60.0.0/24",
        private_ip_address="10.60.0.2",
        admin_access_method="iap_tunnel" if iap else "administrator_network",
    )
    spec.inputs.update(changes)
    return spec


@pytest.mark.parametrize("windows", [False, True])
def test_existing_subnet_leaves_network_rules_routes_nat_and_api_unmanaged(windows):
    result = compile_project(subnet_spec(windows))
    main = hcl2.loads(result["files"]["main.tf"])
    resources = {}
    for entry in main["resource"]:
        for kind, values in entry.items():
            resources.setdefault(kind, {}).update(values)
    for kind in (
        "google_project_service",
        "google_compute_network",
        "google_compute_subnetwork",
        "google_compute_firewall",
        "google_compute_router",
        "google_compute_router_nat",
        "google_compute_route",
    ):
        for name, resource in resources.get(f'"{kind}"', {}).items():
            if kind == "google_compute_firewall" and name in (
                '"outbound_web_dns"',
                '"outbound_deny_other"',
            ):
                assert (
                    resource["count"]
                    == '${var.use_existing_network || var.outbound_access != "https_dns" ? 0 : 1}'
                )
            else:
                assert resource["count"] == "${var.use_existing_network ? 0 : 1}"
    vm = resources['"google_compute_instance"']['"this"']
    assert vm["tags"] == '${var.use_existing_network ? [] : ["terraforma-web"]}'
    assert (
        "data.google_compute_subnetwork.existing[0].self_link"
        in vm["network_interface"][0]["subnetwork"]
    )
    assert "self.ip_cidr_range == var.network_cidr" in result["files"]["main.tf"]
    assert 'self.stack_type == "IPV4_ONLY"' in result["files"]["main.tf"]
    assert len(main["moved"]) == (8 if windows else 6)
    assert all(move["to"].endswith("[0]}") for move in main["moved"])


@pytest.mark.parametrize(
    "changes,field",
    [
        ({"existing_subnetwork_resource": ""}, "existing_subnetwork_resource"),
        (
            {"existing_subnetwork_resource": "https://secret-marker/subnet"},
            "existing_subnetwork_resource",
        ),
        (
            {"existing_subnetwork_resource": SUBNET.replace("example-project", "other-project")},
            "existing_subnetwork_resource",
        ),
        (
            {"existing_subnetwork_resource": SUBNET.replace("us-central1", "us-east1")},
            "existing_subnetwork_resource",
        ),
        ({"confirm_existing_network_review": False}, "confirm_existing_network_review"),
        ({"use_existing_network": False}, "use_existing_network"),
        ({"private_ip_address": "10.61.0.4"}, "private_ip_address"),
        ({"private_ip_address": "10.60.0.1"}, "private_ip_address"),
        ({"network_cidr": "0.0.0.0/0"}, "network_cidr"),
    ],
)
def test_invalid_existing_subnet_declarations_fail_closed(changes, field):
    with pytest.raises(ProjectInputError) as error:
        compile_project(subnet_spec(**changes))
    assert error.value.field == field
    assert "secret-marker" not in str(error.value)
    assert SUBNET not in str(error.value)


def test_existing_subnet_requires_explicit_range():
    spec = subnet_spec()
    del spec.inputs["network_cidr"]
    with pytest.raises(ProjectInputError) as error:
        compile_project(spec)
    assert error.value.field == "network_cidr"


@pytest.mark.parametrize("windows", [False, True])
def test_existing_subnet_browser_roundtrip_and_guidance_do_not_execute(windows, monkeypatch):
    monkeypatch.setattr(
        "subprocess.run",
        lambda *a, **k: pytest.fail("Offline import/export must not execute tools."),
    )
    spec = subnet_spec(windows, iap=True)
    with TestClient(create_app(), base_url="http://127.0.0.1") as client:
        headers = {"X-TerraForma-Token": client.get("/api/session").json()["token"]}
        exported = client.post("/api/download", headers=headers, json=spec.model_dump())
        assert exported.status_code == 200, exported.text
        with zipfile.ZipFile(io.BytesIO(exported.content)) as archive:
            manifest = archive.read("terraforma.project.json")
        assert json.loads(manifest)["inputs"] == spec.inputs
        imported = client.post("/api/projects/import", headers=headers, content=manifest)
    assert imported.status_code == 200, imported.text
    result = imported.json()
    assert result["target"]["identity_verified"] is False
    assert result["guide"]["route"][1] == "Existing access rules (separate review)"
    assert "creates no access rule" in json.dumps(result["guide"])


@pytest.mark.parametrize("windows", [False, True])
def test_terminal_collects_existing_subnet_and_actual_cidr(windows, monkeypatch):
    spec = subnet_spec(windows)
    fields = {field["label"]: field for field in input_contract(spec.recipe)}
    asked = []

    def prompt(message, **options):
        field = fields[message.rstrip("?:")]
        asked.append(field["name"])
        answer = spec.inputs.get(field["name"], field["default"])
        return Mock(ask=lambda: str(answer) if field["kind"] == "integer" else answer)

    for kind in ("text", "confirm", "select"):
        monkeypatch.setattr(f"terraforma.cli.questionary.{kind}", prompt)
    result = compile_project(collect_recipe_inputs(spec.recipe))
    assert "existing_subnetwork_resource" in asked
    assert result["specification"]["inputs"]["network_cidr"] == "10.60.0.0/24"


@pytest.mark.parametrize("windows", [False, True])
@pytest.mark.parametrize("public", [False, True])
@pytest.mark.parametrize("custom", [False, True])
@pytest.mark.parametrize("iap", [False, True])
def test_native_existing_subnet_combinations(native_directories, windows, public, custom, iap):
    assert_native_files(
        native_directories["gcp"],
        compile_project(subnet_spec(windows, public, custom, iap))["files"],
    )


@pytest.mark.parametrize("windows", [False, True])
def test_mocked_plan_leaves_existing_network_infrastructure_outside_management(
    native_directories, windows
):
    directory = native_directories["gcp"]
    assert_native_files(directory, compile_project(subnet_spec(windows))["files"])
    tests = directory / "offline-tests"
    tests.mkdir(exist_ok=True)
    (tests / "attachment.tftest.hcl").write_text(
        """
mock_provider "google" {
  alias = "offline"
  override_during = plan
  mock_data "google_compute_subnetwork" {
    defaults = {
      ip_cidr_range = "10.60.0.0/24"
      stack_type = "IPV4_ONLY"
      self_link = "https://www.googleapis.com/compute/v1/projects/example-project/regions/us-central1/subnetworks/vm-network"
    }
  }
}
run "attachment_without_network_management" {
  command = plan
  providers = {
    google = google.offline
  }
  assert {
    condition = length(google_compute_network.this) == 0 && length(google_compute_subnetwork.this) == 0 && length(google_compute_firewall.this) == 0 && length(google_compute_firewall.outbound_web_dns) == 0 && length(google_compute_firewall.outbound_deny_other) == 0 && length(google_compute_router.this) == 0 && length(google_compute_router_nat.this) == 0 && length(google_project_service.compute) == 0
    error_message = "Existing attachment must not manage network infrastructure, access rules or API enablement."
  }
  assert {
    condition = length(google_compute_instance.this.tags) == 0
    error_message = "Existing attachment must not automatically adopt existing network tags."
  }
}
run "reject_mismatched_actual_subnet_range" {
  command = plan
  providers = { google = google.offline }
  override_data {
    target = data.google_compute_subnetwork.existing[0]
    values = {
      ip_cidr_range = "10.61.0.0/24"
      stack_type = "IPV4_ONLY"
      self_link = "https://www.googleapis.com/compute/v1/projects/example-project/regions/us-central1/subnetworks/vm-network"
    }
  }
  expect_failures = [data.google_compute_subnetwork.existing]
}
run "reject_non_ipv4_only_subnet" {
  command = plan
  providers = { google = google.offline }
  override_data {
    target = data.google_compute_subnetwork.existing[0]
    values = {
      ip_cidr_range = "10.60.0.0/24"
      stack_type = "IPV4_IPV6"
      self_link = "https://www.googleapis.com/compute/v1/projects/example-project/regions/us-central1/subnetworks/vm-network"
    }
  }
  expect_failures = [data.google_compute_subnetwork.existing]
}
""",
        encoding="utf-8",
    )
    result = subprocess.run(
        [shutil.which("terraform"), "test", "-test-directory=offline-tests", "-no-color"],
        cwd=directory,
        capture_output=True,
        text=True,
        timeout=60,
        check=False,
    )
    assert result.returncode == 0, result.stdout + result.stderr
