import pytest

from terraforma.catalog import recipe_capabilities
from terraforma.generator import TerraformGenerator, WizardConfig


@pytest.mark.parametrize("workload", ["virtual_machine", "single_web_server", "load_balanced_tier"])
@pytest.mark.parametrize("public", [False, True])
def test_gcp_compute_explicitly_disables_interactive_serial_access(workload, public):
    recipe = WizardConfig(
        provider="gcp", project_name="serial-test", architecture_type=workload, is_public=public
    )
    generator = TerraformGenerator(recipe)
    generator.generate()
    expected = (
        "google_compute_instance_template"
        if workload == "load_balanced_tier"
        else "google_compute_instance"
    )
    resource = next(
        item for item in generator.main if item.kind == "resource" and item.labels[0] == expected
    )
    assert resource.attributes["metadata"]["serial-port-enable"] == "FALSE"
    if workload == "virtual_machine":
        assert resource.attributes["metadata"]["enable-oslogin"] == "TRUE"
        assert resource.attributes["metadata"]["block-project-ssh-keys"] == "TRUE"
        assert (
            resource.attributes["metadata_startup_script"].value
            == "var.enable_initialization ? var.initialization_script : null"
        )
    else:
        assert "nginx" in resource.attributes["metadata_startup_script"]
    capabilities = recipe_capabilities(recipe)
    assert any("serial console" in item for item in capabilities["fixed_choices"])


@pytest.mark.parametrize("provider", ["aws", "azure"])
def test_serial_console_guidance_does_not_cross_provider_boundaries(provider):
    capabilities = recipe_capabilities(
        WizardConfig(
            provider=provider, project_name="serial-test", architecture_type="virtual_machine"
        )
    )
    assert not any(
        "serial console" in item or "Google OS Login" in item
        for item in capabilities["fixed_choices"]
    )
