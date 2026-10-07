import io
import zipfile

import pytest
from fastapi.testclient import TestClient

from terraforma.generator import WizardConfig
from terraforma.project import compile_project, input_contract
from terraforma.web import create_app
from tests.test_private_ip import specification


@pytest.mark.parametrize("prefix", ["boot_disk", "data_disk"])
@pytest.mark.parametrize(
    "size,iops,throughput,valid",
    [
        (32, 3000, 125, True),
        (32, 16000, 1000, True),
        (20, 10000, 1000, True),
        (20, 10001, 1000, False),
        (32, 3000, 750, True),
        (32, 3000, 751, False),
        (32, 2999, 125, False),
        (32, 16001, 125, False),
        (32, 3000, 124, False),
        (160, 80000, 2000, True),
        (160, 80001, 2000, False),
        (159, 80000, 2000, False),
        (32, 8000, 2000, True),
        (32, 7999, 2000, False),
        (160, 80000, 2001, False),
        (32, 16000, 1001, True),
    ],
)
def test_gp3_limits_and_performance_ratios(prefix, size, iops, throughput, valid):
    spec = specification("aws")
    spec.inputs.update(enable_data_disk=True)
    spec.inputs.update(
        {f"{prefix}_size_gb": size, f"{prefix}_iops": iops, f"{prefix}_throughput": throughput}
    )
    if prefix == "data_disk" and size < 32:
        valid = False
    if valid:
        result = compile_project(spec)
        assert (
            f'var.{prefix}_type == "gp3" ? var.{prefix}_iops : null' in result["files"]["main.tf"]
        )
        assert "throughput no greater than one quarter" in result["files"]["main.tf"]
    else:
        with pytest.raises(ValueError):
            compile_project(spec)


@pytest.mark.parametrize("prefix", ["boot_disk", "data_disk"])
@pytest.mark.parametrize(
    "suffix,value", [("iops", 3000.0), ("iops", "3000"), ("throughput", True), ("throughput", None)]
)
def test_gp3_requires_whole_integer_answers(prefix, suffix, value):
    spec = specification("aws")
    spec.inputs[f"{prefix}_{suffix}"] = value
    with pytest.raises(ValueError):
        compile_project(spec)


@pytest.mark.parametrize("prefix", ["boot_disk", "data_disk"])
def test_gp2_rejects_custom_gp3_answers_and_hides_questions(prefix):
    spec = specification("aws")
    spec.inputs.update(enable_data_disk=True)
    spec.inputs[f"{prefix}_type"] = "gp2"
    result = compile_project(spec)
    assert not any(
        item["name"].startswith(prefix) and item["name"].endswith(("iops", "throughput"))
        for item in result["choice_summary"]
    )
    spec.inputs[f"{prefix}_iops"] = 4000
    with pytest.raises(ValueError, match="enabled gp3"):
        compile_project(spec)


def test_disabled_data_disk_rejects_custom_performance():
    spec = specification("aws")
    spec.inputs["data_disk_throughput"] = 250
    with pytest.raises(ValueError, match="enabled gp3"):
        compile_project(spec)


def test_gp3_defaults_and_visibility_conditions():
    contract = input_contract(specification("aws").recipe)
    questions = {item["name"]: item for item in contract}
    assert questions["boot_disk_iops"]["default"] == 3000
    assert questions["boot_disk_throughput"]["default"] == 125
    assert questions["boot_disk_iops"]["visible_when"] == {"boot_disk_type": "gp3"}
    assert questions["data_disk_throughput"]["visible_when"] == {
        "enable_data_disk": True,
        "data_disk_type": "gp3",
    }
    assert "Outposts is unsupported" in questions["boot_disk_iops"]["description"]
    assert questions["boot_disk_iops"]["maximum"] == 80000
    assert questions["boot_disk_throughput"]["maximum"] == 2000


@pytest.mark.parametrize(
    "provider,workload",
    [
        ("aws", "single_web_server"),
        ("aws", "load_balanced_tier"),
        ("azure", "virtual_machine"),
        ("gcp", "virtual_machine"),
    ],
)
def test_gp3_tuning_scope(provider, workload):
    recipe = WizardConfig(provider=provider, project_name="disk-test", architecture_type=workload)
    assert not any(
        item["name"].endswith(("_iops", "_throughput")) for item in input_contract(recipe)
    )


def test_gp3_export_and_import_preserve_requested_values():
    spec = specification("aws")
    spec.inputs.update(
        enable_data_disk=True,
        boot_disk_iops=6000,
        boot_disk_throughput=1000,
        data_disk_iops=12000,
        data_disk_throughput=1000,
    )
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
            assert imported.json()["specification"]["inputs"]["data_disk_iops"] == 12000
            assert imported.json()["files"]["variables.tf"] == archive.read("variables.tf").decode()


@pytest.mark.parametrize("windows", [False, True])
def test_expanded_performance_api_round_trip(windows):
    from tests.test_aws_placement import specification as vm_specification

    spec = vm_specification(
        windows,
        boot_disk_size_gb=160,
        boot_disk_iops=80000,
        boot_disk_throughput=2000,
        enable_data_disk=True,
        data_disk_size_gb=160,
        data_disk_iops=80000,
        data_disk_throughput=2000,
    )
    with TestClient(create_app(), base_url="http://127.0.0.1") as client:
        headers = {"X-TerraForma-Token": client.get("/api/session").json()["token"]}
        generated = client.post("/api/generate", headers=headers, json=spec.model_dump())
        imported = client.post("/api/projects/import", headers=headers, json=spec.model_dump())
    assert generated.status_code == imported.status_code == 200
    assert imported.json()["files"] == generated.json()["files"]
    assert imported.json()["specification"]["inputs"] == spec.inputs
