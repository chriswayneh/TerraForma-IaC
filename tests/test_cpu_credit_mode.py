import itertools

import pytest
from fastapi.testclient import TestClient

from terraforma.generator import TerraformGenerator, WizardConfig
from terraforma.project import ProjectInputError, compile_project, input_contract
from terraforma.web import create_app
from tests.test_aws_placement import specification


@pytest.mark.parametrize(
    "windows,mode",
    list(itertools.product([False, True], ["provider_default", "standard", "unlimited"])),
)
def test_credit_choice_survives_generation_and_summary(windows, mode):
    project = specification(windows, cpu_credit_mode=mode)
    output = compile_project(project)
    definition = next(
        field for field in input_contract(project.recipe) if field["name"] == "cpu_credit_mode"
    )
    assert definition["label"] == "CPU credit mode"
    assert definition["choices"] == ["provider_default", "standard", "unlimited"]
    assert output["specification"]["inputs"]["cpu_credit_mode"] == mode
    assert f'default = "{mode}"' in output["files"]["variables.tf"]
    assert 'dynamic "credit_specification"' in output["files"]["main.tf"]
    assert (
        'var.cpu_credit_mode == "provider_default" ? [] : [var.cpu_credit_mode]'
        in output["files"]["main.tf"]
    )
    assert "cpu_credits = credit_specification.value" in output["files"]["main.tf"]
    assert "Explicit CPU credit modes are supported only" in output["files"]["main.tf"]


@pytest.mark.parametrize(
    "family,mode",
    list(itertools.product(["t2.micro", "t3.micro", "t3a.small"], ["standard", "unlimited"])),
)
def test_supported_burstable_families_accept_explicit_modes(family, mode):
    compile_project(specification(False, instance_type=family, cpu_credit_mode=mode))


@pytest.mark.parametrize(
    "family,mode",
    list(itertools.product(["m5.large", "t4g.small", "t3ax.large"], ["standard", "unlimited"])),
)
def test_other_families_reject_explicit_modes_before_generation(family, mode):
    with pytest.raises(ProjectInputError) as error:
        compile_project(specification(False, instance_type=family, cpu_credit_mode=mode))
    assert error.value.field == "cpu_credit_mode"


def test_default_keeps_credit_setting_unmanaged_for_non_burstable_instances():
    output = compile_project(specification(False, instance_type="m5.large"))
    choice = next(row for row in output["choice_summary"] if row["name"] == "cpu_credit_mode")
    assert choice["value"] == "Provider default (credit setting unmanaged)"
    assert choice["source"] == "default"


@pytest.mark.parametrize(
    "provider,workload",
    list(
        itertools.product(
            ["aws", "azure", "gcp"],
            ["single_web_server", "load_balanced_tier", "secure_database", "static_site"],
        )
    ),
)
def test_unrelated_recipes_have_no_credit_question_or_block(provider, workload):
    recipe = WizardConfig(provider=provider, project_name="credit-test", architecture_type=workload)
    assert all(field["name"] != "cpu_credit_mode" for field in input_contract(recipe))
    assert "credit_specification" not in TerraformGenerator(recipe).generate()["main.tf"]


def test_api_import_preserves_credit_answer_and_rejects_incompatible_size():
    project = specification(True, cpu_credit_mode="standard").model_dump()
    with TestClient(create_app(), base_url="http://127.0.0.1") as client:
        headers = {"X-TerraForma-Token": client.get("/api/session").json()["token"]}
        response = client.post("/api/projects/import", headers=headers, json=project)
        assert response.status_code == 200
        assert response.json()["specification"]["inputs"]["cpu_credit_mode"] == "standard"
        project["inputs"]["instance_type"] = "m5.large"
        response = client.post("/api/projects/compile", headers=headers, json=project)
        assert response.status_code == 422
