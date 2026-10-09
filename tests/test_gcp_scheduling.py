import itertools

import hcl2
import pytest
from fastapi.testclient import TestClient

from terraforma.generator import TerraformGenerator, WizardConfig
from terraforma.project import ProjectSpecification, compile_project, input_contract
from terraforma.web import create_app
from tests.hcl_text import unaligned


def specification(windows=False, **inputs):
    return ProjectSpecification(
        recipe=WizardConfig(
            provider="gcp",
            project_name="maintenance-demo",
            architecture_type="windows_virtual_machine" if windows else "virtual_machine",
        ),
        inputs={"gcp_project_id": "example-project", **inputs},
    )


@pytest.mark.parametrize(
    "windows,policy,restart",
    list(itertools.product([False, True], ["MIGRATE", "TERMINATE"], [False, True])),
)
def test_selected_scheduling_survives_api_import_and_binds_only_standard_vm(
    windows, policy, restart
):
    spec = specification(windows, host_maintenance_policy=policy, automatic_restart=restart)
    with TestClient(create_app(), base_url="http://127.0.0.1") as client:
        headers = {"X-TerraForma-Token": client.get("/api/session").json()["token"]}
        response = client.post("/api/generate", json=spec.model_dump(), headers=headers)
        assert response.status_code == 200, response.text
        result = response.json()
    restored = ProjectSpecification.model_validate(result["specification"])
    assert compile_project(restored)["files"] == result["files"]
    assert restored.inputs["host_maintenance_policy"] == policy
    assert restored.inputs["automatic_restart"] is restart
    main = hcl2.loads(result["files"]["main.tf"])
    vm = next(
        item['"google_compute_instance"']['"this"']
        for item in main["resource"]
        if '"google_compute_instance"' in item
    )
    scheduling = vm["scheduling"][0]
    assert scheduling["provisioning_model"] == '"STANDARD"'
    assert scheduling["preemptible"] is False
    assert scheduling["on_host_maintenance"] == "${var.host_maintenance_policy}"
    assert scheduling["automatic_restart"] == "${var.automatic_restart}"
    assert vm["allow_stopping_for_update"] is False
    assert f'default = "{policy}"' in unaligned(result["files"]["variables.tf"])
    assert f"default = {str(restart).lower()}" in unaligned(result["files"]["variables.tf"])


@pytest.mark.parametrize("windows", [False, True])
def test_old_manifest_defaults_to_standard_migration_and_restart(windows):
    definitions = {item["name"]: item for item in input_contract(specification(windows).recipe)}
    assert definitions["host_maintenance_policy"]["default"] == "MIGRATE"
    assert definitions["automatic_restart"]["default"] is True
    assert "guest patch schedules" in definitions["host_maintenance_policy"]["description"]
    assert "deliberately stopped by a user" in definitions["automatic_restart"]["description"]
    assert compile_project(specification(windows))["files"]["main.tf"]


@pytest.mark.parametrize(
    "name,value",
    [
        ("host_maintenance_policy", "migrate"),
        ("host_maintenance_policy", "SPOT"),
        ("host_maintenance_policy", True),
        ("automatic_restart", "false"),
        ("automatic_restart", 0),
    ],
)
def test_invalid_scheduling_choices_fail_closed(name, value):
    with pytest.raises(ValueError):
        compile_project(specification(**{name: value}))


@pytest.mark.parametrize("workload", ["single_web_server", "load_balanced_tier"])
def test_web_recipes_do_not_expose_standalone_scheduling(workload):
    config = WizardConfig(provider="gcp", project_name="example", architecture_type=workload)
    names = {item["name"] for item in input_contract(config)}
    assert not names & {"host_maintenance_policy", "automatic_restart"}
    assert "var.host_maintenance_policy" not in TerraformGenerator(config).generate()["main.tf"]
