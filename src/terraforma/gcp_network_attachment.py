from terraforma.hcl import block, ref

SUBNETWORK_PATTERN = r"projects/[a-z][a-z0-9-]{4,28}[a-z0-9]/regions/[a-z][a-z0-9-]{1,62}/subnetworks/[a-z](?:[a-z0-9-]{0,61}[a-z0-9])?"


def declare_gcp_network_attachment(builder):
    builder.variable(
        "use_existing_network",
        "Attach this VM to one existing IPv4-only regional subnet in the selected project. Existing mode creates no VPC, subnet, firewall, activation route, router, NAT or Compute API enablement. Review inherited firewall policies, routes, egress, administrator access and Windows activation separately. Public IP assignment remains separate. Use a separate project/state to attach to independently managed infrastructure. Switching an already deployed new-network project can delete its owned network, routes, rules and NAT, replace the VM and delete boot data. This toggle does not transfer state ownership; review the plan and recovery first.",
        False,
        type_name="bool",
    )
    builder.variable(
        "existing_subnetwork_resource",
        "Exact existing subnet resource: projects/PROJECT/regions/REGION/subnetworks/NAME. It must belong to the selected project and region. Shared VPC, cross-project, legacy and IPv6/dual-stack subnets are unsupported. Existence, permissions, inherited rules, routing and capacity are not checked during generation.",
        "",
        pattern=rf"^($|{SUBNETWORK_PATTERN})$",
        visible_when={"use_existing_network": True},
        required_when={"use_existing_network": True},
    )
    builder.variable(
        "confirm_existing_network_review",
        "I have reviewed the existing subnet's actual primary IPv4 CIDR, project, region, inherited access policies, administrator path, outbound connectivity and any Windows activation requirements. Existing rules remain separately managed; supplied administrator CIDRs or IAP choices do not create rules in this mode. This declaration does not verify connectivity or approve deployment.",
        False,
        type_name="bool",
        visible_when={"use_existing_network": True},
    )


def gcp_attachment_precondition():
    return block(
        "precondition",
        condition=ref(
            "var.use_existing_network ? (var.confirm_existing_network_review && "
            'try(split("/", var.existing_subnetwork_resource)[1] == var.gcp_project_id && split("/", var.existing_subnetwork_resource)[3] == var.region, false)) : '
            '(var.existing_subnetwork_resource == "" && !var.confirm_existing_network_review)'
        ),
        error_message="Existing subnet mode requires an exact reference in the selected project and region and an explicit network review declaration. Clear inactive references and declarations in new-network mode.",
    )


def add_existing_subnetwork_data(builder):
    builder.main.append(
        block(
            "data",
            "google_compute_subnetwork",
            "existing",
            count=ref("var.use_existing_network ? 1 : 0"),
            name=ref('element(reverse(split("/", var.existing_subnetwork_resource)), 0)'),
            project=ref("var.gcp_project_id"),
            region=ref("var.region"),
            children=[
                block(
                    "lifecycle",
                    children=[
                        gcp_attachment_precondition(),
                        block(
                            "postcondition",
                            condition=ref(
                                'self.ip_cidr_range == var.network_cidr && self.stack_type == "IPV4_ONLY"'
                            ),
                            error_message="Choose an IPv4-only existing subnet whose actual primary CIDR matches the declared VM subnet range.",
                        ),
                    ],
                )
            ],
        )
    )


def add_network_address_moves(builder):
    addresses = [
        "google_project_service.compute",
        "google_compute_network.this",
        "google_compute_subnetwork.this",
        "google_compute_firewall.this",
        "google_compute_router.this",
        "google_compute_router_nat.this",
    ]
    if builder.config.architecture_type == "windows_virtual_machine":
        addresses += [
            "google_compute_route.windows_activation",
            "google_compute_firewall.windows_activation",
        ]
    for address in addresses:
        builder.main.append(block("moved", **{"from": ref(address), "to": ref(address + "[0]")}))
