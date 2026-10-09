import itertools
import json
import os
import shutil
import subprocess

import hcl2
import pytest
from fastapi.testclient import TestClient

from terraforma.generator import TerraformGenerator, WizardConfig
from terraforma.project import (
    ProjectInputError,
    ProjectSpecification,
    compile_project,
    input_contract,
)
from terraforma.web import create_app
from tests.test_virtual_machine import KEY
from tests.test_windows_vm import RSA_KEY


def specification(windows, public=False, **inputs):
    return ProjectSpecification(
        recipe=WizardConfig(
            provider="aws",
            project_name="placement-test",
            architecture_type="windows_virtual_machine" if windows else "virtual_machine",
            is_public=public,
        ),
        inputs={
            "aws_account_id": "123456789012",
            "ssh_public_key": RSA_KEY if windows else KEY,
            "allowed_cidr": "10.20.0.0/24",
            **inputs,
        },
    )


@pytest.mark.parametrize(
    "windows,public,zone",
    list(itertools.product([False, True], [False, True], ["", "us-east-1a", "us-east-1b"])),
)
def test_placement_reorders_matching_subnets_and_survives_api_import(windows, public, zone):
    spec = specification(windows, public, availability_zone=zone, enable_data_disk=True)
    with TestClient(create_app(), base_url="http://127.0.0.1") as client:
        headers = {"X-TerraForma-Token": client.get("/api/session").json()["token"]}
        response = client.post("/api/generate", json=spec.model_dump(), headers=headers)
        assert response.status_code == 200, response.text
        result = response.json()
    restored = ProjectSpecification.model_validate(result["specification"])
    assert restored.inputs["availability_zone"] == zone
    assert compile_project(restored)["files"] == result["files"]
    main = hcl2.loads(result["files"]["main.tf"])
    subnets = next(entry['"aws_subnet"'] for entry in main["resource"] if '"aws_subnet"' in entry)
    all_subnets = [entry['"aws_subnet"'] for entry in main["resource"] if '"aws_subnet"' in entry]
    public_subnet = subnets['"public"']
    assert "concat([var.availability_zone]" in public_subnet["availability_zone"]
    assert "zone != var.availability_zone" in public_subnet["availability_zone"]
    assert public_subnet["count"] == "${var.use_existing_network ? 0 : 2}"
    checked = [public_subnet]
    if public:
        # Public VMs use the public subnets directly; no unused private subnets are emitted.
        assert len(all_subnets) == 1
    else:
        private_subnet = all_subnets[1]['"private"']
        assert public_subnet["availability_zone"] == private_subnet["availability_zone"]
        assert private_subnet["count"] == "${var.use_existing_network ? 0 : 2}"
        checked.append(private_subnet)
    for subnet in checked:
        checks = subnet["lifecycle"][0]["precondition"]
        assert "length(data.aws_availability_zones.available.names) >= 2" in checks[0]["condition"]
        assert (
            "contains(data.aws_availability_zones.available.names, var.availability_zone)"
            in checks[1]["condition"]
        )
    zones = main["data"][0]['"aws_availability_zones"']['"available"']
    assert zones["filter"][0]["values"] == ['"opt-in-not-required"']
    assert "availability_zone = aws_instance.web[0].availability_zone" in result["files"]["main.tf"]
    answer = next(item for item in result["choice_summary"] if item["name"] == "availability_zone")
    assert answer["value"] == (zone or "Automatic placement (resolved at planning)")
    assert answer["source"] == "answer"


@pytest.mark.parametrize("windows", [False, True])
def test_old_project_defaults_to_automatic_standard_zone_placement(windows):
    spec = specification(windows)
    field = next(
        item for item in input_contract(spec.recipe) if item["name"] == "availability_zone"
    )
    assert field["default"] == "" and field["kind"] == "optional_zone"
    assert "account-specific" in field["description"]
    assert "delete disks" in field["description"]
    result = compile_project(spec)
    assert (
        next(item for item in result["choice_summary"] if item["name"] == "availability_zone")[
            "source"
        ]
        == "default"
    )


@pytest.mark.parametrize(
    "zone",
    [
        "us-west-2a",
        "us-east-1aa",
        "use1-az1",
        "us-east-1-b",
        "us-east-1-bos-1a",
        "US-EAST-1A",
        "private-invalid-value",
        True,
        1,
    ],
)
def test_mismatched_or_unsupported_placement_answers_fail_closed(zone):
    with pytest.raises(ValueError):
        compile_project(specification(True, availability_zone=zone))


