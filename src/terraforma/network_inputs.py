import ipaddress


def selected_vm_cidr(provider: str, values: dict) -> tuple[str, bool]:
    existing = provider in {"aws", "azure"} and values.get("use_existing_network", False)
    return values["existing_subnet_cidr"] if existing else values["network_cidr"], existing


def vm_subnet(
    provider: str, network_cidr: str, public: bool, existing: bool = False
) -> ipaddress.IPv4Network:
    network = ipaddress.IPv4Network(network_cidr, strict=True)
    if provider == "gcp" or existing:
        return network
    number = 1 if provider == "azure" else 0 if public else 10
    prefix = network.prefixlen + 8
    return ipaddress.IPv4Network(
        (int(network.network_address) + number * (1 << (32 - prefix)), prefix)
    )


def usable_vm_address(
    provider: str, network_cidr: str, public: bool, address: str, existing: bool = False
) -> bool:
    subnet = vm_subnet(provider, network_cidr, public, existing)
    value = ipaddress.IPv4Address(address)
    first, reserved_last = (2, 2) if provider == "gcp" else (4, 1)
    return (
        int(subnet.network_address) + first
        <= int(value)
        <= int(subnet.broadcast_address) - reserved_last
    )


def private_ip_condition(provider: str, public: bool) -> str:
    subnet = (
        "var.network_cidr"
        if provider == "gcp"
        else f"cidrsubnet(var.network_cidr, 8, {1 if provider == 'azure' else 0 if public else 10})"
    )
    if provider == "azure":
        subnet = f"(var.use_existing_network ? var.existing_subnet_cidr : {subnet})"
    first, last = (2, -3) if provider == "gcp" else (4, -2)

    def number(expression: str) -> str:
        return f'sum([for index, octet in split(".", {expression}) : tonumber(octet) * pow(256, 3 - index)])'

    value = number("var.private_ip_address")
    return (
        'var.private_ip_address == "" ? true : try('
        f"{value} >= {number(f'cidrhost({subnet}, {first})')} && "
        f"{value} <= {number(f'cidrhost({subnet}, {last})')}, false)"
    )
