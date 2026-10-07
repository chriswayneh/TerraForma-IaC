import pytest

from terraforma.generator import TerraformGenerator, WizardConfig


@pytest.mark.parametrize(
    "provider,expression",
    [
        ("aws", "aws_instance.web[0].id"),
        ("azure", "azurerm_linux_virtual_machine.this.id"),
        ("gcp", "google_compute_instance.this.id"),
    ],
)
def test_standalone_vm_reference_outputs_are_provider_specific(provider, expression):
    generator = TerraformGenerator(
        WizardConfig(
            provider=provider, project_name="reference-test", architecture_type="virtual_machine"
        )
    )
    generator.generate()
    outputs = {item.labels[0]: item for item in generator.outputs}
    assert outputs["vm_id"].attributes["value"].value == expression
    assert {"vm_name", "vm_location", "vm_address"} <= outputs.keys()
    assert ("vm_resource_group" in outputs) == (provider == "azure")
    if provider == "aws":
        assert "not a unique" in outputs["vm_name"].attributes["description"]
    for name in ("vm_id", "vm_name", "vm_location"):
        assert not outputs[name].attributes.get("sensitive", False)


@pytest.mark.parametrize("provider", ["aws", "azure", "gcp"])
@pytest.mark.parametrize(
    "workload", ["single_web_server", "load_balanced_tier", "secure_database", "static_site"]
)
def test_single_vm_references_are_not_added_to_other_workloads(provider, workload):
    generator = TerraformGenerator(
        WizardConfig(provider=provider, project_name="reference-test", architecture_type=workload)
    )
    generator.generate()
    assert not {"vm_id", "vm_name", "vm_location", "vm_resource_group"} & {
        item.labels[0] for item in generator.outputs
    }
