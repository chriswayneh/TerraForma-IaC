import io
import ipaddress
import json
import shutil
import subprocess
import zipfile
from pathlib import Path
from unittest.mock import Mock

import pytest
from fastapi.testclient import TestClient

from terraforma.cli import collect_recipe_inputs
from terraforma.generator import WizardConfig
from terraforma.network_inputs import vm_subnet
from terraforma.project import ProjectSpecification, compile_project, input_contract
from terraforma.web import create_app
from tests.test_trusted_launch import KEY

NETWORK_CASES = [
    ("aws", True, "10.32.0.0/16", "10.32.0.0/24"),
    ("aws", False, "10.32.0.0/16", "10.32.10.0/24"),
    ("aws", True, "10.32.0.0/20", "10.32.0.0/28"),
    ("aws", False, "10.32.0.0/20", "10.32.0.160/28"),
    ("azure", True, "10.32.0.0/16", "10.32.1.0/24"),
    ("azure", False, "10.32.0.0/20", "10.32.0.16/28"),
    ("gcp", True, "10.32.0.0/16", "10.32.0.0/16"),
    ("gcp", False, "10.32.0.0/24", "10.32.0.0/24"),
    ("gcp", True, "10.32.0.0/28", "10.32.0.0/28"),
]


def specification(provider, public=False, network=None, address=""):
    inputs = {
        "aws": {"aws_account_id": "123456789012", "ssh_public_key": KEY},
        "azure": {"subscription_id": "12345678-1234-1234-1234-123456789abc", "ssh_public_key": KEY},
        "gcp": {"gcp_project_id": "example-project"},
    }[provider]
    inputs.update(allowed_cidr="10.0.0.0/16", private_ip_address=address)
    if network is not None:
        inputs["network_cidr"] = network
    return ProjectSpecification(
        recipe=WizardConfig(
            provider=provider,
            project_name="address-test",
            architecture_type="virtual_machine",
            is_public=public,
        ),
        inputs=inputs,
    )


@pytest.mark.parametrize("provider,public,network,subnet", NETWORK_CASES)
def test_private_ip_boundaries_match_generated_subnet(provider, public, network, subnet):
    expected = ipaddress.IPv4Network(subnet)
    assert vm_subnet(provider, network, public) == expected
    first, excluded_last = (2, 2) if provider == "gcp" else (4, 1)
    for offset in (first, expected.num_addresses - excluded_last - 1):
        compile_project(specification(provider, public, network, str(expected[offset])))
    for offset in (
        *range(first),
        *range(expected.num_addresses - excluded_last, expected.num_addresses),
    ):
        with pytest.raises(ValueError, match="provider-reserved"):
            compile_project(specification(provider, public, network, str(expected[offset])))
    with pytest.raises(ValueError, match="generated VM subnet"):
        compile_project(specification(provider, public, network, "192.168.250.10"))


@pytest.mark.parametrize("provider", ["aws", "azure", "gcp"])
@pytest.mark.parametrize(
    "address", ["", "auto", "10.0.0.256", "010.0.1.4", "::1", '${file("secret")}', 1, False, None]
)
def test_private_ip_format_and_blank_allocation(provider, address):
    if address == "" and type(address) is str:
        spec = specification(provider, address=address)
        result = compile_project(spec)
        assert (
            'var.private_ip_address == "" ? null : var.private_ip_address'
            in result["files"]["main.tf"]
        )
        question = next(
            item for item in input_contract(spec.recipe) if item["name"] == "private_ip_address"
        )
        assert question["kind"] == "optional_ipv4_address" and question["default"] == ""
        assert (
            next(item for item in result["choice_summary"] if item["name"] == "private_ip_address")[
                "value"
            ]
            == "Allocated by the cloud provider"
        )
    else:
        with pytest.raises(ValueError):
            compile_project(specification(provider, address=address))


@pytest.mark.parametrize(
    "provider,address", [("aws", "10.0.10.4"), ("azure", "10.0.1.4"), ("gcp", "10.0.1.2")]
)
def test_fixed_private_ip_export_import(provider, address):
    spec = specification(provider, address=address)
    with TestClient(create_app(), base_url="http://127.0.0.1") as client:
        headers = {"X-TerraForma-Token": client.get("/api/session").json()["token"]}
        response = client.post("/api/download", headers=headers, json=spec.model_dump())
        assert response.status_code == 200
        with zipfile.ZipFile(io.BytesIO(response.content)) as archive:
            imported = client.post(
                "/api/projects/import",
                headers=headers,
                content=archive.read("terraforma.project.json"),
            )
            assert imported.status_code == 200
            assert imported.json()["specification"]["inputs"]["private_ip_address"] == address
            assert imported.json()["files"]["variables.tf"] == archive.read("variables.tf").decode()


