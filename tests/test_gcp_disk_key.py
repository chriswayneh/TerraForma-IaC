import itertools

import hcl2
import pytest
from fastapi.testclient import TestClient

from terraforma.generator import WizardConfig
from terraforma.project import ProjectInputError, compile_project, input_contract
from terraforma.web import create_app
from tests.test_gcp_scheduling import specification

KEY = "projects/key-project/locations/us-central1/keyRings/storage/cryptoKeys/vm-disks"


@pytest.mark.parametrize(
    "windows,data_disk,enabled", list(itertools.product([False, True], repeat=3))
)
def test_key_scope_preserves_default_and_uses_external_reference(windows, data_disk, enabled):
    spec = specification(windows, use_customer_managed_disk_key=enabled, enable_data_disk=data_disk)
    if enabled:
        spec.inputs["disk_kms_key"] = KEY
    result = compile_project(spec)
    main = hcl2.loads(result["files"]["main.tf"])
    resources = {kind: values for item in main["resource"] for kind, values in item.items()}
    vm = resources['"google_compute_instance"']['"this"']
    assert (
        vm["boot_disk"][0]["kms_key_self_link"]
        == "${var.use_customer_managed_disk_key ? var.disk_kms_key : null}"
    )
    disk = resources['"google_compute_disk"']['"data"']
    assert (
        disk["dynamic"][0]['"disk_encryption_key"']["for_each"]
        == "${var.use_customer_managed_disk_key ? [1] : []}"
    )
    assert "google_kms_crypto_key" not in resources
    assert not any("iam" in kind for kind in resources)
    assert vm["shielded_instance_config"][0]["enable_vtpm"] is True
    assert "Supply an existing Cloud KMS CryptoKey reference" in result["files"]["main.tf"]
    assert f"default = {str(enabled).lower()}" in result["files"]["variables.tf"]


@pytest.mark.parametrize(
    "key",
    [
        "raw-key-material",
        "https://cloudkms.googleapis.com/v1/" + KEY,
        KEY + "/cryptoKeyVersions/1",
        KEY + "?token=secret",
        KEY.replace("vm-disks", '${file("secret")}'),
        "-----BEGIN PRIVATE KEY-----",
        "",
        KEY + "\n",
    ],
)
def test_malformed_or_raw_keys_fail_closed(key):
    with pytest.raises(ProjectInputError) as error:
        compile_project(specification(use_customer_managed_disk_key=True, disk_kms_key=key))
    assert error.value.field == "disk_kms_key"
    assert key not in str(error.value) if key else True


def test_enabled_mode_requires_key_and_disabled_mode_rejects_unused_reference():
    with pytest.raises(ProjectInputError) as missing:
        compile_project(specification(use_customer_managed_disk_key=True))
    assert missing.value.field == "disk_kms_key"
    with pytest.raises(ProjectInputError) as inactive:
        compile_project(specification(disk_kms_key=KEY))
    assert inactive.value.field == "disk_kms_key"


@pytest.mark.parametrize("location", ["us-central1", "global", "us"])
def test_supported_key_reference_shapes_do_not_assert_location_compatibility(location):
    compile_project(
        specification(
            use_customer_managed_disk_key=True, disk_kms_key=KEY.replace("us-central1", location)
        )
    )


@pytest.mark.parametrize(
    "provider,workload",
    [
        ("aws", "virtual_machine"),
        ("azure", "windows_virtual_machine"),
        ("gcp", "single_web_server"),
        ("gcp", "load_balanced_tier"),
    ],
)
def test_key_control_is_only_for_gcp_standalone(provider, workload):
    config = WizardConfig(provider=provider, project_name="key-scope", architecture_type=workload)
    assert "disk_kms_key" not in {item["name"] for item in input_contract(config)}


@pytest.mark.parametrize("windows", [False, True])
def test_api_import_preserves_key_reference_and_recovery_warning(windows):
    spec = specification(
        windows, use_customer_managed_disk_key=True, disk_kms_key=KEY, enable_data_disk=True
    )
    contract = {item["name"]: item for item in input_contract(spec.recipe)}
    assert contract["use_customer_managed_disk_key"]["default"] is False
    assert contract["disk_kms_key"]["visible_when"] == {"use_customer_managed_disk_key": True}
    with TestClient(create_app(), base_url="http://127.0.0.1") as client:
        headers = {"X-TerraForma-Token": client.get("/api/session").json()["token"]}
        generated = client.post("/api/generate", headers=headers, json=spec.model_dump())
        imported = client.post("/api/projects/import", headers=headers, json=spec.model_dump())
    assert generated.status_code == imported.status_code == 200
    assert imported.json()["files"] == generated.json()["files"]
    assert imported.json()["specification"]["inputs"]["disk_kms_key"] == KEY
    assert any(
        "Disk retention does not preserve key availability" in note
        for note in generated.json()["notes"]
    )
