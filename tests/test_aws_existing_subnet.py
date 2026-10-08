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

SUBNET = "subnet-0123456789abcdef0"
GROUP = "sg-0123456789abcdef0"
OWNED = (
    "aws_vpc.this",
    "aws_subnet.public",
    "aws_subnet.private",
    "aws_internet_gateway.this",
    "aws_route_table.public",
    "aws_route_table_association.public",
    "aws_security_group.web",
    "aws_eip.nat",
    "aws_nat_gateway.this",
    "aws_route_table.private",
    "aws_route_table_association.private",
)


def subnet_spec(windows=False, public=False, custom=False, **changes):
    spec = specification("aws", windows, custom, public)
    spec.inputs.update(
        use_existing_network=True,
        existing_subnetwork_resource=SUBNET,
        existing_security_group_id=GROUP,
        existing_subnet_cidr="10.55.0.0/24",
        confirm_existing_network_review=True,
        private_ip_address="10.55.0.4",
    )
    spec.inputs.update(changes)
    return spec


@pytest.mark.parametrize("windows", [False, True])
@pytest.mark.parametrize("public", [False, True])
def test_existing_subnet_and_group_leave_network_ownership_separate(windows, public):
    result = compile_project(subnet_spec(windows, public))
    main = hcl2.loads(result["files"]["main.tf"])
    resources = {}
    for entry in main["resource"]:
        for kind, values in entry.items():
            resources.setdefault(kind.strip('"'), {}).update(
                {name.strip('"'): value for name, value in values.items()}
            )
    for address in OWNED:
        kind, name = address.split(".")
        if name not in resources.get(kind, {}):
            assert public and address in OWNED[-4:]
            continue
        assert resources[kind][name]["count"] in (
            "${var.use_existing_network ? 0 : 1}",
            "${var.use_existing_network ? 0 : 2}",
        )
    vm = resources["aws_instance"]["web"]
    assert "data.aws_subnet.existing[0].id" in vm["subnet_id"]
    assert "data.aws_security_group.existing[0].id" in vm["vpc_security_group_ids"]
    assert vm["associate_public_ip_address"] is public
    assert len(main["moved"]) == (4 if public else 7)
    assert "self.owner_id == var.aws_account_id" in result["files"]["main.tf"]
    assert "self.vpc_id == data.aws_subnet.existing[0].vpc_id" in result["files"]["main.tf"]