@pytest.mark.parametrize("provider", ["aws", "azure", "gcp"])
@pytest.mark.parametrize(
    "workload", ["single_web_server", "load_balanced_tier", "secure_database", "static_site"]
)
def test_private_ip_scope_excludes_multi_resource_recipes(provider, workload):
    recipe = WizardConfig(provider=provider, project_name="scope-test", architecture_type=workload)
    assert not any(item["name"] == "private_ip_address" for item in input_contract(recipe))


def browser_ranges(cases):
    executable = shutil.which("node")
    if executable is None:
        pytest.skip("Node.js is optional and required for browser address-hint checks.")
    script = Path(__file__).parents[1] / "src/terraforma/static/network.js"
    runner = (
        "const fs=require('fs'),vm=require('vm'); const context={}; "
        "vm.createContext(context); vm.runInContext(fs.readFileSync(process.argv[1],'utf8'),context); "
        "console.log(JSON.stringify(JSON.parse(process.argv[2]).map(args=>context.vmPrivateAddressRange(...args))));"
    )
    result = subprocess.run(
        [executable, "-e", runner, str(script), json.dumps(cases)],
        capture_output=True,
        text=True,
        timeout=10,
        check=False,
    )
    assert result.returncode == 0, result.stderr
    return json.loads(result.stdout)


def test_browser_range_hints_match_supported_subnets():
    reports = browser_ranges(
        [[provider, public, network] for provider, public, network, subnet in NETWORK_CASES]
    )
    for (provider, public, network, subnet), report in zip(NETWORK_CASES, reports, strict=True):
        selected = ipaddress.IPv4Network(subnet)
        first, excluded_last = (2, 2) if provider == "gcp" else (4, 1)
        assert report == {
            "subnet": subnet,
            "first": str(selected[first]),
            "last": str(selected[selected.num_addresses - excluded_last - 1]),
        }


def test_browser_range_hints_reject_invalid_or_unsupported_networks():
    cases = [
        ["azure", False, value]
        for value in [
            "",
            "10.0.0.1/16",
            "010.0.0.0/16",
            "10.0.0.0/21",
            "0.0.0.0/16",
            "172.32.0.0/16",
            "10.0.0.0/016",
            "192.168.256.0/16",
            None,
        ]
    ]
    cases.extend([["unknown", False, "10.0.0.0/16"], ["aws", "false", "10.0.0.0/16"]])
    assert browser_ranges(cases) == [None] * len(cases)


@pytest.mark.parametrize(
    "provider,address,range_text",
    [
        ("aws", "10.0.10.4", "10.0.10.4 through 10.0.10.254 in 10.0.10.0/24"),
        ("azure", "10.0.1.4", "10.0.1.4 through 10.0.1.254 in 10.0.1.0/24"),
        ("gcp", "10.0.1.2", "10.0.1.2 through 10.0.1.253 in 10.0.1.0/24"),
    ],
)
def test_terminal_shows_range_and_rejects_wrong_subnet_during_question(
    monkeypatch, capsys, provider, address, range_text
):
    def prompt(message, **options):
        required = {
            "Target AWS account ID:": "123456789012",
            "Azure subscription ID:": "12345678-1234-1234-1234-123456789abc",
            "Google Cloud project ID:": "example-project",
            "Administrator SSH public key (Ed25519 or RSA):": KEY,
        }
        if message == "Private IPv4 address (optional):":
            assert options["validate"]("") is True
            assert options["validate"](address) is True
            assert options["validate"]("192.168.250.10") is not True
            answer = address
        else:
            answer = required.get(message, options.get("default"))
        return Mock(ask=lambda: answer)

    for kind in ("text", "select", "confirm"):
        monkeypatch.setattr(f"terraforma.cli.questionary.{kind}", prompt)
    result = collect_recipe_inputs(specification(provider).recipe)
    compile_project(result)
    assert result.inputs["private_ip_address"] == address
    assert range_text in capsys.readouterr().out
