import hcl2
import pytest

from terraforma.generator import TerraformGenerator, WizardConfig


@pytest.mark.parametrize("public", [False, True])
def test_azure_static_site_storage_account_sets_secure_options(public):
    files = TerraformGenerator(
        WizardConfig(
            provider="azure",
            project_name="static-test",
            architecture_type="static_site",
            is_public=public,
        )
    ).generate()
    parsed = hcl2.loads(files["main.tf"])
    account = next(
        entry['"azurerm_storage_account"']['"this"']
        for entry in parsed["resource"]
        if '"azurerm_storage_account"' in entry
    )
    assert account["min_tls_version"] == '"TLS1_2"'
    assert account["https_traffic_only_enabled"] is True
    assert account["allow_nested_items_to_be_public"] is public
    assert account["cross_tenant_replication_enabled"] is False
    assert account["local_user_enabled"] is False
    assert account["sftp_enabled"] is False
    properties = account["blob_properties"][0]
    assert properties["delete_retention_policy"][0]["days"] == 7
    assert properties["container_delete_retention_policy"][0]["days"] == 7
