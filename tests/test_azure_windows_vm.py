import io
import itertools
import json
import zipfile
from unittest.mock import Mock

import hcl2
import pytest
from fastapi.testclient import TestClient

from terraforma.generator import WizardConfig
from terraforma.project import ProjectSpecification, compile_project, input_contract
from terraforma.web import create_app


def specification(public=False, encryption=True, **inputs):
    return ProjectSpecification(
        recipe=WizardConfig(
            provider="azure",
            project_name="windows-azure",
            architecture_type="windows_virtual_machine",
            is_public=public,
            enable_encryption=encryption,
        ),
        inputs={
            "subscription_id": "00000000-0000-0000-0000-000000000001",
            "allowed_cidr": "203.0.113.8/32",
            **inputs,
        },
        secret_references={"admin_password": "TF_VAR_admin_password"},
    )


@pytest.mark.parametrize("public,encryption", list(itertools.product([False, True], repeat=2)))
def test_windows_resource_uses_external_password_and_restricted_rdp(public, encryption):
    result = compile_project(specification(public, encryption, enable_data_disk=True))
    files = result["files"]
    resources = {}
    for entry in hcl2.loads(files["main.tf"])["resource"]:
        for kind, values in entry.items():
            resources.setdefault(kind, {}).update(values)
    vm = resources['"azurerm_windows_virtual_machine"']['"this"']
    assert vm["admin_password"] == "${var.admin_password}"
    assert vm["computer_name"] == "${var.computer_name}"
    assert vm["license_type"] == "${var.license_type}"
    assert vm["automatic_updates_enabled"] is True
    assert vm["patch_mode"] == '"AutomaticByOS"'
    assert vm["provision_vm_agent"] is True
    assert vm["vtpm_enabled"] is True
    assert vm["secure_boot_enabled"] == "${var.enable_secure_boot}"
    assert vm["encryption_at_host_enabled"] is encryption
    assert "admin_ssh_key" not in vm
    assert "custom_data" not in vm
    assert "disable_password_authentication" not in vm
    assert '"azurerm_linux_virtual_machine"' not in resources
    assert '"azurerm_virtual_machine_data_disk_attachment"' in resources
    assert ('"web"' in resources['"azurerm_public_ip"']) is public
    assert '"egress"' in resources['"azurerm_public_ip"']
    image = vm["source_image_reference"][0]
    assert image["publisher"] == '"MicrosoftWindowsServer"'
    assert image["offer"] == '"WindowsServer"'
    assert "2022-datacenter-g2" in image["sku"]
    assert image["version"] == "${var.image_version}"
    rule = resources['"azurerm_network_security_group"']['"this"']["security_rule"][0]
    assert rule["destination_port_range"] == '"3389"'
    assert rule["source_address_prefix"] == "${var.allowed_cidr}"
    assert "DenyOtherInbound" in files["main.tf"]
    variables = {}
    for entry in hcl2.loads(files["variables.tf"])["variable"]:
        variables.update(entry)
    password = variables['"admin_password"']
    assert password["sensitive"] is True
    assert "default" not in password
    assert "admin_password" not in files["outputs.tf"]
    assert "ssh_public_key" not in files["variables.tf"]
    assert "Terraform state" in files["variables.tf"]


@pytest.mark.parametrize(
    "name,value",
    [
        ("admin_username", "administrator"),
        ("admin_username", "a" * 21),
        ("computer_name", "a" * 16),
        ("computer_name", "123"),
        ("computer_name", "host_01"),
        ("computer_name", "host-"),
        ("license_type", "Windows_Client"),
        ("boot_disk_size_gb", 127),
        ("boot_disk_size_gb", 2049),
        ("os_image", "ubuntu-24.04"),
        ("ssh_public_key", "unsupported-key"),
        ("admin_password", "private-marker"),
    ],
)
def test_windows_invalid_answers_and_inline_password_fail_closed(name, value):
    with pytest.raises(ValueError):
        compile_project(specification(**{name: value}))


