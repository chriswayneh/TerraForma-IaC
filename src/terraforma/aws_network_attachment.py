from terraforma.hcl import block, ref


def declare_aws_network_attachment(builder):
    builder.variable(
        "use_existing_network",
        "Attach this VM to one existing IPv4-only standard-zone subnet and one reviewed security group in the selected AWS account, region and VPC. Existing mode creates no VPC, subnet, security group, route, internet gateway or NAT. Existing rules, network ACLs and egress remain separately managed. Public IP assignment remains separate. Use a separate project/state: switching a deployed new-network project can delete its owned infrastructure, replace the VM and delete boot data; this toggle does not transfer ownership.",
        False,
        type_name="bool",
    )
    for name, prefix, description in (
        (
            "existing_subnetwork_resource",
            "subnet",
            "Existing subnet ID in the selected account and region, such as subnet-0123456789abcdef0. Shared VPC, Outposts, Local Zones, Wavelength and IPv6/dual-stack subnets are unsupported.",
        ),
        (
            "existing_security_group_id",
            "sg",
            "One reviewed existing security group ID, such as sg-0123456789abcdef0, in the same account and VPC as the selected subnet. Rules are not modified. Effective access remains unverified.",
        ),
    ):
        builder.variable(
            name,
            description,
            "",
            pattern=rf"^($|{prefix}-([0-9a-f]{{8}}|[0-9a-f]{{17}}))$",
            visible_when={"use_existing_network": True},
            required_when={"use_existing_network": True},
        )
    builder.variable(
        "existing_subnet_cidr",
        "Actual IPv4 CIDR of the existing subnet. Use one canonical RFC1918 /16 through /28 range. Terraform later checks subnet metadata; this declaration does not change the range or verify IP availability.",
        "10.0.0.0/24",
        network_policy="vm_network",
        prefix_minimum=16,
        prefix_maximum=28,
        visible_when={"use_existing_network": True},
        required_when={"use_existing_network": True},
    )
    builder.variable(
        "confirm_existing_network_review",
        "I have reviewed the existing subnet and security group, effective rules and network ACLs, region/zone, routing, outbound connectivity and administrator access. The supplied administrator CIDR does not create a rule in this mode. This declaration does not verify connectivity or approve deployment.",
        False,
        type_name="bool",
        visible_when={"use_existing_network": True},
    )


def aws_attachment_precondition():
    return block(
        "precondition",
        condition=ref(
            'var.use_existing_network ? (var.confirm_existing_network_review && var.network_cidr == "10.0.0.0/16" && '
            'var.existing_subnetwork_resource != "" && var.existing_security_group_id != "") : '
            '(var.existing_subnetwork_resource == "" && var.existing_security_group_id == "" && !var.confirm_existing_network_review && var.existing_subnet_cidr == "10.0.0.0/24")'
        ),
        error_message="Existing AWS network mode requires reviewed subnet/security-group references and no conflicting new-network range. Clear inactive references and existing CIDR changes in new-network mode.",
    )


def add_aws_attachment_data(builder):
    builder.main.append(
        block(
            "data",
            "aws_subnet",
            "existing",
            count=ref("var.use_existing_network ? 1 : 0"),
            id=ref("var.existing_subnetwork_resource"),
            children=[
                block(
                    "lifecycle",
                    children=[
                        aws_attachment_precondition(),
                        block(
                            "postcondition",
                            condition=ref(
                                "self.owner_id == var.aws_account_id && self.cidr_block == var.existing_subnet_cidr && !self.ipv6_native && "
                                '(self.ipv6_cidr_block == null || self.ipv6_cidr_block == "") && (self.outpost_arn == null || self.outpost_arn == "") && '
                                'can(regex("^${var.region}[a-z]$", self.availability_zone)) && '
                                '(var.availability_zone == "" || self.availability_zone == var.availability_zone)'
                            ),
                            error_message="Choose an owned IPv4-only, non-Outposts subnet with the declared CIDR in a compatible standard availability zone.",
                        ),
                    ],
                )
            ],
        )
    )
    builder.main.append(
        block(
            "data",
            "aws_security_group",
            "existing",
            count=ref("var.use_existing_network ? 1 : 0"),
            id=ref("var.existing_security_group_id"),
            children=[
                block(
                    "lifecycle",
                    children=[
                        block(
                            "postcondition",
                            condition=ref(
                                'self.vpc_id == data.aws_subnet.existing[0].vpc_id && try(split(":", self.arn)[4] == var.aws_account_id, false)'
                            ),
                            error_message="Choose a reviewed security group owned by the selected account in the existing subnet's VPC.",
                        )
                    ],
                )
            ],
        )
    )
    addresses = [
        "aws_vpc.this",
        "aws_internet_gateway.this",
        "aws_route_table.public",
        "aws_security_group.web",
    ]
    if not builder.config.is_public:
        addresses.extend(["aws_eip.nat", "aws_nat_gateway.this", "aws_route_table.private"])
    for address in addresses:
        builder.main.append(block("moved", **{"from": ref(address), "to": ref(address + "[0]")}))
