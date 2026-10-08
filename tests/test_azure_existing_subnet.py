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
from tests.test_private_ip import browser_ranges

pytest_plugins = ["tests.test_generator"]

SUBNET = "/subscriptions/00000000-0000-0000-0000-000000000001/resourceGroups/network-library/providers/Microsoft.Network/virtualNetworks/approved-network/subnets/vm-subnet"
OWNED = (
    "azurerm_virtual_network.this",
    "azurerm_subnet.this",
    "azurerm_network_security_group.this",
    "azurerm_subnet_network_security_group_association.this",
    "azurerm_public_ip.egress",
    "azurerm_nat_gateway.this",
    "azurerm_nat_gateway_public_ip_association.this",
    "azurerm_subnet_nat_gateway_association.this",
)


def subnet_spec(windows=False, public=False, custom=False, **changes):
    spec = specification("azure", windows, custom, public)
    spec.inputs.update(
        use_existing_network=True,
        existing_subnetwork_resource=SUBNET,
        existing_subnet_cidr="10.44.0.0/24",
        confirm_existing_network_review=True,
        private_ip_address="10.44.0.4",
    )
    spec.inputs.update(changes)
    return spec


@pytest.mark.parametrize("windows", [False, True])
def test_existing_subnet_preserves_separate_network_ownership(windows):
    result = compile_project(subnet_spec(windows))
    main = hcl2.loads(result["files"]["main.tf"])
    resources = {}
    for entry in main["resource"]:
        for kind, values in entry.items():
            resources.setdefault(kind.strip('"'), {}).update(
                {name.strip('"'): value for name, value in values.items()}
            )
    for address in OWNED:
        kind, name = address.split(".")
        assert resources[kind][name]["count"] == "${var.use_existing_network ? 0 : 1}"
    assert (
        "data.azurerm_subnet.existing[0].id"
        in resources["azurerm_network_interface"]["this"]["ip_configuration"][0]["subnet_id"]
    )
    assert len(main["moved"]) == len(OWNED)
    assert all(move["to"].endswith("[0]}") for move in main["moved"])
    assert "self.network_security_group_id != null" in result["files"]["main.tf"]
    assert "self.address_prefixes[0] == var.existing_subnet_cidr" in result["files"]["main.tf"]
    assert 'lower(replace(self.location, " ", "")) == var.location' in result["files"]["main.tf"]


@pytest.mark.parametrize(
    "changes,field",
    [
        ({"existing_subnetwork_resource": ""}, "existing_subnetwork_resource"),
        (
            {"existing_subnetwork_resource": "https://secret-marker/subnet"},
            "existing_subnetwork_resource",
        ),
        (
            {"existing_subnetwork_resource": SUBNET.replace("000000000001", "000000000002")},
            "existing_subnetwork_resource",
        ),
        ({"confirm_existing_network_review": False}, "confirm_existing_network_review"),
        ({"use_existing_network": False}, "use_existing_network"),
        ({"network_cidr": "10.32.0.0/16"}, "use_existing_network"),
        ({"existing_subnet_cidr": "0.0.0.0/0"}, "existing_subnet_cidr"),
        ({"existing_subnet_cidr": "10.44.0.1/24"}, "existing_subnet_cidr"),
        ({"private_ip_address": "10.44.1.4"}, "private_ip_address"),
        *[
            ({"private_ip_address": f"10.44.0.{offset}"}, "private_ip_address")
            for offset in (0, 1, 2, 3, 255)
        ],
    ],
)
def test_invalid_existing_declarations_fail_closed(changes, field):
    with pytest.raises(ProjectInputError) as error:
        compile_project(subnet_spec(**changes))
    assert error.value.field == field
    assert "secret-marker" not in str(error.value)
    assert SUBNET not in str(error.value)


def test_existing_subnet_requires_explicit_range_and_browser_hints_match():
    spec = subnet_spec()
    del spec.inputs["existing_subnet_cidr"]
    with pytest.raises(ProjectInputError) as error:
        compile_project(spec)
    assert error.value.field == "existing_subnet_cidr"
    assert browser_ranges([["azure", False, "10.44.0.0/24", True]]) == [
        {"subnet": "10.44.0.0/24", "first": "10.44.0.4", "last": "10.44.0.254"}
    ]


