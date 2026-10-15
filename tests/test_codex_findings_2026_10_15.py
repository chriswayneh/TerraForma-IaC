"""Regression tests for the 2026-10-15 Codex review findings."""

import json
import re
from datetime import UTC, datetime

import pytest

from terraforma.ai_engine import AIDiagnosticsEngine, redact_sensitive_text
from terraforma.configuration import WizardConfig
from terraforma.image_metadata import deprecation_acceptable
from terraforma.preflight import machine_report
from terraforma.terragrunt import terragrunt_artifacts
from terraforma.web import generate_project
from tests.test_aws_placement import specification


def resource_text(provider, architecture, public, kind, name):
    config = WizardConfig(
        provider=provider,
        project_name="rv-findings",
        architecture_type=architecture,
        is_public=public,
        enable_encryption=True,
    )
    text = generate_project(config)["files"]["main.tf"]
    start = text.index(f'resource "{kind}" "{name}" {{')
    return text[start : text.index("\n}\n", start)]


def depends_on(text):
    match = re.search(r"depends_on\s*=\s*\[([^\]]*)\]", text)
    return [item.strip() for item in match.group(1).split(",") if item.strip()] if match else []


# Finding 1: Terragrunt state must not live in the content-addressed cache directory.
def test_terragrunt_state_is_pinned_to_the_unit_directory():
    files = terragrunt_artifacts({"dev": specification(False)})
    unit = files["units/dev/terragrunt.hcl"]
    assert 'backend "local"' in unit
    assert 'path = "${get_terragrunt_dir()}/terraform.tfstate"' in unit
    assert ".terragrunt-cache" not in unit
    assert json.loads(files["terraforma.units.json"])["state"] == "local-per-unit-directory"


def test_recipe_change_moves_module_but_not_state_path():
    before = terragrunt_artifacts({"dev": specification(False, instance_type="t3.micro")})
    after = terragrunt_artifacts({"dev": specification(True, instance_type="t3.micro")})
    modules = lambda files: {n.split("/")[1] for n in files if n.startswith("modules/")}
    assert modules(before) != modules(after)
    state = lambda files: [
        line for line in files["units/dev/terragrunt.hcl"].splitlines() if "tfstate" in line
    ]
    assert state(before) == state(after) and state(before)


# Finding 2: quoted (JSON) keys must be redacted before reaching the AI payload.
@pytest.mark.parametrize(
    "text",
    [
        json.dumps({"db": {"password": "Sup3rS3cretValue!"}}),
        json.dumps({"api_key": "abcd1234efgh"}, indent=2),
        '{"client_secret":"Sup3rS3cretValue!"}',
        json.dumps({"admin_password": 'Sup3r"S3cretValue!'}),
        "{'token': 'Sup3rS3cretValue!'}",
    ],
)
def test_json_secret_values_are_redacted(text):
    redacted = redact_sensitive_text(text)
    assert "Sup3r" not in redacted and "abcd1234efgh" not in redacted
    assert "[REDACTED]" in redacted


def test_json_secret_never_reaches_ai_payload():
    engine = AIDiagnosticsEngine(api_key="sk-test-key-not-real-000000")
    payload = engine._payload(json.dumps({"password": "Sup3rS3cretValue!"}), "")
    assert "Sup3rS3cretValue!" not in json.dumps(payload)


def test_non_secret_json_is_untouched():
    text = json.dumps({"instance_type": "t3.micro", "region": "us-east-1"})
    assert redact_sensitive_text(text) == text


# Finding 3: the MIG's instance template must be created before the old one is destroyed.
def test_gcp_instance_template_creates_before_destroy():
    template = resource_text(
        "gcp", "load_balanced_tier", True, "google_compute_instance_template", "this"
    )
    lifecycle = template[template.index("lifecycle {") :]
    assert re.search(r"create_before_destroy\s*=\s*true", lifecycle)
    assert "precondition {" in lifecycle


# Finding 4: only a past AWS DeprecationTime disqualifies an image.
@pytest.mark.parametrize(
    "value,expected",
    [
        (None, True),
        ("2099-01-01T00:00:00Z", True),
        ("2020-01-01T00:00:00Z", False),
        ("2020-01-01T00:00:00.000Z", False),
        ("not-a-date", None),
    ],
)
def test_aws_deprecation_time_compares_to_now(value, expected):
    now = datetime(2026, 10, 15, tzinfo=UTC)
    assert deprecation_acceptable(value, now) is expected


# Finding 5: Azure restrictions must match the selected location and zone.
def azure_machine(restrictions):
    return [
        {
            "name": "Standard_B2s",
            "resourceType": "virtualMachines",
            "locations": ["eastus"],
            "locationInfo": [{"location": "eastus", "zones": ["1", "2", "3"]}],
            "capabilities": [{"name": "CpuArchitectureType", "value": "x64"}],
            "restrictions": restrictions,
        }
    ]


def zone_restriction(location, zones):
    return {
        "type": "Zone",
        "values": [location],
        "restrictionInfo": {"locations": [location], "zones": zones},
        "reasonCode": "NotAvailableForSubscription",
    }


@pytest.mark.parametrize(
    "restrictions,zone,expected",
    [
        ([zone_restriction("westus2", ["1"])], None, False),
        ([zone_restriction("eastus", ["1"])], None, False),
        ([zone_restriction("eastus", ["1"])], "2", False),
        ([zone_restriction("eastus", ["1"])], "1", True),
        (
            [
                {
                    "type": "Location",
                    "values": ["eastus"],
                    "restrictionInfo": {"locations": ["eastus"]},
                }
            ],
            None,
            True,
        ),
        (
            [
                {
                    "type": "Location",
                    "values": ["westus"],
                    "restrictionInfo": {"locations": ["westus"]},
                }
            ],
            None,
            False,
        ),
        ([{"type": "Zone"}], None, True),
    ],
)
def test_azure_restrictions_match_selected_placement(restrictions, zone, expected):
    report = machine_report(
        "azure", azure_machine(restrictions), "Standard_B2s", "eastus", availability_zone=zone
    )
    assert (report["status"] == "restricted") is expected


# Finding 6: public AWS instances wait for the public subnet's internet route.
@pytest.mark.parametrize("architecture", ["single_web_server", "virtual_machine"])
def test_public_aws_instance_waits_for_public_route(architecture):
    instance = resource_text("aws", architecture, True, "aws_instance", "web")
    assert depends_on(instance) == ["aws_route_table_association.public"]


def test_private_aws_instance_still_waits_for_private_route():
    instance = resource_text("aws", "single_web_server", False, "aws_instance", "web")
    assert depends_on(instance) == ["aws_route_table_association.private"]
