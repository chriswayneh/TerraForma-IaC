import io
import itertools
import zipfile

import hcl2
import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

from terraforma.generator import TerraformGenerator, WizardConfig
from terraforma.project import ProjectSpecification, compile_project, input_contract
from terraforma.web import create_app
from tests.test_project_keys import public_key, rsa_integer
from tests.test_virtual_machine import KEY

RSA_KEY = public_key("ssh-rsa", [rsa_integer(65537), rsa_integer((1 << 2047) + 1)])


def specification(public=False, encryption=True, **inputs):
    return ProjectSpecification(
        recipe=WizardConfig(
            provider="aws",
            project_name="windows-demo",
            architecture_type="windows_virtual_machine",
            is_public=public,
            enable_encryption=encryption,
        ),
        inputs={
            "aws_account_id": "123456789012",
            "ssh_public_key": RSA_KEY,
            "allowed_cidr": "203.0.113.8/32",
            **inputs,
        },
    )


@pytest.mark.parametrize(
    "public,encryption,data_disk", list(itertools.product([False, True], repeat=3))
)
def test_windows_access_image_and_no_secret_collection(public, encryption, data_disk):
    spec = specification(public, encryption, enable_data_disk=data_disk)
    result = compile_project(spec)
    files = result["files"]
    main = hcl2.loads(files["main.tf"])
    resources = {kind: values for entry in main["resource"] for kind, values in entry.items()}
    group = resources['"aws_security_group"']['"web"']
    assert group["ingress"][0]["from_port"] == 3389
    assert group["ingress"][0]["to_port"] == 3389
    assert group["ingress"][0]["cidr_blocks"] == ["${var.allowed_cidr}"]
    ami = main["data"][1]['"aws_ami"']['"windows"']
    assert [item.strip('"') for item in ami["owners"]] == ["amazon"]
    assert "Windows_Server-2022-English-Full-Base-*" in ami["filter"][0]["values"][0]
    assert "var.os_image" in ami["filter"][0]["values"][0]
    assert '"x86_64"' in files["main.tf"]
    instance = resources['"aws_instance"']['"web"']
    assert "user_data" not in instance
    assert "get_password_data" not in instance
    assert instance["associate_public_ip_address"] is public
    assert instance["metadata_options"][0]["http_tokens"] == '"required"'
    assert "disable_api_termination = var.protect_vm" in files["main.tf"]
    assert 'output "administrator_username"' in files["outputs.tf"]
    assert 'value = "Administrator"' in files["outputs.tf"]
    assert 'output "ssh_username"' not in files["outputs.tf"]
    assert not any(item["sensitive"] for item in result["input_contract"])
    assert result["specification"]["secret_references"] == {}
    assert all("password" not in item["name"] for item in result["input_contract"])
    assert any("RDP" in item for item in result["capabilities"]["fixed_choices"])
    assert not any("ec2-user" in item for item in result["capabilities"]["fixed_choices"])


@pytest.mark.parametrize("provider", ["azure", "gcp"])
def test_other_windows_providers_fail_closed(provider):
    with pytest.raises(ValidationError, match="AWS only"):
        WizardConfig(
            provider=provider,
            project_name="windows-demo",
            architecture_type="windows_virtual_machine",
        )


@pytest.mark.parametrize("key", [KEY, "ssh-rsa broken", "-----BEGIN PRIVATE KEY-----"])
def test_windows_rejects_ed25519_malformed_and_private_keys(key):
    with pytest.raises(ValueError, match="RSA public key for Windows"):
        compile_project(specification(ssh_public_key=key))


