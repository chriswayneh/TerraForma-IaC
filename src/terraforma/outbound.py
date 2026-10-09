from terraforma.hcl import block, ref, value_hcl


def declare_outbound_access(builder):
    builder.variable(
        "outbound_access",
        "Outbound port profile for this project's new VM network. unrestricted preserves the existing allow-all behavior. https_dns permits TCP 443 and TCP/UDP 53 to IPv4 destinations; provider platform services and Windows licensing exceptions remain. HTTP, outbound SSH/RDP, database connections and other application ports can fail, including within private networks. Review initialization, updates and workload dependencies before changing it. This is not a destination allowlist or a guarantee against data exfiltration. Existing-subnet policies remain separately managed and require unrestricted here. NAT, routes and public-IP choices are unchanged and can still incur charges. Effective policy and live connectivity remain unverified.",
        "unrestricted",
        choices=("unrestricted", "https_dns"),
        visible_when={"use_existing_network": False},
    )


def outbound_precondition():
    return block(
        "precondition",
        condition=ref('!var.use_existing_network || var.outbound_access == "unrestricted"'),
        error_message="Existing-subnet outbound policy is separately managed. Clear the inactive restricted outbound profile before selecting an existing network.",
    )


def aws_outbound_rules():
    unrestricted = [{"protocol": "-1", "from_port": 0, "to_port": 0}]
    restricted = [
        {"protocol": "tcp", "from_port": 443, "to_port": 443},
        {"protocol": "tcp", "from_port": 53, "to_port": 53},
        {"protocol": "udp", "from_port": 53, "to_port": 53},
    ]
    return [
        block(
            "dynamic",
            "egress",
            for_each=ref(
                f'var.outbound_access == "unrestricted" ? {value_hcl(unrestricted)} : {value_hcl(restricted)}'
            ),
            children=[
                block(
                    "content",
                    protocol=ref("egress.value.protocol"),
                    from_port=ref("egress.value.from_port"),
                    to_port=ref("egress.value.to_port"),
                    cidr_blocks=["0.0.0.0/0"],
                )
            ],
        )
    ]


def azure_outbound_rules(windows):
    rules = {
        "AllowHttpsEgress": {
            "priority": 2000,
            "protocol": "Tcp",
            "port": "443",
            "access": "Allow",
            "destination": "*",
        },
        "AllowDnsTcpEgress": {
            "priority": 2001,
            "protocol": "Tcp",
            "port": "53",
            "access": "Allow",
            "destination": "*",
        },
        "AllowDnsUdpEgress": {
            "priority": 2002,
            "protocol": "Udp",
            "port": "53",
            "access": "Allow",
            "destination": "*",
        },
        "DenyOtherEgress": {
            "priority": 2010,
            "protocol": "*",
            "port": "*",
            "access": "Deny",
            "destination": "*",
        },
    }
    if windows:
        rules["AllowWindowsLicensing"] = {
            "priority": 2003,
            "protocol": "Tcp",
            "port": "1688",
            "access": "Allow",
            "destination": "AzurePlatformLKM",
        }
    return [
        block(
            "dynamic",
            "security_rule",
            for_each=ref(f'var.outbound_access == "https_dns" ? {value_hcl(rules)} : {{}}'),
            children=[
                block(
                    "content",
                    name=ref("security_rule.key"),
                    priority=ref("security_rule.value.priority"),
                    direction="Outbound",
                    access=ref("security_rule.value.access"),
                    protocol=ref("security_rule.value.protocol"),
                    source_port_range="*",
                    destination_port_range=ref("security_rule.value.port"),
                    source_address_prefix="*",
                    destination_address_prefix=ref("security_rule.value.destination"),
                )
            ],
        )
    ]


def add_gcp_outbound(builder):
    attributes = {
        "count": ref('var.use_existing_network || var.outbound_access != "https_dns" ? 0 : 1'),
        "network": ref("google_compute_network.this[0].name"),
        "direction": "EGRESS",
        "destination_ranges": ["0.0.0.0/0"],
        "target_tags": ["terraforma-web"],
    }
    builder.resource(
        "google_compute_firewall",
        "outbound_web_dns",
        **attributes,
        name=ref('"${var.project_name}-egress-web-dns"'),
        priority=1000,
        children=[
            block("allow", protocol="tcp", ports=["443", "53"]),
            block("allow", protocol="udp", ports=["53"]),
        ],
    )
    builder.resource(
        "google_compute_firewall",
        "outbound_deny_other",
        **attributes,
        name=ref('"${var.project_name}-egress-deny-other"'),
        priority=1100,
        children=[block("deny", protocol="all")],
    )