def test_region_mismatch_identifies_the_field_without_echoing_the_answer():
    with pytest.raises(ProjectInputError) as caught:
        compile_project(specification(False, availability_zone="us-west-2a"))
    assert caught.value.field == "availability_zone"
    assert "us-west-2a" not in str(caught.value)


@pytest.mark.parametrize(
    "region,zone",
    [
        ("us-gov-east-1", "us-gov-east-1b"),
        ("cn-northwest-1", "cn-northwest-1a"),
        ("eusc-de-east-1", "eusc-de-east-1a"),
    ],
)
def test_valid_format_remains_an_unverified_request_in_the_selected_region(region, zone):
    result = compile_project(specification(False, region=region, availability_zone=zone))
    assert result["specification"]["inputs"]["availability_zone"] == zone
    assert "unverified" in result["verification"]


@pytest.mark.parametrize(
    "workload", ["static_site", "single_web_server", "load_balanced_tier", "secure_database"]
)
def test_zone_input_is_limited_to_standalone_vm_recipes(workload):
    config = WizardConfig(provider="aws", project_name="example", architecture_type=workload)
    assert "availability_zone" not in {item["name"] for item in input_contract(config)}


@pytest.mark.skipif(
    os.environ.get("TERRAFORMA_NATIVE_TESTS") != "1", reason="Native Terraform console is opt-in"
)
@pytest.mark.parametrize(
    "requested,available,selected,allowed,enough",
    [
        ("", ["us-east-1a", "us-east-1b", "us-east-1c"], ["us-east-1a", "us-east-1b"], True, True),
        ("us-east-1a", ["us-east-1a", "us-east-1b"], ["us-east-1a", "us-east-1b"], True, True),
        ("us-east-1b", ["us-east-1a", "us-east-1b"], ["us-east-1b", "us-east-1a"], True, True),
        (
            "us-east-1c",
            ["us-east-1a", "us-east-1b", "us-east-1c"],
            ["us-east-1c", "us-east-1a"],
            True,
            True,
        ),
        ("us-east-1c", ["us-east-1a", "us-east-1b"], ["us-east-1c", "us-east-1a"], False, True),
        ("", ["us-east-1a"], [], True, False),
    ],
)
def test_native_subnet_zone_order_and_guards_with_mocked_zone_data(
    tmp_path, requested, available, selected, allowed, enough
):
    terraform = shutil.which("terraform")
    assert terraform, "Terraform must be on PATH for native tests"
    generator = TerraformGenerator(specification(False).recipe)
    generator.generate()
    subnet = next(
        item
        for item in generator.main
        if item.kind == "resource" and item.labels == ("aws_subnet", "public")
    )
    expression = subnet.attributes["availability_zone"].value
    checks = subnet.children[0].children
    replacement = "data.aws_availability_zones.available.names"
    zone0 = expression.replace(replacement, "var.available_zones").replace("count.index", "0")
    zone1 = expression.replace(replacement, "var.available_zones").replace("count.index", "1")
    sufficient = checks[0].attributes["condition"].value.replace(replacement, "var.available_zones")
    member = checks[1].attributes["condition"].value.replace(replacement, "var.available_zones")
    (tmp_path / "main.tf").write_text(
        'variable "availability_zone" { default = '
        + json.dumps(requested)
        + " }\n"
        + 'variable "available_zones" { default = '
        + json.dumps(available)
        + " }\n"
        + f"locals {{\n  enough = {sufficient}\n  allowed = {member}\n  selected = local.enough ? [{zone0}, {zone1}] : []\n}}\n",
        encoding="utf-8",
    )
    environment = {
        key: value
        for key, value in os.environ.items()
        if not key.upper().startswith(("TF_VAR_", "TF_CLI_ARGS"))
    }
    result = subprocess.run(
        [terraform, "console", "-no-color"],
        cwd=tmp_path,
        env=environment,
        input="jsonencode({selected=local.selected, allowed=local.allowed, enough=local.enough})\n",
        capture_output=True,
        text=True,
        timeout=15,
        check=False,
    )
    assert result.returncode == 0, result.stderr
    assert json.loads(json.loads(result.stdout.strip())) == {
        "selected": selected,
        "allowed": allowed,
        "enough": enough,
    }