def test_windows_contract_defaults_and_secret_boundary():
    contract = {item["name"]: item for item in input_contract(specification().recipe)}
    assert contract["vm_size"]["default"] == "Standard_D2s_v5"
    assert contract["boot_disk_size_gb"]["default"] == 128
    assert contract["computer_name"]["default"] == "terraforma"
    assert contract["license_type"]["choices"] == ["None", "Windows_Server"]
    assert contract["admin_password"]["kind"] == "external_secret"
    assert contract["admin_password"]["environment_variable"] == "TF_VAR_admin_password"
    assert "BitLocker" in contract["enable_secure_boot"]["description"]
    spec = specification()
    spec.secret_references["admin_password"] = "OTHER_SECRET"
    with pytest.raises(ValueError):
        compile_project(spec)


def test_windows_terminal_never_reads_password_value(monkeypatch):
    from terraforma.cli import collect_recipe_inputs

    monkeypatch.setenv("TF_VAR_admin_password", "private-marker-never-read")

    def prompt(message, **options):
        assert "password" not in message.lower()
        answer = (
            "00000000-0000-0000-0000-000000000001"
            if message.startswith("Azure subscription ID")
            else options.get("default")
        )
        if options.get("choices") and answer is None:
            answer = options["choices"][0]
        return Mock(ask=lambda: answer)

    for kind in ("text", "select", "confirm"):
        monkeypatch.setattr(f"terraforma.cli.questionary.{kind}", prompt)
    spec = collect_recipe_inputs(specification().recipe)
    assert spec.secret_references == {"admin_password": "TF_VAR_admin_password"}
    result = compile_project(spec)
    assert "private-marker-never-read" not in json.dumps(result)


def test_windows_api_and_zip_keep_only_external_reference(monkeypatch):
    monkeypatch.setenv("TF_VAR_admin_password", "private-marker-never-read")
    spec = specification(computer_name="operations", license_type="Windows_Server")
    with TestClient(create_app(), base_url="http://127.0.0.1") as client:
        headers = {"X-TerraForma-Token": client.get("/api/session").json()["token"]}
        generated = client.post("/api/generate", headers=headers, json=spec.model_dump())
        assert generated.status_code == 200, generated.text
        assert "Terraform state" in str(generated.json()["notes"])
        assert "private-marker-never-read" not in generated.text
        exported = client.post("/api/download", headers=headers, json=spec.model_dump())
        assert exported.status_code == 200, exported.text
        with zipfile.ZipFile(io.BytesIO(exported.content)) as archive:
            for name in archive.namelist():
                assert b"private-marker-never-read" not in archive.read(name)
            restored = ProjectSpecification.model_validate_json(
                archive.read("terraforma.project.json")
            )
        assert restored.secret_references == spec.secret_references
        assert compile_project(restored)["files"] == compile_project(spec)["files"]


@pytest.mark.parametrize(
    "generation,status",
    [
        ("V2", "metadata_confirmed"),
        ("V1", "boot_features_incompatible"),
        (None, "boot_features_unknown"),
    ],
)
def test_windows_size_preflight_checks_gen2_without_claiming_deployment(
    monkeypatch, generation, status
):
    import copy

    from terraforma.preflight import target_preflight
    from tests.test_machine_preflight import MACHINES, commands

    metadata = copy.deepcopy(MACHINES["azure"])
    metadata[0]["name"] = "Standard_D2s_v5"
    if generation:
        metadata[0]["capabilities"].append({"name": "HyperVGenerations", "value": generation})
    calls = commands(
        monkeypatch,
        "azure",
        metadata,
        target={"subscriptionId": specification().inputs["subscription_id"], "state": "Enabled"},
    )
    report = target_preflight(specification(), verify_target=True, verify_machine=True)
    assert len(calls) == 2
    assert report["machine_check"]["status"] == status
    assert report["approval_granted"] is False
    assert report["deployment_readiness_verified"] is False
