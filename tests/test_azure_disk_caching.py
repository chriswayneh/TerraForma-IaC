import pytest

from terraforma.generator import WizardConfig
from terraforma.project import ProjectSpecification, compile_project, input_contract
from tests.test_project_keys import public_key


def specification(windows, **inputs):
    return ProjectSpecification(
        recipe=WizardConfig(
            provider="azure",
            project_name="cache-test",
            architecture_type="windows_virtual_machine" if windows else "virtual_machine",
        ),
        inputs={
            "subscription_id": "00000000-0000-0000-0000-000000000001",
            **(
                {} if windows else {"ssh_public_key": public_key("ssh-ed25519", [bytes(range(32))])}
            ),
            **inputs,
        },
    )


@pytest.mark.parametrize("windows", [False, True])
@pytest.mark.parametrize("mode", ["None", "ReadOnly", "ReadWrite"])
def test_cache_choices_survive_generation_and_saved_inputs(windows, mode):
    result = compile_project(
        specification(
            windows, enable_data_disk=True, boot_disk_caching=mode, data_disk_caching=mode
        )
    )
    main = result["files"]["main.tf"]
    assert "caching = var.boot_disk_caching" in main
    assert "caching = var.data_disk_caching" in main
    assert result["specification"]["inputs"]["boot_disk_caching"] == mode
    assert result["specification"]["inputs"]["data_disk_caching"] == mode
    assert result["files"]["variables.tf"].count(f'default = "{mode}"') >= 2


@pytest.mark.parametrize("windows", [False, True])
def test_empty_data_disk_disables_remote_export_and_public_network_access(windows):
    result = compile_project(specification(windows, enable_data_disk=True))
    main = result["files"]["main.tf"]
    assert 'network_access_policy = "DenyAll"' in main
    assert "public_network_access_enabled = false" in main
    assert 'create_option = "Empty"' in main
    assert '"azurerm_virtual_machine_data_disk_attachment"' in main
    assert '"azurerm_private_endpoint"' not in main
    assert result["required_secret_environment_variables"] == (
        ["TF_VAR_admin_password"] if windows else []
    )


@pytest.mark.parametrize("name", ["boot_disk_caching", "data_disk_caching"])
@pytest.mark.parametrize("value", ["writeback", "readonly", True, 1])
def test_unknown_cache_modes_fail_closed(name, value):
    with pytest.raises(ValueError):
        compile_project(specification(True, enable_data_disk=True, **{name: value}))


def test_disabled_data_disk_rejects_a_hidden_cache_answer():
    with pytest.raises(ValueError):
        compile_project(specification(True, data_disk_caching="ReadOnly"))


def test_defaults_and_cache_boundary_guidance():
    contract = {item["name"]: item for item in input_contract(specification(True).recipe)}
    assert contract["boot_disk_caching"]["default"] == "ReadWrite"
    assert contract["data_disk_caching"]["default"] == "None"
    assert contract["data_disk_caching"]["visible_when"] == {"enable_data_disk": True}
    assert "acknowledge writes" in contract["data_disk_caching"]["description"]