@pytest.mark.parametrize(
    "architectures,status",
    [(["x86_64"], "metadata_confirmed"), (["arm64"], "architecture_incompatible")],
)
def test_windows_machine_preflight_is_opt_in_and_checks_x86(monkeypatch, architectures, status):
    from terraforma.preflight import target_preflight
    from tests.test_machine_preflight import commands

    calls = commands(
        monkeypatch,
        "aws",
        machine={
            "InstanceTypes": [
                {
                    "InstanceType": "t3.small",
                    "ProcessorInfo": {"SupportedArchitectures": architectures},
                }
            ]
        },
    )
    spec = specification()
    target_preflight(spec)
    assert not calls
    result = target_preflight(spec, verify_target=True, verify_machine=True)
    assert len(calls) == 2
    assert result["machine_check"]["status"] == status
    assert "t3.small" in calls[1][0]


def test_windows_terminal_questions_resolve_required_inputs(monkeypatch, capsys):
    from unittest.mock import Mock

    from terraforma.cli import collect_recipe_inputs

    def prompt(message, **options):
        if "RSA only" in message:
            assert options["validate"](KEY) != True
            assert options["validate"](RSA_KEY) is True
            answer = RSA_KEY
        elif message.startswith("Target AWS account"):
            answer = "123456789012"
        else:
            answer = options.get("default")
        if options.get("choices") and answer is None:
            answer = options["choices"][0]
        return Mock(ask=lambda: answer)

    for kind in ("text", "select", "confirm"):
        monkeypatch.setattr(f"terraforma.cli.questionary.{kind}", prompt)
    collected = collect_recipe_inputs(specification().recipe)
    result = compile_project(collected)
    assert result["specification"]["inputs"]["boot_disk_size_gb"] == 50
    assert collected.secret_references == {}
    assert "RDP" in capsys.readouterr().out


@pytest.mark.parametrize("size", [20, 29, 2049, True])
def test_windows_boot_disk_minimum_and_maximum(size):
    with pytest.raises(ValueError):
        compile_project(specification(boot_disk_size_gb=size))


def test_windows_contract_defaults_and_exact_image_pin():
    spec = specification(image_version="ami-0123456789abcdef0")
    result = compile_project(spec)
    contract = {item["name"]: item for item in input_contract(spec.recipe)}
    assert contract["boot_disk_size_gb"]["default"] == 50
    assert contract["boot_disk_size_gb"]["minimum"] == 30
    assert contract["instance_type"]["default"] == "t3.small"
    assert contract["os_image"]["choices"] == ["windows-server-2022"]
    assert "RSA only" in contract["ssh_public_key"]["label"]
    assert "ami-0123456789abcdef0" in result["files"]["variables.tf"]
    assert "image-id" in result["files"]["main.tf"]


def test_windows_keeps_private_address_and_gp3_guards():
    with pytest.raises(ValueError, match="usable"):
        compile_project(specification(private_ip_address="10.0.0.4"))
    with pytest.raises(ValueError):
        compile_project(specification(boot_disk_size_gb=30, boot_disk_iops=16000))


def test_windows_api_generation_and_export():
    with TestClient(create_app(), base_url="http://127.0.0.1") as client:
        headers = {"X-TerraForma-Token": client.get("/api/session").json()["token"]}
        spec = specification(enable_data_disk=True)
        response = client.post("/api/generate", json=spec.model_dump(), headers=headers)
        assert response.status_code == 200, response.text
        assert response.json()["guide"]["route"][-1] == "Windows VM"
        assert any("RDP" in note for note in response.json()["notes"])
        exported = client.post("/api/download", json=spec.model_dump(), headers=headers)
        assert exported.status_code == 200
        with zipfile.ZipFile(io.BytesIO(exported.content)) as archive:
            assert "Administrator" in archive.read("outputs.tf").decode("utf-8")
            assert "get_password_data" not in archive.read("main.tf").decode("utf-8")


def test_windows_generator_declares_every_referenced_variable():
    import re

    files = TerraformGenerator(specification().recipe).generate()
    variables = hcl2.loads(files["variables.tf"])["variable"]
    declared = {name.strip('"') for item in variables for name in item}
    referenced = set(re.findall(r"\bvar\.([a-z_]+)", "\n".join(files.values())))
    assert declared == referenced
