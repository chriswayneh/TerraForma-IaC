import shutil
import subprocess

import pytest

from terraforma.project import compile_project
from tests.test_custom_images import specification
from tests.test_generator import assert_native_files

pytest_plugins = ["tests.test_generator"]


@pytest.mark.parametrize("provider", ["aws", "azure", "gcp"])
@pytest.mark.parametrize("windows", [False, True])
def test_mocked_plans_enforce_outbound_port_profile(native_directories, provider, windows):
    directory = native_directories[provider]
    spec = specification(provider, windows=windows, custom=False, outbound_access="https_dns")
    assert_native_files(directory, compile_project(spec)["files"])
    tests = directory / "outbound-tests"
    tests.mkdir(exist_ok=True)
    provider_name = {"aws": "aws", "azure": "azurerm", "gcp": "google"}[provider]
    defaults = {
        "aws": 'mock_data "aws_availability_zones" { defaults = { names = ["us-east-1a", "us-east-1b"] } }\nmock_data "aws_ami" { defaults = { id = "ami-0123456789abcdef0" } }',
        "azure": 'mock_resource "azurerm_network_interface" { defaults = { id = "/subscriptions/00000000-0000-0000-0000-000000000001/resourceGroups/offline/providers/Microsoft.Network/networkInterfaces/offline" } }',
        "gcp": "",
    }[provider]
    if provider == "aws":
        restricted = 'length(aws_security_group.web[0].egress) == 3 && alltrue([for rule in aws_security_group.web[0].egress : toset(rule.cidr_blocks) == toset(["0.0.0.0/0"]) && rule.from_port == rule.to_port && ((rule.protocol == "tcp" && contains([53, 443], rule.from_port)) || (rule.protocol == "udp" && rule.from_port == 53))])'
        unrestricted = 'length(aws_security_group.web[0].egress) == 1 && alltrue([for rule in aws_security_group.web[0].egress : rule.protocol == "-1" && toset(rule.cidr_blocks) == toset(["0.0.0.0/0"])])'
    elif provider == "azure":
        count = 5 if windows else 4
        restricted = f'length([for rule in azurerm_network_security_group.this[0].security_rule : rule if rule.direction == "Outbound"]) == {count} && length([for rule in azurerm_network_security_group.this[0].security_rule : rule if rule.name == "DenyOtherEgress" && rule.access == "Deny" && rule.protocol == "*" && rule.destination_port_range == "*" && rule.priority == 2010]) == 1 && alltrue([for rule in azurerm_network_security_group.this[0].security_rule : rule.priority < 2010 && ((rule.protocol == "Tcp" && contains(["53", "443"], rule.destination_port_range)) || (rule.protocol == "Udp" && rule.destination_port_range == "53") || (rule.name == "AllowWindowsLicensing" && rule.protocol == "Tcp" && rule.destination_port_range == "1688" && rule.destination_address_prefix == "AzurePlatformLKM")) if rule.direction == "Outbound" && rule.access == "Allow"])'
        unrestricted = 'length([for rule in azurerm_network_security_group.this[0].security_rule : rule if rule.direction == "Outbound"]) == 0'
    else:
        restricted = 'length(google_compute_firewall.outbound_web_dns) == 1 && length(google_compute_firewall.outbound_deny_other) == 1 && google_compute_firewall.outbound_web_dns[0].priority == 1000 && google_compute_firewall.outbound_deny_other[0].priority == 1100 && toset(google_compute_firewall.outbound_web_dns[0].destination_ranges) == toset(["0.0.0.0/0"]) && toset(google_compute_firewall.outbound_web_dns[0].target_tags) == toset(["terraforma-web"]) && alltrue([for rule in google_compute_firewall.outbound_web_dns[0].allow : (rule.protocol == "tcp" && toset(rule.ports) == toset(["53", "443"])) || (rule.protocol == "udp" && toset(rule.ports) == toset(["53"]))]) && alltrue([for rule in google_compute_firewall.outbound_deny_other[0].deny : rule.protocol == "all"])'
        if windows:
            restricted += ' && google_compute_firewall.windows_activation[0].priority < google_compute_firewall.outbound_deny_other[0].priority && toset(google_compute_firewall.windows_activation[0].destination_ranges) == toset(["35.190.247.13/32"])'
        unrestricted = "length(google_compute_firewall.outbound_web_dns) == 0 && length(google_compute_firewall.outbound_deny_other) == 0"
    password = (
        'variables { admin_password = "Offline-Test-Only-123!" }'
        if provider == "azure" and windows
        else ""
    )
    content = f'''
mock_provider "{provider_name}" {{
  alias = "offline"
  override_during = plan
  {defaults}
}}
{password}
run "restricted_ports" {{
  command = plan
  providers = {{ {provider_name} = {provider_name}.offline }}
  assert {{
    condition = {restricted}
    error_message = "Restricted profile must declare only its ports, platform exception and ordered deny."
  }}
}}
run "unrestricted_default" {{
  command = plan
  providers = {{ {provider_name} = {provider_name}.offline }}
  variables {{ outbound_access = "unrestricted" }}
  assert {{
    condition = {unrestricted}
    error_message = "Default profile must preserve the prior outbound configuration."
  }}
}}
'''
    (tests / "outbound.tftest.hcl").write_text(content, encoding="utf-8")
    result = subprocess.run(
        [shutil.which("terraform"), "test", "-test-directory=outbound-tests", "-no-color"],
        cwd=directory,
        capture_output=True,
        text=True,
        timeout=60,
        check=False,
    )
    assert result.returncode == 0, result.stdout + result.stderr
