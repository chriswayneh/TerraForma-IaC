import shutil
import subprocess

import pytest

from terraforma.hcl import value_hcl
from terraforma.project import compile_project
from tests.test_generator import assert_native_files
from tests.test_initialization import initialized_spec

pytest_plugins = ["tests.test_generator"]


@pytest.mark.parametrize("provider", ["aws", "azure", "gcp"])
@pytest.mark.parametrize("windows", [False, True])
def test_mocked_plans_include_only_requested_initialization(native_directories, provider, windows):
    directory = native_directories[provider]
    spec = initialized_spec(provider, windows)
    assert_native_files(directory, compile_project(spec)["files"])
    tests = directory / "initialization-tests"
    tests.mkdir(exist_ok=True)
    script = spec.inputs["initialization_script"]
    provider_name = "google" if provider == "gcp" else "azurerm" if provider == "azure" else "aws"
    mock_defaults = {
        "aws": """
  mock_data "aws_availability_zones" {
    defaults = { names = ["us-east-1a", "us-east-1b"] }
  }
  mock_data "aws_ami" { defaults = { id = "ami-0123456789abcdef0" } }
  mock_resource "aws_instance" { defaults = { user_data_base64 = "" } }
""",
        "azure": """
  mock_resource "azurerm_network_interface" {
    defaults = { id = "/subscriptions/00000000-0000-0000-0000-000000000001/resourceGroups/offline/providers/Microsoft.Network/networkInterfaces/offline" }
  }
  mock_resource "azurerm_windows_virtual_machine" {
    defaults = { id = "/subscriptions/00000000-0000-0000-0000-000000000001/resourceGroups/offline/providers/Microsoft.Compute/virtualMachines/offline" }
  }
""",
        "gcp": "",
    }[provider]
    if provider == "aws":
        payload = f"<powershell>\n{script}\n</powershell>" if windows else script
        enabled = f"base64decode(aws_instance.web[0].user_data_base64) == {value_hcl(payload)} && aws_instance.web[0].user_data_replace_on_change"
        disabled = 'aws_instance.web[0].user_data_base64 == ""'
    elif provider == "azure" and windows:
        enabled = 'length(azurerm_virtual_machine_extension.initialization) == 1 && strcontains(jsondecode(azurerm_virtual_machine_extension.initialization[0].protected_settings).commandToExecute, base64encode(var.initialization_script)) && !strcontains(jsondecode(azurerm_virtual_machine_extension.initialization[0].protected_settings).commandToExecute, "review-marker")'
        disabled = "length(azurerm_virtual_machine_extension.initialization) == 0"
    elif provider == "azure":
        enabled = (
            f"base64decode(azurerm_linux_virtual_machine.this.custom_data) == {value_hcl(script)}"
        )
        disabled = "azurerm_linux_virtual_machine.this.custom_data == null"
    elif windows:
        enabled = f'google_compute_instance.this.metadata["windows-startup-script-ps1"] == {value_hcl(script)} && google_compute_instance.this.metadata["serial-port-enable"] == "FALSE"'
        disabled = '!contains(keys(google_compute_instance.this.metadata), "windows-startup-script-ps1") && google_compute_instance.this.metadata["serial-port-enable"] == "FALSE"'
    else:
        enabled = f"google_compute_instance.this.metadata_startup_script == {value_hcl(script)}"
        disabled = "google_compute_instance.this.metadata_startup_script == null"
    password = (
        'variables { admin_password = "Offline-Test-Only-123!" }'
        if provider == "azure" and windows
        else ""
    )
    content = f'''
mock_provider "{provider_name}" {{
  alias = "offline"
  override_during = plan
  {mock_defaults}
}}
{password}
run "reviewed_script_present" {{
  command = plan
  providers = {{ {provider_name} = {provider_name}.offline }}
  assert {{
    condition = {enabled}
    error_message = "Reviewed payload must match its guest mechanism."
  }}
}}
run "disabled_script_absent" {{
  command = plan
  providers = {{ {provider_name} = {provider_name}.offline }}
  variables {{
    enable_initialization = false
    initialization_script = ""
    confirm_initialization_review = false
  }}
  assert {{
    condition = {disabled}
    error_message = "Disabled initialization must omit its payload or extension."
  }}
}}
'''
    (tests / "initialization.tftest.hcl").write_text(content, encoding="utf-8")
    result = subprocess.run(
        [shutil.which("terraform"), "test", "-test-directory=initialization-tests", "-no-color"],
        cwd=directory,
        capture_output=True,
        text=True,
        timeout=60,
        check=False,
    )
    assert result.returncode == 0, result.stdout + result.stderr
