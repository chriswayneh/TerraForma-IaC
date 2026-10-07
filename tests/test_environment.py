import pytest

from terraforma.generator import WizardConfig
from terraforma.project import ProjectSpecification, compile_project


@pytest.mark.parametrize("provider", ["aws", "azure", "gcp"])
@pytest.mark.parametrize(
    "workload", ["single_web_server", "load_balanced_tier", "secure_database", "static_site"]
)
def test_environment_answer_maps_to_generated_label_and_target(provider, workload):
    inputs = {"environment": "production"}
    if provider == "aws":
        inputs["aws_account_id"] = "123456789012"
    elif provider == "azure":
        inputs["subscription_id"] = "12345678-1234-1234-1234-123456789abc"
        if workload in {"single_web_server", "load_balanced_tier"}:
            inputs["ssh_public_key"] = (
                "ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAIAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA"
            )
    else:
        inputs["gcp_project_id"] = "example-project"
    result = compile_project(
        ProjectSpecification(
            recipe=WizardConfig(
                provider=provider, project_name="example", architecture_type=workload
            ),
            inputs=inputs,
        )
    )
    assert 'default = "production"' in result["files"]["variables.tf"]
    assert result["target"]["environment"] == "production"
    assert result["target"]["identity_verified"] is False
    label_key = "environment" if provider == "gcp" else "Environment"
    assert f'"{label_key}" = var.environment' in result["files"]["main.tf"]


@pytest.mark.parametrize(
    "value", ["Production", "two environments", "a", "-production", "prod;execute"]
)
def test_invalid_environment_labels_are_rejected(value):
    with pytest.raises(ValueError):
        compile_project(
            ProjectSpecification(
                recipe=WizardConfig(
                    provider="aws", project_name="example", architecture_type="static_site"
                ),
                inputs={"environment": value, "aws_account_id": "123456789012"},
            )
        )