@pytest.mark.parametrize(
    "changes,field",
    [
        ({"existing_subnetwork_resource": ""}, "existing_subnetwork_resource"),
        (
            {"existing_subnetwork_resource": "https://secret-marker/subnet"},
            "existing_subnetwork_resource",
        ),
        ({"existing_security_group_id": ""}, "existing_security_group_id"),
        ({"existing_security_group_id": "sg-invalid"}, "existing_security_group_id"),
        ({"confirm_existing_network_review": False}, "confirm_existing_network_review"),
        ({"use_existing_network": False}, "use_existing_network"),
        ({"network_cidr": "10.32.0.0/16"}, "use_existing_network"),
        ({"existing_subnet_cidr": "0.0.0.0/0"}, "existing_subnet_cidr"),
        ({"existing_subnet_cidr": "10.55.0.1/24"}, "existing_subnet_cidr"),
        ({"private_ip_address": "10.56.0.4"}, "private_ip_address"),
        *[
            ({"private_ip_address": f"10.55.0.{offset}"}, "private_ip_address")
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
    assert browser_ranges([["aws", False, "10.55.0.0/24", True]]) == [
        {"subnet": "10.55.0.0/24", "first": "10.55.0.4", "last": "10.55.0.254"}
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
    assert result["guide"]["components"][0]["name"] == "Existing AWS subnet"
    assert "creates no access rule" in json.dumps(result["guide"])


@pytest.mark.parametrize("windows", [False, True])
def test_terminal_collects_subnet_group_and_actual_range(windows, monkeypatch):
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
    assert "existing_security_group_id" in asked
    assert "network_cidr" not in asked
    assert result["specification"]["inputs"]["private_ip_address"] == "10.55.0.4"


@pytest.mark.parametrize("windows", [False, True])
@pytest.mark.parametrize("public", [False, True])
@pytest.mark.parametrize("custom", [False, True])
def test_native_existing_subnet_combinations(native_directories, windows, public, custom):
    assert_native_files(
        native_directories["aws"], compile_project(subnet_spec(windows, public, custom))["files"]
    )


@pytest.mark.parametrize("windows", [False, True])
def test_native_mocked_existing_metadata_guards(native_directories, windows):
    directory = native_directories["aws"]
    assert_native_files(directory, compile_project(subnet_spec(windows))["files"])
    tests = directory / "aws-offline-tests"
    tests.mkdir(exist_ok=True)
    subnet_values = 'cidr_block = "10.55.0.0/24", owner_id = "123456789012", vpc_id = "vpc-0123456789abcdef0", availability_zone = "us-east-1a", ipv6_native = false, ipv6_cidr_block = "", outpost_arn = ""'
    group_values = 'vpc_id = "vpc-0123456789abcdef0", arn = "arn:aws:ec2:us-east-1:123456789012:security-group/sg-0123456789abcdef0"'
    runs = []
    for name, target, values in (
        (
            "reject_cidr_mismatch",
            "aws_subnet",
            subnet_values.replace("10.55.0.0/24", "10.56.0.0/24"),
        ),
        (
            "reject_shared_subnet",
            "aws_subnet",
            subnet_values.replace("123456789012", "987654321098"),
        ),
        (
            "reject_ipv6_subnet",
            "aws_subnet",
            subnet_values.replace('ipv6_cidr_block = ""', 'ipv6_cidr_block = "2001:db8::/64"'),
        ),
        (
            "reject_wrong_vpc",
            "aws_security_group",
            group_values.replace("vpc-0123456789abcdef0", "vpc-1123456789abcdef0"),
        ),
        (
            "reject_outposts_subnet",
            "aws_subnet",
            subnet_values.replace(
                'outpost_arn = ""',
                'outpost_arn = "arn:aws:outposts:us-east-1:123456789012:outpost/op-test"',
            ),
        ),
        (
            "reject_nonstandard_zone",
            "aws_subnet",
            subnet_values.replace("us-east-1a", "us-east-1-bos-1a"),
        ),
        (
            "reject_group_account",
            "aws_security_group",
            group_values.replace("123456789012", "987654321098"),
        ),
    ):
        runs.append(
            f'run "{name}" {{\n command = plan\n providers = {{ aws = aws.offline }}\n override_data {{\n target = data.{target}.existing[0]\n values = {{ {values} }}\n }}\n expect_failures = [data.{target}.existing]\n}}'
        )
    guards = " && ".join(f"length({address}) == 0" for address in OWNED)
    content = f'''mock_provider "aws" {{
  alias = "offline"
  override_during = plan
  mock_data "aws_subnet" {{ defaults = {{ id = "{SUBNET}", {subnet_values} }} }}
  mock_data "aws_security_group" {{ defaults = {{ id = "{GROUP}", {group_values} }} }}
  mock_data "aws_ami" {{ defaults = {{ id = "ami-0123456789abcdef0" }} }}
}}
run "existing_network_ownership" {{
  command = plan
  providers = {{ aws = aws.offline }}
  assert {{
    condition = {guards}
    error_message = "Existing attachment must leave network resources independently managed."
  }}
}}
''' + "\n".join(runs)
    (tests / "attachment.tftest.hcl").write_text(content, encoding="utf-8")
    result = subprocess.run(
        [shutil.which("terraform"), "test", "-test-directory=aws-offline-tests", "-no-color"],
        cwd=directory,
        capture_output=True,
        text=True,
        timeout=60,
        check=False,
    )
    assert result.returncode == 0, result.stdout + result.stderr
