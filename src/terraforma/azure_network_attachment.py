from terraforma.hcl import block, ref

AZURE_SUBNET_PATTERN = r"/subscriptions/[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}/resourceGroups/[A-Za-z0-9](?:[A-Za-z0-9_.()-]{0,88}[A-Za-z0-9_])?/providers/Microsoft.Network/virtualNetworks/[A-Za-z0-9](?:[A-Za-z0-9_.-]{0,62}[A-Za-z0-9_])?/subnets/[A-Za-z0-9](?:[A-Za-z0-9_.-]{0,78}[A-Za-z0-9_])?"


def declare_azure_network_attachment(builder):
    builder.variable(
        "use_existing_network",
        "Attach this VM's new NIC to one existing IPv4-only Azure subnet in the selected subscription and VM region. The subnet must already have a reviewed NSG. Existing mode creates no VNet, subnet, NSG association or NAT infrastructure; inherited rules and egress remain separately managed. Public IP assignment remains separate. Use a separate project/state for independently managed infrastructure. Switching a deployed new-network project can delete its owned network/NSG/NAT, replace the VM and delete boot data; this toggle does not transfer state ownership.",
        False,
        type_name="bool",
    )
    builder.variable(
        "existing_subnetwork_resource",
        "Full existing subnet resource ID: /subscriptions/UUID/resourceGroups/GROUP/providers/Microsoft.Network/virtualNetworks/VNET/subnets/SUBNET. Use the selected subscription and VM region. Cross-subscription, IPv6/dual-stack, delegated subnets and subnets without an existing NSG are unsupported. Existence, effective policies and attachment permissions remain unverified during generation.",
        "",
        pattern=rf"^($|{AZURE_SUBNET_PATTERN})$",
        visible_when={"use_existing_network": True},
        required_when={"use_existing_network": True},
    )
    builder.variable(
        "existing_subnet_cidr",
        "Actual primary IPv4 range of the existing subnet. It is a declaration only; Terraform later checks the returned subnet prefixes. The recipe does not modify this range. Use one canonical RFC1918 range with a /16 through /28 prefix and review available IP capacity separately.",
        "10.0.0.0/24",
        network_policy="vm_network",
        prefix_minimum=16,
        prefix_maximum=28,
        visible_when={"use_existing_network": True},
        required_when={"use_existing_network": True},
    )
    builder.variable(
        "confirm_existing_network_review",
        "I have reviewed the existing subnet's CIDR, region, subscription, NSG and effective inherited rules, administrator path, routing and outbound connectivity, and confirmed that the subnet has no delegation. The supplied administrator CIDR does not create a rule in this mode. Delegations and connectivity are not checked by this declaration or the metadata checks; it does not approve deployment.",
        False,
        type_name="bool",
        visible_when={"use_existing_network": True},
    )


def azure_attachment_precondition():
    return block(
        "precondition",
        condition=ref(
            'var.use_existing_network ? (var.confirm_existing_network_review && var.network_cidr == "10.0.0.0/16" && '
            'try(lower(split("/", var.existing_subnetwork_resource)[2]) == lower(var.subscription_id), false)) : '
            '(var.existing_subnetwork_resource == "" && !var.confirm_existing_network_review && var.existing_subnet_cidr == "10.0.0.0/24")'
        ),
        error_message="Existing Azure subnet mode requires a reviewed reference in the selected subscription and no conflicting new-network range. Clear inactive references, declarations and existing CIDR changes in new-network mode.",
    )


def add_azure_attachment_data(builder):
    group = ref('try(split("/", var.existing_subnetwork_resource)[4], "")')
    vnet = ref('try(split("/", var.existing_subnetwork_resource)[8], "")')
    builder.main.append(
        block(
            "data",
            "azurerm_virtual_network",
            "existing",
            count=ref("var.use_existing_network ? 1 : 0"),
            name=vnet,
            resource_group_name=group,
            children=[
                block(
                    "lifecycle",
                    children=[
                        azure_attachment_precondition(),
                        block(
                            "postcondition",
                            condition=ref('lower(replace(self.location, " ", "")) == var.location'),
                            error_message="The existing virtual network must be in the selected VM region.",
                        ),
                    ],
                )
            ],
        )
    )
    builder.main.append(
        block(
            "data",
            "azurerm_subnet",
            "existing",
            count=ref("var.use_existing_network ? 1 : 0"),
            name=ref('try(split("/", var.existing_subnetwork_resource)[10], "")'),
            virtual_network_name=ref("data.azurerm_virtual_network.existing[0].name"),
            resource_group_name=group,
            children=[
                block(
                    "lifecycle",
                    children=[
                        block(
                            "postcondition",
                            condition=ref(
                                'length(self.address_prefixes) == 1 && try(self.address_prefixes[0] == var.existing_subnet_cidr, false) && self.network_security_group_id != null && self.network_security_group_id != ""'
                            ),
                            error_message="Choose an IPv4-only existing subnet with the declared CIDR and an existing reviewed subnet NSG.",
                        ),
                    ],
                )
            ],
        )
    )
    for address in (
        "azurerm_virtual_network.this",
        "azurerm_subnet.this",
        "azurerm_network_security_group.this",
        "azurerm_subnet_network_security_group_association.this",
        "azurerm_public_ip.egress",
        "azurerm_nat_gateway.this",
        "azurerm_nat_gateway_public_ip_association.this",
        "azurerm_subnet_nat_gateway_association.this",
    ):
        builder.main.append(block("moved", **{"from": ref(address), "to": ref(address + "[0]")}))
