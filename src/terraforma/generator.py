import json
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from terraforma.network_inputs import private_ip_condition

LINUX_IMAGE_CHOICES = {
    "aws": ("amazon-linux-2023", "ubuntu-24.04"),
    "azure": ("ubuntu-22.04", "ubuntu-24.04"),
    "gcp": ("debian-12", "ubuntu-24.04"),
}

AZURE_RESERVED_USERNAMES = (
    "1",
    "123",
    "a",
    "actuser",
    "adm",
    "admin",
    "admin1",
    "admin2",
    "administrator",
    "aspnet",
    "backup",
    "console",
    "david",
    "guest",
    "john",
    "owner",
    "root",
    "server",
    "sql",
    "support_388945a0",
    "support",
    "sys",
    "test",
    "test1",
    "test2",
    "test3",
    "user",
    "user1",
    "user2",
    "user3",
    "user4",
    "user5",
    "video",
)


class WizardConfig(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    provider: Literal["aws", "azure", "gcp"]
    project_name: str = Field(pattern=r"^[a-z][a-z0-9\-]{1,18}[a-z0-9]$")
    architecture_type: Literal[
        "virtual_machine",
        "single_web_server",
        "load_balanced_tier",
        "secure_database",
        "static_site",
    ]
    is_public: bool = False
    enable_encryption: bool = True


@dataclass(frozen=True)
class Expression:
    value: str


def value_hcl(value: Any) -> str:
    if isinstance(value, Expression):
        return value.value
    if isinstance(value, dict):
        return (
            "{ "
            + ", ".join(f"{json.dumps(key)} = {value_hcl(item)}" for key, item in value.items())
            + " }"
        )
    if isinstance(value, list):
        return "[" + ", ".join(value_hcl(item) for item in value) + "]"
    if isinstance(value, str):
        return json.dumps(value, ensure_ascii=False).replace("${", "$${").replace("%{", "%%{")
    return json.dumps(value)


@dataclass
class Block:
    kind: str
    labels: tuple[str, ...] = ()
    attributes: dict[str, Any] = field(default_factory=dict)
    children: list["Block"] = field(default_factory=list)

    def render(self, indent: int = 0) -> str:
        prefix = "  " * indent
        header = " ".join([self.kind, *(json.dumps(label) for label in self.labels)])
        lines = [f"{prefix}{header} {{"]
        lines.extend(
            f"{prefix}  {name} = {value_hcl(value)}" for name, value in self.attributes.items()
        )
        lines.extend(child.render(indent + 1) for child in self.children)
        lines.append(f"{prefix}}}")
        return "\n".join(lines)


def block(kind: str, *labels: str, children: list[Block] | None = None, **attributes: Any) -> Block:
    return Block(kind, labels, attributes, children or [])


def ref(value: str) -> Expression:
    return Expression(value)


class TerraformGenerator:
    def __init__(self, config: WizardConfig):
        self.config = config
        self.main: list[Block] = []
        self.variables: list[Block] = []
        self.outputs: list[Block] = []
        self.input_constraints: dict[str, dict] = {}

    def variable(
        self,
        name: str,
        description: str,
        default: Any = None,
        *,
        sensitive: bool = False,
        type_name: str = "string",
        minimum: int | None = None,
        maximum: int | None = None,
        prefix_minimum: int | None = None,
        prefix_maximum: int | None = None,
        visible_when: dict[str, bool] | None = None,
        required_when: dict[str, bool] | None = None,
        choices: tuple[str, ...] | None = None,
        pattern: str | None = None,
        forbidden_values: tuple[str, ...] | None = None,
        network_policy: Literal[
            "database_cidr", "database_address", "administrator_cidr", "vm_network"
        ]
        | None = None,
    ) -> None:
        attributes = {"description": description, "type": ref(type_name)}
        if default is not None:
            attributes["default"] = default
        if sensitive:
            attributes["sensitive"] = True
        validations = []
        if minimum is not None and maximum is not None:
            validations.append(
                block(
                    "validation",
                    condition=ref(
                        f"var.{name} >= {minimum} && var.{name} <= {maximum} && floor(var.{name}) == var.{name}"
                    ),
                    error_message=f"Use a whole number between {minimum} and {maximum}.",
                )
            )
        if choices:
            validations.append(
                block(
                    "validation",
                    condition=ref(f"contains({value_hcl(list(choices))}, var.{name})"),
                    error_message="Use a supported value: " + ", ".join(choices),
                )
            )
        if pattern:
            pattern_condition = f"can(regex({value_hcl(pattern)}, var.{name}))"
            if required_when:
                pattern_condition = f'var.{name} == "" || {pattern_condition}'
            validations.append(
                block(
                    "validation",
                    condition=ref(pattern_condition),
                    error_message="Use the required identifier format for this field.",
                )
            )
        if forbidden_values:
            validations.append(
                block(
                    "validation",
                    condition=ref(f"!contains({value_hcl(list(forbidden_values))}, var.{name})"),
                    error_message="Choose an administrator username outside the provider's reserved-name list.",
                )
            )
        if network_policy:
            address = f"var.{name}"
            if network_policy == "vm_network":
                prefix = f'tonumber(split("/", {address})[1])'
                network = f"cidrhost({address}, 0)"
                private_172 = value_hcl(r"^172\.(1[6-9]|2[0-9]|3[01])\.")
                condition = (
                    f"can(cidrnetmask({address})) && try("
                    f"{prefix} >= {prefix_minimum} && {prefix} <= {prefix_maximum} && "
                    f'format("%s/%d", {network}, {prefix}) == {address} && '
                    f'(startswith({network}, "10.") || '
                    f"can(regex({private_172}, {network})) || "
                    f'startswith({network}, "192.168.")), false)'
                )
                message = f"Use a canonical RFC1918 private IPv4 network with a /{prefix_minimum} through /{prefix_maximum} prefix, without host bits."
            elif network_policy in {"database_cidr", "administrator_cidr"}:
                public_prefix = 32 if network_policy == "administrator_cidr" else 24
                prefix = f'tonumber(split("/", {address})[1])'
                network = f"cidrhost({address}, 0)"
                private_172 = value_hcl(r"^172\.(1[6-9]|2[0-9]|3[01])\.")
                condition = (
                    f"can(cidrnetmask({address})) && try("
                    f"{prefix} >= {public_prefix} || "
                    f'(startswith({network}, "10.") && {prefix} >= 8) || '
                    f"(can(regex({private_172}, {network})) && {prefix} >= 12) || "
                    f'(startswith({network}, "192.168.") && {prefix} >= 16), false)'
                )
                message = "Use an RFC1918 private network or an IPv4 /24 through /32 client network; prefer /32 for one client."
                if network_policy == "administrator_cidr":
                    message = "Use an RFC1918 private subnet or a single IPv4 /32 administrator address. Public network ranges are unsupported."
            else:
                octet = f'tonumber(split(".", {address})[0])'
                condition = (
                    f'can(cidrnetmask(format("%s/32", {address}))) && '
                    f"try({octet} > 0 && {octet} < 224 && {octet} != 127, false)"
                )
                message = "Use a client IPv4 address outside 0/8, loopback, multicast, and reserved 224/3; 0.0.0.0 broad Azure-service access is unsupported."
            description += " " + message
            attributes["description"] = description
            validations.append(block("validation", condition=ref(condition), error_message=message))
        self.input_constraints[name] = {
            "minimum": minimum,
            "maximum": maximum,
            "prefix_minimum": prefix_minimum,
            "prefix_maximum": prefix_maximum,
            "choices": list(choices) if choices else None,
            "pattern": pattern,
            "forbidden_values": list(forbidden_values) if forbidden_values else None,
            "network_policy": network_policy,
            "visible_when": visible_when,
            "required_when": required_when,
        }
        self.variables.append(block("variable", name, children=validations, **attributes))

    def resource(
        self,
        kind: str,
        label: str = "this",
        *,
        children: list[Block] | None = None,
        **attributes: Any,
    ) -> None:
        self.main.append(block("resource", kind, label, children=children, **attributes))

    def output(self, name: str, expression: str, description: str) -> None:
        self.outputs.append(block("output", name, value=ref(expression), description=description))

    def generate(self) -> dict[str, str]:
        if self.main:
            raise RuntimeError("Create a new generator for each configuration.")
        provider = {"aws": "aws", "azure": "azurerm", "gcp": "google"}[self.config.provider]
        versions = {"aws": "~> 6.0", "azure": "~> 4.0", "gcp": "~> 7.0"}
        providers = {
            provider: {"source": f"hashicorp/{provider}", "version": versions[self.config.provider]}
        }
        if self.config.architecture_type == "static_site" and self.config.provider != "aws":
            providers["random"] = {"source": "hashicorp/random", "version": "~> 3.0"}
        self.main.append(
            block(
                "terraform",
                required_version=">= 1.6, < 2.0",
                children=[block("required_providers", **providers)],
            )
        )
        self.variable("project_name", "Resource name prefix.", self.config.project_name)
        self.variable(
            "environment",
            {
                "aws": "Environment tag applied through AWS provider default tags to supported resources.",
                "azure": "Environment tag on the new resource group; tags are not inherited by its resources.",
                "gcp": "Environment label on generated compute, database, or storage resources that support labels.",
            }[self.config.provider]
            + " Use a distinct project name per environment; this label does not isolate state or change resource names.",
            "development",
            pattern=r"^[a-z][a-z0-9\-]{1,18}[a-z0-9]$",
        )
        if self.config.architecture_type == "load_balanced_tier":
            self.variable(
                "instance_count",
                "Number of web VMs in the tier. Each VM adds compute and disk cost; this does not configure automatic scaling or multi-zone placement.",
                2,
                type_name="number",
                minimum=2,
                maximum=20,
            )
        if self.config.architecture_type in {
            "virtual_machine",
            "single_web_server",
            "load_balanced_tier",
        }:
            self.variable(
                "os_image",
                "Linux image from the supported publisher catalog, using x86_64/AMD64. "
                + "The image version can be pinned separately; latest resolves at planning time. "
                + "Region, VM-size compatibility and account policy need preflight. Custom images and ARM64 are not supported.",
                LINUX_IMAGE_CHOICES[self.config.provider][0],
                choices=LINUX_IMAGE_CHOICES[self.config.provider],
            )
        if self.config.architecture_type == "virtual_machine":
            self.variable(
                "network_cidr",
                "Address range for the new VM network. Check for overlap with networks you will connect; existing-network attachment is not configured. "
                + {
                    "aws": "The recipe creates two public and two private subnets with eight additional prefix bits, in two available zones.",
                    "azure": "The recipe derives one workload subnet with eight additional prefix bits.",
                    "gcp": "This range is used directly for one regional subnet; GCP VPC networks have no single enclosing address range.",
                }[self.config.provider],
                "10.0.1.0/24" if self.config.provider == "gcp" else "10.0.0.0/16",
                network_policy="vm_network",
                prefix_minimum=16,
                prefix_maximum=28 if self.config.provider == "gcp" else 20,
            )
            self._data_disk_inputs()
            octet = r"(25[0-5]|2[0-4][0-9]|1[0-9]{2}|[1-9]?[0-9])"
            self.variable(
                "private_ip_address",
                "Optional fixed private IPv4 address for this VM. Leave blank for cloud allocation. The address must be usable in the generated workload subnet; provider-reserved addresses are rejected. AWS public VMs use the first public subnet, private VMs use the first private subnet; Azure uses its derived workload subnet and GCP uses the entered subnet directly. The address is not reserved independently and availability is not checked. Changing it can interrupt access or replace resources; review the plan.",
                "",
                pattern=rf"^($|{octet}\.{octet}\.{octet}\.{octet})$",
            )
            self._workload_identity_inputs()
            self.variable(
                "allowed_cidr",
                "Administrator network permitted to connect on SSH port 22. Private VMs require an existing routed access path; this recipe does not create a VPN or bastion.",
                None if self.config.is_public else "10.0.0.0/16",
                network_policy="administrator_cidr",
            )
            if self.config.provider == "aws":
                self.variable(
                    "ssh_public_key",
                    "Existing administrator Ed25519 or RSA public key to import into EC2. Keep the matching private key outside this project.",
                )
        getattr(self, f"_{self.config.provider}")()
        return {
            "main.tf": "\n\n".join(item.render() for item in self.main) + "\n",
            "variables.tf": "\n\n".join(item.render() for item in self.variables) + "\n",
            "outputs.tf": "\n\n".join(item.render() for item in self.outputs) + "\n",
        }

    def _workload_identity_inputs(self) -> None:
        self.variable(
            "enable_workload_identity",
            {
                "aws": "Attach an existing IAM instance profile for workload API access. Review its role policies and trust relationship; provisioning requires permission to pass its role. This recipe creates no IAM role or policy grant.",
                "azure": "Create a system-assigned managed identity for this VM. It receives no role assignments from this recipe; grant only reviewed access separately. The identity's lifecycle is tied to the VM.",
                "gcp": "Attach an existing user-managed service account for workload API access, using the cloud-platform OAuth scope with access controlled by its IAM roles. Review those roles and attachment permissions separately. This recipe creates no service account, key or IAM grant; changing the account requires a stopped VM.",
            }[self.config.provider],
            False,
            type_name="bool",
        )
        if self.config.provider != "azure":
            self.variable(
                "workload_identity",
                "Existing IAM instance profile name, not a role name or ARN. Its permissions, account and trust configuration remain unverified."
                if self.config.provider == "aws"
                else "Existing user-managed service account email (name@project.iam.gserviceaccount.com). Compute default service accounts and credential keys are unsupported. Identity and permissions remain unverified.",
                "",
                pattern=r"^[A-Za-z0-9_+=,.@\-]{1,128}$"
                if self.config.provider == "aws"
                else r"^[a-z][a-z0-9\-]{4,28}[a-z0-9]@[a-z][a-z0-9\-]{4,28}[a-z0-9]\.iam\.gserviceaccount\.com$",
                visible_when={"enable_workload_identity": True},
                required_when={"enable_workload_identity": True},
            )

    def _identity_precondition(self) -> Block:
        return block(
            "lifecycle",
            children=[
                block(
                    "precondition",
                    condition=ref('!var.enable_workload_identity || var.workload_identity != ""'),
                    error_message="Supply the existing workload identity reference when workload identity is enabled.",
                ),
                self._private_ip_precondition(),
            ],
        )

    def _private_ip_precondition(self) -> Block:
        return block(
            "precondition",
            condition=ref(private_ip_condition(self.config.provider, self.config.is_public)),
            error_message="Choose a usable private IPv4 address in the generated VM subnet, excluding provider-reserved addresses, or leave it blank for cloud allocation.",
        )

    def _data_disk_inputs(self) -> None:
        disk_types = {
            "aws": ("gp3", "gp2"),
            "azure": ("StandardSSD_LRS", "Standard_LRS", "Premium_LRS"),
            "gcp": ("pd-balanced", "pd-standard", "pd-ssd"),
        }[self.config.provider]
        self.variable(
            "enable_data_disk",
            "Attach one new empty data disk. It adds storage charges and is managed by this Terraform project, so teardown can delete it. No filesystem formatting, mounting, backup, or recovery policy is configured.",
            False,
            type_name="bool",
        )
        self.variable(
            "data_disk_size_gb",
            "Data disk size in GiB. Size affects billing and provider disk tiers; shrinking an existing disk is not supported by this recipe.",
            100,
            type_name="number",
            minimum=32,
            maximum=2048,
            visible_when={"enable_data_disk": True},
        )
        self.variable(
            "data_disk_type",
            "Data disk storage class. Review VM, region, performance and billing compatibility before provisioning.",
            disk_types[0],
            choices=disk_types,
            visible_when={"enable_data_disk": True},
        )

    def _aws(self) -> None:
        self.variable("region", "AWS region.", "us-east-1")
        self.variable(
            "aws_account_id",
            "Target AWS account ID: 12 digits. Terraform checks this against its authenticated account before provider operations.",
            pattern=r"^[0-9]{12}$",
        )
        self.main.append(
            block(
                "provider",
                "aws",
                region=ref("var.region"),
                allowed_account_ids=[ref("var.aws_account_id")],
                children=[
                    block(
                        "default_tags",
                        tags={"Environment": ref("var.environment"), "ManagedBy": "TerraForma-IaC"},
                    )
                ],
            )
        )
        if self.config.architecture_type == "static_site":
            self._aws_static()
            return
        self.main.append(block("data", "aws_availability_zones", "available", state="available"))
        self.resource(
            "aws_vpc",
            cidr_block=ref("var.network_cidr")
            if self.config.architecture_type == "virtual_machine"
            else "10.0.0.0/16",
            enable_dns_support=True,
            enable_dns_hostnames=True,
            tags={"Name": ref("var.project_name")},
        )
        self.resource(
            "aws_subnet",
            "public",
            count=2,
            vpc_id=ref("aws_vpc.this.id"),
            cidr_block=ref("cidrsubnet(aws_vpc.this.cidr_block, 8, count.index)"),
            availability_zone=ref("data.aws_availability_zones.available.names[count.index]"),
            map_public_ip_on_launch=True,
        )
        self.resource(
            "aws_subnet",
            "private",
            count=2,
            vpc_id=ref("aws_vpc.this.id"),
            cidr_block=ref("cidrsubnet(aws_vpc.this.cidr_block, 8, count.index + 10)"),
            availability_zone=ref("data.aws_availability_zones.available.names[count.index]"),
        )
        self.resource("aws_internet_gateway", vpc_id=ref("aws_vpc.this.id"))
        self.resource(
            "aws_route_table",
            "public",
            vpc_id=ref("aws_vpc.this.id"),
            children=[
                block(
                    "route", cidr_block="0.0.0.0/0", gateway_id=ref("aws_internet_gateway.this.id")
                )
            ],
        )
        self.resource(
            "aws_route_table_association",
            "public",
            count=2,
            subnet_id=ref("aws_subnet.public[count.index].id"),
            route_table_id=ref("aws_route_table.public.id"),
        )
        if self.config.enable_encryption:
            self.resource(
                "aws_kms_key",
                description="TerraForma storage encryption",
                enable_key_rotation=True,
                deletion_window_in_days=30,
            )
        if self.config.architecture_type == "secure_database":
            self._aws_database()
            return
        standalone = self.config.architecture_type == "virtual_machine"
        if not standalone:
            self.variable(
                "allowed_cidr",
                "Clients allowed to access HTTP.",
                "0.0.0.0/0" if self.config.is_public else "10.0.0.0/16",
            )
        balanced = self.config.architecture_type == "load_balanced_tier"
        private = balanced or not self.config.is_public
        if private:
            self.resource("aws_eip", "nat", domain="vpc")
            self.resource(
                "aws_nat_gateway",
                allocation_id=ref("aws_eip.nat.id"),
                subnet_id=ref("aws_subnet.public[0].id"),
                depends_on=[ref("aws_internet_gateway.this")],
            )
            self.resource(
                "aws_route_table",
                "private",
                vpc_id=ref("aws_vpc.this.id"),
                children=[
                    block(
                        "route",
                        cidr_block="0.0.0.0/0",
                        nat_gateway_id=ref("aws_nat_gateway.this.id"),
                    )
                ],
            )
            self.resource(
                "aws_route_table_association",
                "private",
                count=2,
                subnet_id=ref("aws_subnet.private[count.index].id"),
                route_table_id=ref("aws_route_table.private.id"),
            )
        egress = block("egress", from_port=0, to_port=0, protocol="-1", cidr_blocks=["0.0.0.0/0"])
        ingress = block(
            "ingress",
            from_port=22 if standalone else 80,
            to_port=22 if standalone else 80,
            protocol="tcp",
            **(
                {"security_groups": [ref("aws_security_group.lb.id")]}
                if balanced
                else {"cidr_blocks": [ref("var.allowed_cidr")]}
            ),
        )
        self.resource(
            "aws_security_group",
            "web",
            name_prefix=ref('"${var.project_name}-web-"'),
            vpc_id=ref("aws_vpc.this.id"),
            children=[ingress, egress],
        )
        self.variable(
            "image_version",
            "Use latest to resolve the selected AWS image at planning time, or an exact AMI ID in the chosen region. The AMI must match the selected OS name, trusted owner, x86_64 architecture and HVM filters; custom publishers are unsupported. Verify availability, access and compatibility before planning. Changing an image can replace the VM and destroy boot-disk data. Pinning does not automatically patch the VM.",
            "latest",
            pattern=r"^(latest|ami-([0-9a-f]{8}|[0-9a-f]{17}))$",
        )
        self.main.append(
            block(
                "data",
                "aws_ami",
                "linux",
                most_recent=True,
                owners=ref('var.os_image == "amazon-linux-2023" ? ["amazon"] : ["099720109477"]'),
                children=[
                    block(
                        "filter",
                        name="name",
                        values=ref(
                            'var.os_image == "amazon-linux-2023" ? ["al2023-ami-2023.*-x86_64"] : ["ubuntu/images/hvm-ssd-gp3/ubuntu-noble-24.04-amd64-server-*"]'
                        ),
                    ),
                    block("filter", name="virtualization-type", values=["hvm"]),
                    block("filter", name="architecture", values=["x86_64"]),
                    block(
                        "dynamic",
                        "filter",
                        for_each=ref('var.image_version == "latest" ? [] : [var.image_version]'),
                        children=[block("content", name="image-id", values=[ref("filter.value")])],
                    ),
                ],
            )
        )
        self.variable("instance_type", "EC2 instance size.", "t3.micro")
        if standalone:
            self.variable(
                "protect_vm",
                "Enable EC2 API termination protection. Turn this off and apply that change before intentionally deleting or replacing the VM. This does not prevent stopping the VM and is not a backup or a guarantee against every deletion path.",
                True,
                type_name="bool",
            )
        self.variable(
            "detailed_monitoring",
            "Publish most EC2 metrics every minute instead of the basic five-minute interval. Detailed monitoring can add CloudWatch charges per instance; status checks already use one-minute periods. This does not install an agent or configure logs/alarms.",
            False,
            type_name="bool",
        )
        self.variable(
            "boot_disk_size_gb",
            "Boot disk size in GiB; review the image minimum and ongoing storage cost.",
            20,
            type_name="number",
            minimum=20,
            maximum=2048,
        )
        self.variable("boot_disk_type", "EBS boot disk class.", "gp3", choices=("gp3", "gp2"))
        disk = {
            "volume_type": ref("var.boot_disk_type"),
            "volume_size": ref("var.boot_disk_size_gb"),
            "encrypted": self.config.enable_encryption,
        }
        if self.config.enable_encryption:
            disk["kms_key_id"] = ref("aws_kms_key.this.arn")
        if standalone:
            self.resource(
                "aws_key_pair",
                key_name_prefix=ref('"${var.project_name}-"'),
                public_key=ref("var.ssh_public_key"),
            )
        self.resource(
            "aws_instance",
            "web",
            count=ref("var.instance_count") if balanced else 1,
            ami=ref("data.aws_ami.linux.id"),
            instance_type=ref("var.instance_type"),
            monitoring=ref("var.detailed_monitoring"),
            **(
                {
                    "iam_instance_profile": ref(
                        "var.enable_workload_identity ? var.workload_identity : null"
                    )
                }
                if standalone
                else {}
            ),
            **({"disable_api_termination": ref("var.protect_vm")} if standalone else {}),
            subnet_id=ref(f"aws_subnet.{'private' if private else 'public'}[count.index % 2].id"),
            associate_public_ip_address=not private,
            **(
                {"private_ip": ref('var.private_ip_address == "" ? null : var.private_ip_address')}
                if standalone
                else {}
            ),
            vpc_security_group_ids=[ref("aws_security_group.web.id")],
            **(
                {"key_name": ref("aws_key_pair.this.key_name")}
                if standalone
                else {
                    "user_data": ref(
                        'var.os_image == "amazon-linux-2023" ? '
                        + value_hcl(
                            "#!/bin/bash\nset -eu\ndnf install -y nginx\nsystemctl enable --now nginx\n"
                        )
                        + " : "
                        + value_hcl(
                            "#!/bin/bash\nset -eu\napt-get update\napt-get install -y nginx\nsystemctl enable --now nginx\n"
                        )
                    )
                }
            ),
            tags={"Name": ref("var.project_name")},
            children=[
                block("root_block_device", **disk),
                block("metadata_options", http_tokens="required"),
            ]
            + ([self._identity_precondition()] if standalone else []),
            **({"depends_on": [ref("aws_route_table_association.private")]} if private else {}),
        )
        if standalone:
            self.resource(
                "aws_ebs_volume",
                "data",
                count=ref("var.enable_data_disk ? 1 : 0"),
                availability_zone=ref("aws_instance.web[0].availability_zone"),
                size=ref("var.data_disk_size_gb"),
                type=ref("var.data_disk_type"),
                encrypted=True,
                **(
                    {"kms_key_id": ref("aws_kms_key.this.arn")}
                    if self.config.enable_encryption
                    else {}
                ),
            )
            self.resource(
                "aws_volume_attachment",
                "data",
                count=ref("var.enable_data_disk ? 1 : 0"),
                device_name="/dev/sdf",
                volume_id=ref("aws_ebs_volume.data[0].id"),
                instance_id=ref("aws_instance.web[0].id"),
                force_detach=False,
                stop_instance_before_detaching=True,
            )
            self.output(
                "data_disk_id",
                "var.enable_data_disk ? aws_ebs_volume.data[0].id : null",
                "Optional data volume ID. Map the actual Linux device before formatting; this project does not mount or back it up. AWS attachment changes may stop the VM.",
            )
        if balanced:
            self.resource(
                "aws_security_group",
                "lb",
                name_prefix=ref('"${var.project_name}-lb-"'),
                vpc_id=ref("aws_vpc.this.id"),
                children=[
                    block(
                        "ingress",
                        from_port=80,
                        to_port=80,
                        protocol="tcp",
                        cidr_blocks=[ref("var.allowed_cidr")],
                    ),
                    egress,
                ],
            )
            self.resource(
                "aws_lb",
                name=ref("var.project_name"),
                internal=not self.config.is_public,
                load_balancer_type="application",
                subnets=ref(f"aws_subnet.{'public' if self.config.is_public else 'private'}[*].id"),
                security_groups=[ref("aws_security_group.lb.id")],
            )
            self.resource(
                "aws_lb_target_group",
                port=80,
                protocol="HTTP",
                vpc_id=ref("aws_vpc.this.id"),
                children=[block("health_check", path="/")],
            )
            self.resource(
                "aws_lb_target_group_attachment",
                count=ref("var.instance_count"),
                target_group_arn=ref("aws_lb_target_group.this.arn"),
                target_id=ref("aws_instance.web[count.index].id"),
                port=80,
            )
            self.resource(
                "aws_lb_listener",
                load_balancer_arn=ref("aws_lb.this.arn"),
                port=80,
                protocol="HTTP",
                children=[
                    block(
                        "default_action",
                        type="forward",
                        target_group_arn=ref("aws_lb_target_group.this.arn"),
                    )
                ],
            )
            self.output(
                "endpoint",
                '"http://${aws_lb.this.dns_name}"',
                "HTTP endpoint; add TLS before serving sensitive traffic.",
            )
        else:
            address = "public_ip" if self.config.is_public else "private_ip"
            if standalone:
                self.output(
                    "vm_id",
                    "aws_instance.web[0].id",
                    "EC2 instance ID for cloud operations; available after provisioning.",
                )
                self.output(
                    "vm_name",
                    'aws_instance.web[0].tags["Name"]',
                    "EC2 Name tag; it is not a unique instance identifier. Use vm_id for operations.",
                )
                self.output(
                    "vm_location",
                    "aws_instance.web[0].availability_zone",
                    "EC2 availability zone; the region is supplied in the project inputs.",
                )
                self.output(
                    "vm_address",
                    f"aws_instance.web[0].{address}",
                    "VM IPv4 address; SSH requires the allowed client network and matching private key.",
                )
                self.output(
                    "ssh_username",
                    'var.os_image == "amazon-linux-2023" ? "ec2-user" : "ubuntu"',
                    "Default administrator username for the selected publisher image.",
                )
                return
            self.output(
                "endpoint",
                f'"http://${{aws_instance.web[0].{address}}}"',
                "Web server HTTP endpoint.",
            )

    def _aws_database(self) -> None:
        self.variable(
            "database_password",
            "PostgreSQL administrator password; supply through TF_VAR_database_password.",
            sensitive=True,
        )
        self.variable(
            "allowed_cidr",
            "Network permitted to connect to PostgreSQL.",
            "10.0.0.0/16",
            network_policy="database_cidr",
        )
        self.resource(
            "aws_security_group",
            "database",
            vpc_id=ref("aws_vpc.this.id"),
            children=[
                block(
                    "ingress",
                    from_port=5432,
                    to_port=5432,
                    protocol="tcp",
                    cidr_blocks=[ref("var.allowed_cidr")],
                )
            ],
        )
        self.resource(
            "aws_db_subnet_group",
            subnet_ids=ref(f"aws_subnet.{'public' if self.config.is_public else 'private'}[*].id"),
        )
        attributes = {
            "identifier": ref("var.project_name"),
            "engine": "postgres",
            "instance_class": "db.t3.micro",
            "allocated_storage": 20,
            "storage_type": "gp3",
            "storage_encrypted": self.config.enable_encryption,
            "username": "terraforma",
            "password": ref("var.database_password"),
            "db_name": "app",
            "db_subnet_group_name": ref("aws_db_subnet_group.this.name"),
            "vpc_security_group_ids": [ref("aws_security_group.database.id")],
            "publicly_accessible": self.config.is_public,
            "multi_az": True,
            "backup_retention_period": 7,
            "deletion_protection": True,
            "skip_final_snapshot": False,
            "final_snapshot_identifier": ref('"${var.project_name}-final"'),
        }
        if self.config.enable_encryption:
            attributes["kms_key_id"] = ref("aws_kms_key.this.arn")
        self.resource("aws_db_instance", **attributes)
        self.output(
            "database_endpoint", "aws_db_instance.this.endpoint", "PostgreSQL hostname and port."
        )

    def _aws_static(self) -> None:
        self.variable(
            "index_html",
            "Initial website HTML.",
            "<html><body><h1>TerraForma-IaC</h1></body></html>",
        )
        self.resource("aws_s3_bucket", bucket_prefix=ref('"${var.project_name}-"'))
        self.resource(
            "aws_s3_bucket_public_access_block",
            bucket=ref("aws_s3_bucket.this.id"),
            block_public_acls=True,
            ignore_public_acls=True,
            block_public_policy=not self.config.is_public,
            restrict_public_buckets=not self.config.is_public,
        )
        self.resource(
            "aws_s3_bucket_versioning",
            bucket=ref("aws_s3_bucket.this.id"),
            children=[block("versioning_configuration", status="Enabled")],
        )
        self.resource(
            "aws_s3_bucket_server_side_encryption_configuration",
            bucket=ref("aws_s3_bucket.this.id"),
            children=[
                block(
                    "rule",
                    children=[
                        block("apply_server_side_encryption_by_default", sse_algorithm="AES256")
                    ],
                )
            ],
        )
        self.resource(
            "aws_s3_object",
            bucket=ref("aws_s3_bucket.this.id"),
            key="index.html",
            content=ref("var.index_html"),
            content_type="text/html",
        )
        if self.config.is_public:
            self.resource(
                "aws_s3_bucket_website_configuration",
                bucket=ref("aws_s3_bucket.this.id"),
                children=[block("index_document", suffix="index.html")],
            )
            policy = 'jsonencode({ Version = "2012-10-17", Statement = [{ Effect = "Allow", Principal = "*", Action = "s3:GetObject", Resource = "${aws_s3_bucket.this.arn}/*" }] })'
            self.resource(
                "aws_s3_bucket_policy",
                bucket=ref("aws_s3_bucket.this.id"),
                policy=ref(policy),
                depends_on=[ref("aws_s3_bucket_public_access_block.this")],
            )
            self.output(
                "endpoint",
                '"http://${aws_s3_bucket_website_configuration.this.website_endpoint}"',
                "Public S3 website endpoint; account-level public-access blocks must permit hosting.",
            )
        else:
            self.output(
                "endpoint",
                '"s3://${aws_s3_bucket.this.id}/index.html"',
                "Private site object; authenticated access required.",
            )

    def _azure(self) -> None:
        self.variable("location", "Azure region.", "eastus")
        self.variable("subscription_id", "Azure subscription ID.")
        self.main.append(
            block(
                "provider",
                "azurerm",
                subscription_id=ref("var.subscription_id"),
                children=[block("features")],
            )
        )
        self.resource(
            "azurerm_resource_group",
            name=ref("var.project_name"),
            location=ref("var.location"),
            tags={"Environment": ref("var.environment"), "ManagedBy": "TerraForma-IaC"},
        )
        common = {
            "resource_group_name": ref("azurerm_resource_group.this.name"),
            "location": ref("azurerm_resource_group.this.location"),
        }
        if self.config.architecture_type == "static_site":
            self._azure_static(common)
            return
        self.resource(
            "azurerm_virtual_network",
            name=ref('"${var.project_name}-vnet"'),
            address_space=[ref("var.network_cidr")]
            if self.config.architecture_type == "virtual_machine"
            else ["10.0.0.0/16"],
            **common,
        )
        subnet = {
            "name": "workload",
            "resource_group_name": common["resource_group_name"],
            "virtual_network_name": ref("azurerm_virtual_network.this.name"),
            "address_prefixes": [ref("cidrsubnet(var.network_cidr, 8, 1)")]
            if self.config.architecture_type == "virtual_machine"
            else ["10.0.1.0/24"],
        }
        if self.config.architecture_type == "secure_database":
            self._azure_database(common, subnet)
            return
        self.resource("azurerm_subnet", **subnet)
        standalone = self.config.architecture_type == "virtual_machine"
        self.variable(
            "admin_username",
            "Linux administrator username: 3–32 lowercase letters, digits, underscores or hyphens. Start with a letter and end with a letter or digit. Azure reserved names are rejected; password authentication stays disabled.",
            "terraforma",
            pattern=r"^[a-z][a-z0-9_\-]{1,30}[a-z0-9]$",
            forbidden_values=AZURE_RESERVED_USERNAMES,
        )
        self.variable(
            "ssh_public_key",
            "Administrator SSH public key for the selected user. Keep the matching private key outside this project."
            if standalone
            else "Administrator SSH public key. SSH is not exposed by the generated firewall.",
        )
        if not standalone:
            self.variable(
                "allowed_cidr",
                "Clients allowed to access HTTP.",
                "0.0.0.0/0" if self.config.is_public else "10.0.0.0/16",
            )
        self.resource(
            "azurerm_network_security_group",
            name=ref('"${var.project_name}-nsg"'),
            children=[
                block(
                    "security_rule",
                    name="SSH" if standalone else "HTTP",
                    priority=100,
                    direction="Inbound",
                    access="Allow",
                    protocol="Tcp",
                    source_port_range="*",
                    destination_port_range="22" if standalone else "80",
                    source_address_prefix=ref("var.allowed_cidr"),
                    destination_address_prefix="*",
                )
            ]
            + (
                [
                    block(
                        "security_rule",
                        name="DenyOtherInbound",
                        priority=4096,
                        direction="Inbound",
                        access="Deny",
                        protocol="*",
                        source_port_range="*",
                        destination_port_range="*",
                        source_address_prefix="*",
                        destination_address_prefix="*",
                    )
                ]
                if standalone
                else []
            ),
            **common,
        )
        self.resource(
            "azurerm_subnet_network_security_group_association",
            subnet_id=ref("azurerm_subnet.this.id"),
            network_security_group_id=ref("azurerm_network_security_group.this.id"),
        )
        self.resource(
            "azurerm_public_ip",
            "egress",
            name=ref('"${var.project_name}-egress"'),
            allocation_method="Static",
            sku="Standard",
            **common,
        )
        self.resource(
            "azurerm_nat_gateway",
            name=ref('"${var.project_name}-nat"'),
            sku_name="Standard",
            **common,
        )
        self.resource(
            "azurerm_nat_gateway_public_ip_association",
            nat_gateway_id=ref("azurerm_nat_gateway.this.id"),
            public_ip_address_id=ref("azurerm_public_ip.egress.id"),
        )
        self.resource(
            "azurerm_subnet_nat_gateway_association",
            subnet_id=ref("azurerm_subnet.this.id"),
            nat_gateway_id=ref("azurerm_nat_gateway.this.id"),
        )
        balanced = self.config.architecture_type == "load_balanced_tier"
        if self.config.is_public:
            self.resource(
                "azurerm_public_ip",
                "web",
                name=ref('"${var.project_name}-web"'),
                allocation_method="Static",
                sku="Standard",
                **common,
            )
        self.variable(
            "vm_size",
            "Azure VM size; availability and encryption-at-host support require account preflight.",
            "Standard_B1s",
        )
        self.variable(
            "boot_disk_size_gb",
            "OS disk size in GiB; cannot be smaller than the selected image.",
            30,
            type_name="number",
            minimum=30,
            maximum=2048,
        )
        self.variable(
            "boot_disk_type",
            "Azure managed OS disk class.",
            "Standard_LRS",
            choices=("Standard_LRS", "StandardSSD_LRS", "Premium_LRS"),
        )
        disk = block(
            "os_disk",
            caching="ReadWrite",
            storage_account_type=ref("var.boot_disk_type"),
            disk_size_gb=ref("var.boot_disk_size_gb"),
        )
        if standalone:
            self.variable(
                "enable_accelerated_networking",
                "Enable accelerated networking on the VM's network interface for supported Azure VM sizes and Linux images. This can reduce latency and CPU overhead; it does not change firewall access. Leave it off unless the selected size supports it. Changing an existing VM's setting can require stopping and deallocating the VM; this generator does not perform that operation. The optional VM-size metadata check can report support, but does not prove guest-driver compatibility or capacity.",
                False,
                type_name="bool",
            )
            self.variable(
                "enable_secure_boot",
                "Enable Azure Trusted Launch Secure Boot for the selected Gen2 Ubuntu image. vTPM stays enabled. Unsigned kernel drivers can prevent booting; check VM-size support and workload compatibility before deployment. This recipe does not configure guest attestation or Defender monitoring.",
                True,
                type_name="bool",
            )
            self.variable(
                "enable_boot_diagnostics",
                "Capture boot console output and screenshots in Azure-managed diagnostic storage for startup troubleshooting. Managed diagnostic blobs are currently not billed by Azure; verify current pricing. Retention is not configurable and logs are overwritten above 1 GB. Console output can contain sensitive data; restrict cloud access and avoid writing secrets to the console. This does not configure application logs, alerts or guest attestation, and no custom storage account or public log URL is created by this recipe.",
                False,
                type_name="bool",
            )
        self.variable(
            "image_version",
            "Azure marketplace image version for the selected Canonical offer/SKU. Use latest to resolve at planning time, or an exact Major.Minor.Build version to pin the image. A version number does not prove availability or compatibility; check the selected image and location before planning. Changing a VM image can replace the VM and destroy its boot-disk data. Custom publishers and gallery images are unsupported.",
            "latest",
            pattern=r"^(latest|[0-9]{1,10}\.[0-9]{1,10}\.[0-9]{1,10})$",
        )
        image = block(
            "source_image_reference",
            publisher="Canonical",
            offer=ref(
                'var.os_image == "ubuntu-22.04" ? "0001-com-ubuntu-server-jammy" : "ubuntu-24_04-lts"'
            ),
            sku=ref('var.os_image == "ubuntu-22.04" ? "22_04-lts-gen2" : "server"'),
            version=ref("var.image_version"),
        )
        key = block(
            "admin_ssh_key",
            username=ref("var.admin_username"),
            public_key=ref("var.ssh_public_key"),
        )
        startup = "#cloud-config\npackage_update: true\npackages:\n  - nginx\nruncmd:\n  - [systemctl, enable, --now, nginx]\n"
        compute = {
            "name": ref("var.project_name"),
            "admin_username": ref("var.admin_username"),
            "disable_password_authentication": True,
            "custom_data": ref(f"base64encode({value_hcl(startup)})"),
            "encryption_at_host_enabled": self.config.enable_encryption,
            "depends_on": [
                ref("azurerm_subnet_nat_gateway_association.this"),
                ref("azurerm_nat_gateway_public_ip_association.this"),
                ref("azurerm_subnet_network_security_group_association.this"),
            ],
            **common,
        }
        if standalone:
            compute.pop("custom_data")
        if balanced:
            frontend = {"name": "frontend"}
            if self.config.is_public:
                frontend["public_ip_address_id"] = ref("azurerm_public_ip.web.id")
            else:
                frontend.update(
                    subnet_id=ref("azurerm_subnet.this.id"), private_ip_address_allocation="Dynamic"
                )
            self.resource(
                "azurerm_lb",
                name=ref('"${var.project_name}-lb"'),
                sku="Standard",
                children=[block("frontend_ip_configuration", **frontend)],
                **common,
            )
            self.resource(
                "azurerm_lb_backend_address_pool",
                name="web",
                loadbalancer_id=ref("azurerm_lb.this.id"),
            )
            self.resource(
                "azurerm_lb_probe",
                name="http",
                loadbalancer_id=ref("azurerm_lb.this.id"),
                protocol="Http",
                port=80,
                request_path="/",
            )
            self.resource(
                "azurerm_lb_rule",
                name="http",
                loadbalancer_id=ref("azurerm_lb.this.id"),
                protocol="Tcp",
                frontend_port=80,
                backend_port=80,
                frontend_ip_configuration_name="frontend",
                backend_address_pool_ids=[ref("azurerm_lb_backend_address_pool.this.id")],
                probe_id=ref("azurerm_lb_probe.this.id"),
            )
            ip = block(
                "ip_configuration",
                name="internal",
                primary=True,
                subnet_id=ref("azurerm_subnet.this.id"),
                load_balancer_backend_address_pool_ids=[
                    ref("azurerm_lb_backend_address_pool.this.id")
                ],
            )
            self.resource(
                "azurerm_linux_virtual_machine_scale_set",
                sku=ref("var.vm_size"),
                instances=ref("var.instance_count"),
                children=[
                    disk,
                    image,
                    key,
                    block("network_interface", name="internal", primary=True, children=[ip]),
                ],
                **compute,
            )
            endpoint = (
                "azurerm_public_ip.web.ip_address"
                if self.config.is_public
                else "azurerm_lb.this.private_ip_address"
            )
        else:
            ip = {
                "name": "internal",
                "subnet_id": ref("azurerm_subnet.this.id"),
                "private_ip_address_allocation": "Dynamic",
            }
            if standalone:
                ip["private_ip_address_allocation"] = ref(
                    'var.private_ip_address == "" ? "Dynamic" : "Static"'
                )
                ip["private_ip_address"] = ref(
                    'var.private_ip_address == "" ? null : var.private_ip_address'
                )
            if self.config.is_public:
                ip["public_ip_address_id"] = ref("azurerm_public_ip.web.id")
            self.resource(
                "azurerm_network_interface",
                name=ref('"${var.project_name}-nic"'),
                **(
                    {"accelerated_networking_enabled": ref("var.enable_accelerated_networking")}
                    if standalone
                    else {}
                ),
                children=[block("ip_configuration", **ip)],
                **common,
            )
            self.resource(
                "azurerm_linux_virtual_machine",
                size=ref("var.vm_size"),
                network_interface_ids=[ref("azurerm_network_interface.this.id")],
                **(
                    {"secure_boot_enabled": ref("var.enable_secure_boot"), "vtpm_enabled": True}
                    if standalone
                    else {}
                ),
                children=[disk, image, key]
                + (
                    [block("lifecycle", children=[self._private_ip_precondition()])]
                    if standalone
                    else []
                )
                + (
                    [
                        block(
                            "dynamic",
                            "boot_diagnostics",
                            for_each=ref("var.enable_boot_diagnostics ? [1] : []"),
                            children=[block("content", storage_account_uri=None)],
                        )
                    ]
                    if standalone
                    else []
                )
                + (
                    [
                        block(
                            "dynamic",
                            "identity",
                            for_each=ref("var.enable_workload_identity ? [1] : []"),
                            children=[block("content", type="SystemAssigned")],
                        )
                    ]
                    if standalone
                    else []
                ),
                **compute,
            )
            endpoint = (
                "azurerm_public_ip.web.ip_address"
                if self.config.is_public
                else "azurerm_network_interface.this.private_ip_address"
            )
        if standalone:
            self.output(
                "managed_identity_principal_id",
                "var.enable_workload_identity ? azurerm_linux_virtual_machine.this.identity[0].principal_id : null",
                "Optional system-assigned identity principal. No role assignments are created; the identity is removed with the VM.",
            )
            self.resource(
                "azurerm_managed_disk",
                "data",
                count=ref("var.enable_data_disk ? 1 : 0"),
                name=ref('"${var.project_name}-data"'),
                create_option="Empty",
                disk_size_gb=ref("var.data_disk_size_gb"),
                storage_account_type=ref("var.data_disk_type"),
                **common,
            )
            self.resource(
                "azurerm_virtual_machine_data_disk_attachment",
                "data",
                count=ref("var.enable_data_disk ? 1 : 0"),
                managed_disk_id=ref("azurerm_managed_disk.data[0].id"),
                virtual_machine_id=ref("azurerm_linux_virtual_machine.this.id"),
                lun=0,
                caching="None",
            )
            self.output(
                "data_disk_id",
                "var.enable_data_disk ? azurerm_managed_disk.data[0].id : null",
                "Optional empty data disk ID, attached at LUN 0. Formatting, mounting, backups and recovery are not configured.",
            )
        if standalone:
            self.output(
                "vm_id",
                "azurerm_linux_virtual_machine.this.id",
                "Azure VM resource ID for cloud operations; available after provisioning.",
            )
            self.output(
                "vm_name",
                "azurerm_linux_virtual_machine.this.name",
                "Azure VM name within its resource group.",
            )
            self.output(
                "vm_location",
                "azurerm_linux_virtual_machine.this.location",
                "Azure VM location; this recipe does not select an availability zone.",
            )
            self.output(
                "vm_resource_group",
                "azurerm_resource_group.this.name",
                "Azure resource group name used with the VM name for cloud operations.",
            )
            self.output(
                "vm_address",
                endpoint,
                "VM IPv4 address; SSH requires the allowed client network and matching private key.",
            )
            self.output(
                "ssh_username",
                "var.admin_username",
                "Administrator username; password authentication is disabled.",
            )
        else:
            self.output("endpoint", f'"http://${{{endpoint}}}"', "Web workload HTTP endpoint.")

    def _azure_database(self, common: dict, subnet: dict) -> None:
        self.variable(
            "database_password",
            "PostgreSQL administrator password; supply through TF_VAR_database_password.",
            sensitive=True,
        )
        attributes = {
            "name": ref("var.project_name"),
            "version": "16",
            "administrator_login": "terraforma",
            "administrator_password": ref("var.database_password"),
            "storage_mb": 32768,
            "sku_name": "GP_Standard_D2s_v3",
            "backup_retention_days": 7,
            "public_network_access_enabled": self.config.is_public,
            **common,
        }
        if not self.config.is_public:
            self.resource(
                "azurerm_subnet",
                children=[
                    block(
                        "delegation",
                        name="postgres",
                        children=[
                            block(
                                "service_delegation",
                                name="Microsoft.DBforPostgreSQL/flexibleServers",
                                actions=["Microsoft.Network/virtualNetworks/subnets/join/action"],
                            )
                        ],
                    )
                ],
                **subnet,
            )
            self.resource(
                "azurerm_private_dns_zone",
                name=ref('"${var.project_name}.postgres.database.azure.com"'),
                resource_group_name=common["resource_group_name"],
            )
            self.resource(
                "azurerm_private_dns_zone_virtual_network_link",
                name="postgres",
                resource_group_name=common["resource_group_name"],
                private_dns_zone_name=ref("azurerm_private_dns_zone.this.name"),
                virtual_network_id=ref("azurerm_virtual_network.this.id"),
            )
            attributes.update(
                delegated_subnet_id=ref("azurerm_subnet.this.id"),
                private_dns_zone_id=ref("azurerm_private_dns_zone.this.id"),
                depends_on=[ref("azurerm_private_dns_zone_virtual_network_link.this")],
            )
        self.resource(
            "azurerm_postgresql_flexible_server",
            children=[
                block("high_availability", mode="SameZone"),
                block("lifecycle", prevent_destroy=True),
            ],
            **attributes,
        )
        if self.config.is_public:
            self.variable(
                "database_client_ip",
                "Single public IPv4 client permitted by the database firewall.",
                network_policy="database_address",
            )
            self.resource(
                "azurerm_postgresql_flexible_server_firewall_rule",
                name="client",
                server_id=ref("azurerm_postgresql_flexible_server.this.id"),
                start_ip_address=ref("var.database_client_ip"),
                end_ip_address=ref("var.database_client_ip"),
            )
        self.output(
            "database_endpoint",
            "azurerm_postgresql_flexible_server.this.fqdn",
            "PostgreSQL hostname; connect with TLS.",
        )

    def _azure_static(self, common: dict) -> None:
        self.variable(
            "index_html",
            "Initial website HTML.",
            "<html><body><h1>TerraForma-IaC</h1></body></html>",
        )
        self.resource("random_id", "suffix", byte_length=4)
        self.resource(
            "azurerm_storage_account",
            name=ref(
                '"${substr(replace(var.project_name, "-", ""), 0, 16)}${random_id.suffix.hex}"'
            ),
            account_tier="Standard",
            account_replication_type="LRS",
            min_tls_version="TLS1_2",
            allow_nested_items_to_be_public=self.config.is_public,
            **common,
        )
        if self.config.is_public:
            self.resource(
                "azurerm_storage_account_static_website",
                storage_account_id=ref("azurerm_storage_account.this.id"),
                index_document="index.html",
            )
            container = '"$web"'
        else:
            self.resource(
                "azurerm_storage_container",
                name="site",
                storage_account_id=ref("azurerm_storage_account.this.id"),
                container_access_type="private",
            )
            container = "azurerm_storage_container.this.name"
        self.resource(
            "azurerm_storage_blob",
            name="index.html",
            storage_account_name=ref("azurerm_storage_account.this.name"),
            storage_container_name=ref(container),
            type="Block",
            source_content=ref("var.index_html"),
            content_type="text/html",
            **(
                {"depends_on": [ref("azurerm_storage_account_static_website.this")]}
                if self.config.is_public
                else {}
            ),
        )
        endpoint = (
            "azurerm_storage_account.this.primary_web_endpoint"
            if self.config.is_public
            else '"${azurerm_storage_account.this.primary_blob_endpoint}site/index.html"'
        )
        self.output(
            "endpoint", endpoint, "Website endpoint; private objects require authenticated access."
        )

    def _gcp(self) -> None:
        self.variable("gcp_project_id", "Existing Google Cloud project ID with billing enabled.")
        self.variable("region", "Google Cloud region.", "us-central1")
        self.main.append(
            block("provider", "google", project=ref("var.gcp_project_id"), region=ref("var.region"))
        )
        if self.config.architecture_type == "static_site":
            self._gcp_static()
            return
        self.resource(
            "google_project_service",
            "compute",
            service="compute.googleapis.com",
            disable_on_destroy=False,
        )
        self.resource(
            "google_compute_network",
            name=ref("var.project_name"),
            auto_create_subnetworks=False,
            depends_on=[ref("google_project_service.compute")],
        )
        self.resource(
            "google_compute_subnetwork",
            name=ref("var.project_name"),
            ip_cidr_range=ref("var.network_cidr")
            if self.config.architecture_type == "virtual_machine"
            else "10.0.1.0/24",
            region=ref("var.region"),
            network=ref("google_compute_network.this.id"),
            private_ip_google_access=True,
        )
        if self.config.architecture_type == "secure_database":
            self._gcp_database()
            return
        self.variable("zone", "Compute zone in the chosen region.", "us-central1-a")
        standalone = self.config.architecture_type == "virtual_machine"
        if standalone:
            self.variable(
                "protect_vm",
                "Enable Google Compute Engine VM deletion protection. Turn this off and apply that change before intentionally deleting or replacing the VM. This is not a backup and does not protect the whole project from deletion.",
                True,
                type_name="bool",
            )
        if not standalone:
            self.variable(
                "allowed_cidr",
                "Clients allowed to access HTTP.",
                "0.0.0.0/0" if self.config.is_public else "10.0.0.0/16",
            )
        self.resource(
            "google_compute_firewall",
            name=ref('"${var.project_name}-ssh"' if standalone else '"${var.project_name}-http"'),
            network=ref("google_compute_network.this.name"),
            source_ranges=[ref("var.allowed_cidr")]
            if standalone
            else [ref("var.allowed_cidr"), "35.191.0.0/16", "130.211.0.0/22"],
            target_tags=["terraforma-web"],
            children=[block("allow", protocol="tcp", ports=["22" if standalone else "80"])],
        )
        self.resource(
            "google_compute_router",
            name=ref("var.project_name"),
            region=ref("var.region"),
            network=ref("google_compute_network.this.id"),
        )
        self.resource(
            "google_compute_router_nat",
            name=ref("var.project_name"),
            router=ref("google_compute_router.this.name"),
            region=ref("var.region"),
            nat_ip_allocate_option="AUTO_ONLY",
            source_subnetwork_ip_ranges_to_nat="ALL_SUBNETWORKS_ALL_IP_RANGES",
        )
        startup = "#!/bin/bash\nset -eu\napt-get update\napt-get install -y nginx\nsystemctl enable --now nginx\n"
        balanced = self.config.architecture_type == "load_balanced_tier"
        network = block(
            "network_interface",
            subnetwork=ref("google_compute_subnetwork.this.id"),
            **(
                {"network_ip": ref('var.private_ip_address == "" ? null : var.private_ip_address')}
                if standalone
                else {}
            ),
            children=[block("access_config")] if self.config.is_public and not balanced else [],
        )
        self.variable(
            "machine_type",
            "Google Compute Engine machine type; zone availability requires account preflight.",
            "e2-micro",
        )
        self.variable(
            "boot_disk_size_gb",
            "Boot disk size in GiB; review image requirements and storage cost.",
            20,
            type_name="number",
            minimum=20,
            maximum=2048,
        )
        self.variable(
            "boot_disk_type",
            "Google persistent boot disk class.",
            "pd-balanced",
            choices=("pd-balanced", "pd-standard", "pd-ssd"),
        )
        self.variable(
            "image_version",
            "Use latest to resolve the selected GCP image family at planning time, or enter an exact published Debian 12 Bookworm / Ubuntu 24.04 Noble AMD64 image name. The publisher project stays fixed. Verify availability, deprecation and compatibility before planning. Changing the image can replace a VM and destroy boot-disk data; pinning does not apply security patches automatically.",
            "latest",
            pattern=r"^(latest|debian-12-bookworm-v[0-9]{8}|ubuntu-2404-noble(-amd64)?-v[0-9]{8})$",
        )
        image_source = ref(
            'var.image_version == "latest" ? '
            '(var.os_image == "debian-12" ? "debian-cloud/debian-12" : "ubuntu-os-cloud/ubuntu-2404-lts-amd64") : '
            '(var.os_image == "debian-12" ? "debian-cloud/${var.image_version}" : "ubuntu-os-cloud/${var.image_version}")'
        )
        image_lifecycle = block(
            "lifecycle",
            children=[
                block(
                    "precondition",
                    condition=ref(
                        'var.image_version == "latest" || '
                        '(var.os_image == "debian-12" ? startswith(var.image_version, "debian-12-bookworm-v") : startswith(var.image_version, "ubuntu-2404-noble"))'
                    ),
                    error_message="Choose an exact image name matching the selected Linux operating system.",
                )
            ]
            + (self._identity_precondition().children if standalone else []),
        )
        disk = block(
            "boot_disk",
            children=[
                block(
                    "initialize_params",
                    image=image_source,
                    size=ref("var.boot_disk_size_gb"),
                    type=ref("var.boot_disk_type"),
                )
            ],
        )
        if standalone:
            self.variable(
                "enable_secure_boot",
                "Verify signed boot components with Google Shielded VM Secure Boot. Unsigned kernel modules or drivers can prevent booting; review workload compatibility before changing this setting. Changing Shielded VM options requires a stopped VM; automatic stopping is disabled. vTPM and integrity monitoring remain enabled.",
                True,
                type_name="bool",
            )
            self.resource(
                "google_compute_disk",
                "data",
                count=ref("var.enable_data_disk ? 1 : 0"),
                name=ref('"${var.project_name}-data"'),
                zone=ref("var.zone"),
                size=ref("var.data_disk_size_gb"),
                type=ref("var.data_disk_type"),
                labels={"environment": ref("var.environment"), "managed_by": "terraforma"},
                depends_on=[ref("google_project_service.compute")],
            )
            self.output(
                "data_disk_id",
                "var.enable_data_disk ? google_compute_disk.data[0].id : null",
                "Optional empty persistent disk ID, attached as data-disk. Formatting, mounting, backups and recovery are not configured.",
            )
        if balanced:
            self.resource(
                "google_compute_instance_template",
                name_prefix=ref('"${var.project_name}-"'),
                labels={"environment": ref("var.environment"), "managed_by": "terraforma"},
                machine_type=ref("var.machine_type"),
                tags=["terraforma-web"],
                metadata_startup_script=startup,
                metadata={"serial-port-enable": "FALSE"},
                children=[
                    block(
                        "disk",
                        source_image=image_source,
                        auto_delete=True,
                        boot=True,
                        disk_size_gb=ref("var.boot_disk_size_gb"),
                        disk_type=ref("var.boot_disk_type"),
                    ),
                    network,
                    image_lifecycle,
                ],
            )
            self.resource(
                "google_compute_instance_group_manager",
                name=ref("var.project_name"),
                base_instance_name=ref("var.project_name"),
                zone=ref("var.zone"),
                target_size=ref("var.instance_count"),
                children=[
                    block(
                        "version", instance_template=ref("google_compute_instance_template.this.id")
                    ),
                    block("named_port", name="http", port=80),
                ],
                depends_on=[ref("google_compute_router_nat.this")],
            )
            if self.config.is_public:
                self.resource(
                    "google_compute_health_check",
                    name=ref("var.project_name"),
                    children=[block("http_health_check", port=80)],
                )
                self.resource(
                    "google_compute_backend_service",
                    name=ref("var.project_name"),
                    protocol="HTTP",
                    port_name="http",
                    health_checks=[ref("google_compute_health_check.this.id")],
                    children=[
                        block(
                            "backend",
                            group=ref("google_compute_instance_group_manager.this.instance_group"),
                        )
                    ],
                )
                self.resource(
                    "google_compute_url_map",
                    name=ref("var.project_name"),
                    default_service=ref("google_compute_backend_service.this.id"),
                )
                self.resource(
                    "google_compute_target_http_proxy",
                    name=ref("var.project_name"),
                    url_map=ref("google_compute_url_map.this.id"),
                )
                self.resource(
                    "google_compute_global_forwarding_rule",
                    name=ref("var.project_name"),
                    target=ref("google_compute_target_http_proxy.this.id"),
                    port_range="80",
                )
                endpoint = "google_compute_global_forwarding_rule.this.ip_address"
            else:
                self.resource(
                    "google_compute_region_health_check",
                    name=ref("var.project_name"),
                    region=ref("var.region"),
                    children=[block("tcp_health_check", port=80)],
                )
                self.resource(
                    "google_compute_region_backend_service",
                    name=ref("var.project_name"),
                    region=ref("var.region"),
                    protocol="TCP",
                    load_balancing_scheme="INTERNAL",
                    health_checks=[ref("google_compute_region_health_check.this.id")],
                    children=[
                        block(
                            "backend",
                            group=ref("google_compute_instance_group_manager.this.instance_group"),
                            balancing_mode="CONNECTION",
                        )
                    ],
                )
                self.resource(
                    "google_compute_forwarding_rule",
                    name=ref("var.project_name"),
                    region=ref("var.region"),
                    load_balancing_scheme="INTERNAL",
                    network=ref("google_compute_network.this.id"),
                    subnetwork=ref("google_compute_subnetwork.this.id"),
                    backend_service=ref("google_compute_region_backend_service.this.id"),
                    ports=["80"],
                )
                endpoint = "google_compute_forwarding_rule.this.ip_address"
        else:
            self.resource(
                "google_compute_instance",
                name=ref("var.project_name"),
                **({"deletion_protection": ref("var.protect_vm")} if standalone else {}),
                labels={"environment": ref("var.environment"), "managed_by": "terraforma"},
                machine_type=ref("var.machine_type"),
                zone=ref("var.zone"),
                **({"allow_stopping_for_update": False} if standalone else {}),
                tags=["terraforma-web"],
                **(
                    {
                        "metadata": {
                            "enable-oslogin": "TRUE",
                            "block-project-ssh-keys": "TRUE",
                            "serial-port-enable": "FALSE",
                        }
                    }
                    if standalone
                    else {
                        "metadata_startup_script": startup,
                        "metadata": {"serial-port-enable": "FALSE"},
                    }
                ),
                children=[disk, network, image_lifecycle]
                + (
                    [
                        block(
                            "shielded_instance_config",
                            enable_secure_boot=ref("var.enable_secure_boot"),
                            enable_vtpm=True,
                            enable_integrity_monitoring=True,
                        ),
                        block(
                            "dynamic",
                            "service_account",
                            for_each=ref(
                                "var.enable_workload_identity ? [var.workload_identity] : []"
                            ),
                            children=[
                                block(
                                    "content",
                                    email=ref("service_account.value"),
                                    scopes=["cloud-platform"],
                                )
                            ],
                        ),
                    ]
                    if standalone
                    else []
                )
                + (
                    [
                        block(
                            "dynamic",
                            "attached_disk",
                            for_each=ref(
                                "var.enable_data_disk ? [google_compute_disk.data[0].id] : []"
                            ),
                            children=[
                                block(
                                    "content",
                                    source=ref("attached_disk.value"),
                                    device_name="data-disk",
                                    mode="READ_WRITE",
                                )
                            ],
                        )
                    ]
                    if standalone
                    else []
                ),
                depends_on=[ref("google_compute_router_nat.this")],
            )
            endpoint = (
                "google_compute_instance.this.network_interface[0].access_config[0].nat_ip"
                if self.config.is_public
                else "google_compute_instance.this.network_interface[0].network_ip"
            )
        if standalone:
            self.output(
                "vm_id",
                "google_compute_instance.this.id",
                "GCP VM resource path for cloud operations; available after provisioning.",
            )
            self.output(
                "vm_name",
                "google_compute_instance.this.name",
                "GCP instance name within its project and zone.",
            )
            self.output(
                "vm_location",
                "google_compute_instance.this.zone",
                "GCP compute zone; project ID is supplied in the project inputs.",
            )
            self.output(
                "vm_address",
                endpoint,
                "VM IPv4 address; use OS Login with the required IAM role and allowed client network. Private VMs require routed access.",
            )
        else:
            self.output("endpoint", f'"http://${{{endpoint}}}"', "Web workload HTTP endpoint.")

    def _gcp_database(self) -> None:
        self.variable(
            "database_password",
            "PostgreSQL user password; supply through TF_VAR_database_password.",
            sensitive=True,
        )
        self.resource(
            "google_project_service",
            "sql",
            service="sqladmin.googleapis.com",
            disable_on_destroy=False,
        )
        self.resource(
            "google_project_service",
            "networking",
            service="servicenetworking.googleapis.com",
            disable_on_destroy=False,
        )
        self.resource(
            "google_compute_global_address",
            name=ref('"${var.project_name}-sql"'),
            purpose="VPC_PEERING",
            address_type="INTERNAL",
            prefix_length=16,
            network=ref("google_compute_network.this.id"),
        )
        self.resource(
            "google_service_networking_connection",
            network=ref("google_compute_network.this.id"),
            service="servicenetworking.googleapis.com",
            reserved_peering_ranges=[ref("google_compute_global_address.this.name")],
            depends_on=[ref("google_project_service.networking")],
        )
        ip = {
            "ipv4_enabled": self.config.is_public,
            "private_network": ref("google_compute_network.this.id"),
            "ssl_mode": "ENCRYPTED_ONLY",
        }
        allowed = []
        if self.config.is_public:
            self.variable(
                "allowed_cidr",
                "IPv4 client network permitted to connect to the database.",
                network_policy="database_cidr",
            )
            allowed.append(
                block("authorized_networks", name="client", value=ref("var.allowed_cidr"))
            )
        settings = block(
            "settings",
            tier="db-custom-2-7680",
            user_labels={"environment": ref("var.environment"), "managed_by": "terraforma"},
            availability_type="REGIONAL",
            disk_size=20,
            children=[
                block("backup_configuration", enabled=True, point_in_time_recovery_enabled=True),
                block("ip_configuration", children=allowed, **ip),
            ],
        )
        self.resource(
            "google_sql_database_instance",
            name=ref("var.project_name"),
            region=ref("var.region"),
            database_version="POSTGRES_16",
            deletion_protection=True,
            children=[settings],
            depends_on=[
                ref("google_service_networking_connection.this"),
                ref("google_project_service.sql"),
            ],
        )
        self.resource(
            "google_sql_database",
            name="app",
            instance=ref("google_sql_database_instance.this.name"),
        )
        self.resource(
            "google_sql_user",
            name="terraforma",
            instance=ref("google_sql_database_instance.this.name"),
            password=ref("var.database_password"),
        )
        self.output(
            "database_endpoint",
            "google_sql_database_instance.this.connection_name",
            "Cloud SQL connection name; use Cloud SQL Auth Proxy or private networking.",
        )

    def _gcp_static(self) -> None:
        self.variable(
            "index_html",
            "Initial website HTML.",
            "<html><body><h1>TerraForma-IaC</h1></body></html>",
        )
        self.resource("random_id", "suffix", byte_length=4)
        self.resource(
            "google_storage_bucket",
            name=ref('"${var.gcp_project_id}-${var.project_name}-${random_id.suffix.hex}"'),
            labels={"environment": ref("var.environment"), "managed_by": "terraforma"},
            location=ref("var.region"),
            uniform_bucket_level_access=True,
            public_access_prevention="inherited" if self.config.is_public else "enforced",
            children=[
                block("versioning", enabled=True),
                block("website", main_page_suffix="index.html"),
            ],
        )
        self.resource(
            "google_storage_bucket_object",
            name="index.html",
            bucket=ref("google_storage_bucket.this.name"),
            content=ref("var.index_html"),
            content_type="text/html",
        )
        if self.config.is_public:
            self.resource(
                "google_storage_bucket_iam_member",
                bucket=ref("google_storage_bucket.this.name"),
                role="roles/storage.objectViewer",
                member="allUsers",
            )
            endpoint = (
                '"https://storage.googleapis.com/${google_storage_bucket.this.name}/index.html"'
            )
        else:
            endpoint = '"gs://${google_storage_bucket.this.name}/index.html"'
        self.output(
            "endpoint",
            endpoint,
            "Site object endpoint; organization policy may forbid public access.",
        )


GENERATED_FILENAMES = frozenset(
    {
        ".gitignore",
        "main.tf",
        "variables.tf",
        "outputs.tf",
        "terraforma.project.json",
        "terraforma.receipt.json",
        "SHA256SUMS.txt",
    }
)


def project_destination(directory: str | Path) -> Path:
    destination = Path(directory).resolve()
    if any(
        any(destination.glob(pattern))
        for pattern in (
            "*.tf",
            "*.tf.json",
            "*.tfvars",
            "*.tfvars.json",
            "*.tfstate",
            "*.tfstate.*",
        )
    ) or any(
        (destination / name).exists() or (destination / name).is_symlink()
        for name in (".terraform", ".terraform.lock.hcl")
    ):
        raise ValueError(
            "The destination already contains Terraform configuration, state, variable files, or initialization data. Choose a fresh project directory."
        )
    if any(
        (destination / name).exists() or (destination / name).is_symlink()
        for name in GENERATED_FILENAMES
    ):
        raise FileExistsError(
            "The destination already contains generated artifacts. Choose a fresh project directory."
        )
    return destination


def write_configuration(files: dict[str, str], directory: str | Path) -> Path:
    if not files or not set(files) <= GENERATED_FILENAMES:
        raise ValueError("Unexpected or empty generated filename set.")
    destination = project_destination(directory)
    destination.mkdir(mode=0o700, parents=True, exist_ok=True)
    created: list[Path] = []
    try:
        for name, content in files.items():
            path = destination / name
            with open(
                path,
                "x",
                encoding="utf-8",
                newline="\n",
                opener=lambda name, flags: os.open(name, flags, 0o600),
            ) as stream:
                created.append(path)
                stream.write(content)
    except BaseException:
        for path in created:
            path.unlink(missing_ok=True)
        raise
    return destination