@pytest.mark.parametrize("windows", [False, True])
def test_offline_browser_roundtrip_and_guidance(windows, monkeypatch):
    monkeypatch.setattr(
        "subprocess.run", lambda *a, **k: pytest.fail("Import/export must not execute tools.")
    )
    spec = subnet_spec(windows)
    with TestClient(create_app(), base_url="http://127.0.0.1") as client:
        headers = {"X-TerraForma-Token": client.get("/api/session").json()["token"]}
        response = client.post("/api/download", headers=headers, json=spec.model_dump())
        assert response.status_code == 200, response.text
        with zipfile.ZipFile(io.BytesIO(response.content)) as archive:
            manifest = archive.read("terraforma.project.json")
        assert json.loads(manifest)["inputs"] == spec.inputs
        response = client.post("/api/projects/import", headers=headers, content=manifest)
    assert response.status_code == 200, response.text
    result = response.json()
    assert result["target"]["identity_verified"] is False
    assert result["guide"]["components"][0]["name"] == "Existing Azure subnet"
    assert "creates no access rule" in json.dumps(result["guide"])


@pytest.mark.parametrize("windows", [False, True])
def test_terminal_collects_existing_range_and_hides_new_network(windows, monkeypatch):
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
    assert "existing_subnet_cidr" in asked
    assert "network_cidr" not in asked
    assert result["specification"]["inputs"]["private_ip_address"] == "10.44.0.4"


@pytest.mark.parametrize("windows", [False, True])
@pytest.mark.parametrize("public", [False, True])
@pytest.mark.parametrize("custom", [False, True])
def test_native_existing_subnet_combinations(native_directories, windows, public, custom):
    assert_native_files(
        native_directories["azure"], compile_project(subnet_spec(windows, public, custom))["files"]
    )


@pytest.mark.parametrize("windows", [False, True])
def test_native_mocked_existing_metadata_guards(native_directories, windows):
    directory = native_directories["azure"]
    assert_native_files(directory, compile_project(subnet_spec(windows))["files"])
    tests = directory / "azure-offline-tests"
    tests.mkdir(exist_ok=True)
    guards = " && ".join(f"length({address}) == 0" for address in OWNED)
    password = 'variables { admin_password = "Offline-Test-Only-123!" }' if windows else ""
    runs = []
    for name, target, values in (
        (
            "reject_cidr_mismatch",
            "azurerm_subnet",
            '{ address_prefixes = ["10.45.0.0/24"], network_security_group_id = "existing-nsg" }',
        ),
        (
            "reject_missing_nsg",
            "azurerm_subnet",
            '{ address_prefixes = ["10.44.0.0/24"], network_security_group_id = "" }',
        ),
        (
            "reject_region_mismatch",
            "azurerm_virtual_network",
            '{ location = "westus", name = "approved-network" }',
        ),
    ):
        runs.append(
            f'run "{name}" {{\n command = plan\n providers = {{ azurerm = azurerm.offline }}\n override_data {{\n target = data.{target}.existing[0]\n values = {values}\n }}\n expect_failures = [data.{target}.existing]\n}}'
        )
    content = f"""mock_provider "azurerm" {{
  alias = "offline"
  override_during = plan
  mock_data "azurerm_virtual_network" {{ defaults = {{ location = "eastus", name = "approved-network" }} }}
  mock_data "azurerm_subnet" {{ defaults = {{ id = "{SUBNET}", address_prefixes = ["10.44.0.0/24"], network_security_group_id = "existing-nsg" }} }}
  mock_resource "azurerm_network_interface" {{ defaults = {{ id = "/subscriptions/00000000-0000-0000-0000-000000000001/resourceGroups/test/providers/Microsoft.Network/networkInterfaces/test" }} }}
}}
{password}
run "existing_network_ownership" {{
  command = plan
  providers = {{ azurerm = azurerm.offline }}
  assert {{
    condition = {guards}
    error_message = "Existing attachment must leave network resources independently managed."
  }}
}}
""" + "\n".join(runs)
    (tests / "attachment.tftest.hcl").write_text(content, encoding="utf-8")
    result = subprocess.run(
        [shutil.which("terraform"), "test", "-test-directory=azure-offline-tests", "-no-color"],
        cwd=directory,
        capture_output=True,
        text=True,
        timeout=60,
        check=False,
    )
    assert result.returncode == 0, result.stdout + result.stderr
