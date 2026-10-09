import hcl2
import pytest

from terraforma.generator import TerraformGenerator, WizardConfig


@pytest.mark.parametrize("public", [False, True])
def test_static_site_blob_uses_container_id_not_deprecated_names(public):
    files = TerraformGenerator(
        WizardConfig(
            provider="azure",
            project_name="static-test",
            architecture_type="static_site",
            is_public=public,
        )
    ).generate()
    main = hcl2.loads(files["main.tf"])
    blob = next(
        entry['"azurerm_storage_blob"']['"this"']
        for entry in main["resource"]
        if '"azurerm_storage_blob"' in entry
    )
    assert "storage_container_name" not in blob
    assert "storage_account_name" not in blob
    expected = (
        # Resource Manager container ID, the format AzureRM's ParseStorageContainerID expects.
        '"${azurerm_storage_account.this.id}/blobServices/default/containers/$web"'
        if public
        else "${azurerm_storage_container.this.id}"
    )
    assert blob["storage_container_id"] == expected
    assert '"version" = "~> 4.77"' in files["main.tf"]
