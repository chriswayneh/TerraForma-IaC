import pytest

from terraforma.generator import TerraformGenerator, WizardConfig
from terraforma.hcl import value_hcl

TAGGABLE = {
    "azurerm_resource_group",
    "azurerm_virtual_network",
    "azurerm_network_security_group",
    "azurerm_public_ip",
    "azurerm_nat_gateway",
    "azurerm_lb",
    "azurerm_linux_virtual_machine_scale_set",
    "azurerm_network_interface",
    "azurerm_linux_virtual_machine",
    "azurerm_windows_virtual_machine",
    "azurerm_managed_disk",
    "azurerm_postgresql_flexible_server",
    "azurerm_storage_account",
    "azurerm_private_dns_zone",
    "azurerm_private_dns_zone_virtual_network_link",
}


@pytest.mark.parametrize(
    "workload",
    [
        "virtual_machine",
        "windows_virtual_machine",
        "single_web_server",
        "load_balanced_tier",
        "secure_database",
        "static_site",
    ],
)
@pytest.mark.parametrize("public", [False, True])
@pytest.mark.parametrize("encrypted", [False, True])
def test_environment_tags_cover_supported_azure_resources(workload, public, encrypted):
    generator = TerraformGenerator(
        WizardConfig(
            provider="azure",
            project_name="tag-test",
            architecture_type=workload,
            is_public=public,
            enable_encryption=encrypted,
        )
    )
    generator.generate()
    resources = [item for item in generator.main if item.kind == "resource"]
    assert any(
        item.labels[0] in TAGGABLE and item.labels[0] != "azurerm_resource_group"
        for item in resources
    )
    for resource in resources:
        if resource.labels[0] in TAGGABLE:
            tags = value_hcl(resource.attributes["tags"])
            assert '"Environment" = var.environment' in tags
            assert '"ManagedBy" = "TerraForma-IaC"' in tags
        else:
            assert "tags" not in resource.attributes
