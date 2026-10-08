import itertools

import hcl2
import pytest
from fastapi.testclient import TestClient

from terraforma.generator import WizardConfig
from terraforma.project import ProjectSpecification, compile_project, input_contract
from terraforma.web import create_app


def specification(public=False, encryption=True, **inputs):
    return ProjectSpecification(
        recipe=WizardConfig(
            provider="gcp",
            project_name="windows-gcp",
            architecture_type="windows_virtual_machine",
            is_public=public,
            enable_encryption=encryption,
        ),
        inputs={"gcp_project_id": "example-project", "allowed_cidr": "203.0.113.8/32", **inputs},
    )


@pytest.mark.parametrize(
    "public,encryption,data_disk,secure_boot", list(itertools.product([False, True], repeat=4))
)
def test_gcp_windows_restricts_access_and_preserves_boot_and_activation(
    public, encryption, data_disk, secure_boot
):
    spec = specification(
        public,
        encryption,
        enable_data_disk=data_disk,
        enable_secure_boot=secure_boot,
        windows_username="operations",
    )
    result = compile_project(spec)
    files = result["files"]
    main = hcl2.loads(files["main.tf"])
    resources = {}
    for entry in main["resource"]:
        for kind, values in entry.items():
            resources.setdefault(kind, {}).update(values)
    ingress = resources['"google_compute_firewall"']['"this"']
    assert ingress["source_ranges"] == (
        '${var.admin_access_method == "iap_tunnel" ? ["35.235.240.0/20"] : [var.allowed_cidr]}'
    )
    assert ingress["allow"][0]["ports"] == ['"3389"']
    activation = resources['"google_compute_firewall"']['"windows_activation"']
    assert activation["direction"] == '"EGRESS"'
    assert activation["destination_ranges"] == ['"35.190.247.13/32"']
    assert activation["allow"][0]["ports"] == ['"1688"']
    route = resources['"google_compute_route"']['"windows_activation"']
    assert route["next_hop_gateway"] == '"default-internet-gateway"'
    assert route["dest_range"] == '"35.190.247.13/32"'
    assert resources['"google_compute_subnetwork"']['"this"']["private_ip_google_access"] is True
    instance = resources['"google_compute_instance"']['"this"']
    assert '"serial-port-enable" = "FALSE"' in instance["metadata"]
    assert 'var.enable_initialization ? {"windows-startup-script-ps1"' in instance["metadata"]
    assert "metadata_startup_script" not in instance
    assert instance["allow_stopping_for_update"] is False
    assert bool(instance["network_interface"][0].get("access_config")) is public
    shielded = instance["shielded_instance_config"][0]
    assert shielded["enable_vtpm"] is True
    assert shielded["enable_integrity_monitoring"] is True
    assert shielded["enable_secure_boot"] == "${var.enable_secure_boot}"
    assert 'variable "windows_username"' in files["variables.tf"]
    assert "var.windows_username" in files["outputs.tf"]
    assert "windows-cloud/windows-2022" in files["main.tf"]
    assert "ubuntu-os-cloud" not in files["main.tf"]
    assert "debian-cloud" not in files["main.tf"]
    assert result["specification"]["secret_references"] == {}
    assert not any(item["sensitive"] for item in result["input_contract"])
    assert not any(
        item["name"] in {"password", "ssh_public_key"} for item in result["input_contract"]
    )
    assert not any("OS Login" in item for item in result["capabilities"]["fixed_choices"])


@pytest.mark.parametrize(
    "username",
    [
        "Administrator",
        "administrator",
        "guest",
        "admin",
        "ab",
        "1user",
        "user name",
        "user/../other",
        "a" * 21,
    ],
)
def test_gcp_windows_rejects_invalid_user_references(username):
    with pytest.raises(ValueError):
        compile_project(specification(windows_username=username))


@pytest.mark.parametrize(
    "name,value",
    [
        ("image_version", "windows-server-2019-dc-v20261001"),
        ("image_version", "ubuntu-2404-noble-v20261001"),
        ("boot_disk_size_gb", 63),
        ("boot_disk_size_gb", 2049),
        ("private_ip_address", "10.0.1.0"),
        ("zone", "europe-west1-b"),
        ("ssh_public_key", "key"),
        ("windows_password", "private-marker"),
    ],
)
def test_gcp_windows_rejects_unsupported_or_incompatible_answers(name, value):
    with pytest.raises(ValueError):
        compile_project(specification(**{name: value}))


def test_gcp_windows_defaults_and_api_guidance():
    spec = specification()
    contract = {item["name"]: item for item in input_contract(spec.recipe)}
    assert contract["boot_disk_size_gb"]["default"] == 64
    assert contract["machine_type"]["default"] == "e2-standard-2"
    assert contract["image_version"]["choices"] is None
    assert contract["image_version"]["default"] == "latest"
    assert "BitLocker" in contract["enable_secure_boot"]["description"]
    with TestClient(create_app(), base_url="http://127.0.0.1") as client:
        headers = {"X-TerraForma-Token": client.get("/api/session").json()["token"]}
        result = client.post("/api/generate", headers=headers, json=spec.model_dump())
        assert result.status_code == 200, result.text
        assert result.json()["guide"]["route"][-1] == "Windows VM"
        assert "Google Cloud" in str(result.json()["guide"])
        assert "EC2" not in str(result.json()["guide"])
        assert "OS Login" not in str(result.json()["notes"])
        assert any("does not create" in item for item in result.json()["notes"])


def test_gcp_windows_terminal_resolves_non_secret_questions(monkeypatch):
    from unittest.mock import Mock

    from terraforma.cli import collect_recipe_inputs

    def prompt(message, **options):
        answer = (
            "example-project"
            if message.startswith("Google Cloud project ID")
            else options.get("default")
        )
        if options.get("choices") and answer is None:
            answer = options["choices"][0]
        return Mock(ask=lambda: answer)

    for kind in ("text", "select", "confirm"):
        monkeypatch.setattr(f"terraforma.cli.questionary.{kind}", prompt)
    spec = collect_recipe_inputs(specification().recipe)
    result = compile_project(spec)
    assert spec.inputs["windows_username"] == "terraforma"
    assert spec.inputs["boot_disk_size_gb"] == 64
    assert spec.secret_references == {}
    assert "var.windows_username" in result["files"]["outputs.tf"]


def test_gcp_windows_export_import_keeps_external_credential_reference():
    import io
    import json
    import zipfile

    spec = specification(
        windows_username="operations", private_ip_address="10.0.1.2", enable_data_disk=True
    )
    with TestClient(create_app(), base_url="http://127.0.0.1") as client:
        headers = {"X-TerraForma-Token": client.get("/api/session").json()["token"]}
        exported = client.post("/api/download", headers=headers, json=spec.model_dump())
        assert exported.status_code == 200
        with zipfile.ZipFile(io.BytesIO(exported.content)) as archive:
            manifest = json.loads(archive.read("terraforma.project.json"))
        restored = ProjectSpecification.model_validate(manifest)
        assert restored.inputs == spec.inputs
        assert restored.secret_references == {}
        assert compile_project(restored)["files"] == compile_project(spec)["files"]
