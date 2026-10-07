import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field


class WizardConfig(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    provider: Literal["aws", "azure", "gcp"]
    project_name: str = Field(pattern=r"^[a-z][a-z0-9-]{1,18}[a-z0-9]$")
    architecture_type: Literal[
        "single_web_server", "load_balanced_tier", "secure_database", "static_site"
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
        choices: tuple[str, ...] | None = None,
        pattern: str | None = None,
        network_policy: Literal["database_cidr", "database_address"] | None = None,
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
            validations.append(
                block(
                    "validation",
                    condition=ref(f"can(regex({value_hcl(pattern)}, var.{name}))"),
                    error_message="Use the required identifier format for this field.",
                )
            )
        if network_policy:
            address = f"var.{name}"
            if network_policy == "database_cidr":
                prefix = f'tonumber(split("/", {address})[1])'
                network = f"cidrhost({address}, 0)"
                private_172 = value_hcl(r"^172\.(1[6-9]|2[0-9]|3[01])\.")
                condition = (
                    f"can(cidrnetmask({address})) && try("
                    f"{prefix} >= 24 || "
                    f'(startswith({network}, "10.") && {prefix} >= 8) || '
                    f"(can(regex({private_172}, {network})) && {prefix} >= 12) || "
                    f'(startswith({network}, "192.168.") && {prefix} >= 16), false)'
                )
                message = "Use an RFC1918 private network or an IPv4 /24 through /32 client network; prefer /32 for one client."
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
            "choices": list(choices) if choices else None,
            "pattern": pattern,
            "network_policy": network_policy,
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
            pattern=r"^[a-z][a-z0-9-]{1,18}[a-z0-9]$",
        )
        getattr(self, f"_{self.config.provider}")()
        return {
            "main.tf": "\n\n".join(item.render() for item in self.main) + "\n",
            "variables.tf": "\n\n".join(item.render() for item in self.variables) + "\n",
            "outputs.tf": "\n\n".join(item.render() for item in self.outputs) + "\n",
        }

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
            cidr_block="10.0.0.0/16",
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
            from_port=80,
            to_port=80,
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
        self.main.append(
            block(
                "data",
                "aws_ami",
                "linux",
                most_recent=True,
                owners=["amazon"],
                children=[
                    block("filter", name="name", values=["al2023-ami-2023.*-x86_64"]),
                    block("filter", name="virtualization-type", values=["hvm"]),
                ],
            )
        )
        self.variable("instance_type", "EC2 instance size.", "t3.micro")
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
        self.resource(
            "aws_instance",
            "web",
            count=2 if balanced else 1,
            ami=ref("data.aws_ami.linux.id"),
            instance_type=ref("var.instance_type"),
            subnet_id=ref(f"aws_subnet.{'private' if private else 'public'}[count.index % 2].id"),
            associate_public_ip_address=not private,
            vpc_security_group_ids=[ref("aws_security_group.web.id")],
            user_data="#!/bin/bash\nset -eu\ndnf install -y nginx\nsystemctl enable --now nginx\n",
            tags={"Name": ref("var.project_name")},
            children=[
                block("root_block_device", **disk),
                block("metadata_options", http_tokens="required"),
            ],
            **({"depends_on": [ref("aws_route_table_association.private")]} if private else {}),
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
                count=2,
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
            address_space=["10.0.0.0/16"],
            **common,
        )
        subnet = {
            "name": "workload",
            "resource_group_name": common["resource_group_name"],
            "virtual_network_name": ref("azurerm_virtual_network.this.name"),
            "address_prefixes": ["10.0.1.0/24"],
        }
        if self.config.architecture_type == "secure_database":
            self._azure_database(common, subnet)
            return
        self.resource("azurerm_subnet", **subnet)
        self.variable(
            "ssh_public_key",
            "Administrator SSH public key. SSH is not exposed by the generated firewall.",
        )
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
                    name="HTTP",
                    priority=100,
                    direction="Inbound",
                    access="Allow",
                    protocol="Tcp",
                    source_port_range="*",
                    destination_port_range="80",
                    source_address_prefix=ref("var.allowed_cidr"),
                    destination_address_prefix="*",
                )
            ],
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
        image = block(
            "source_image_reference",
            publisher="Canonical",
            offer="0001-com-ubuntu-server-jammy",
            sku="22_04-lts-gen2",
            version="latest",
        )
        key = block("admin_ssh_key", username="terraforma", public_key=ref("var.ssh_public_key"))
        startup = "#cloud-config\npackage_update: true\npackages:\n  - nginx\nruncmd:\n  - [systemctl, enable, --now, nginx]\n"
        compute = {
            "name": ref("var.project_name"),
            "admin_username": "terraforma",
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
                instances=2,
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
            if self.config.is_public:
                ip["public_ip_address_id"] = ref("azurerm_public_ip.web.id")
            self.resource(
                "azurerm_network_interface",
                name=ref('"${var.project_name}-nic"'),
                children=[block("ip_configuration", **ip)],
                **common,
            )
            self.resource(
                "azurerm_linux_virtual_machine",
                size=ref("var.vm_size"),
                network_interface_ids=[ref("azurerm_network_interface.this.id")],
                children=[disk, image, key],
                **compute,
            )
            endpoint = (
                "azurerm_public_ip.web.ip_address"
                if self.config.is_public
                else "azurerm_network_interface.this.private_ip_address"
            )
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
            ip_cidr_range="10.0.1.0/24",
            region=ref("var.region"),
            network=ref("google_compute_network.this.id"),
            private_ip_google_access=True,
        )
        if self.config.architecture_type == "secure_database":
            self._gcp_database()
            return
        self.variable("zone", "Compute zone in the chosen region.", "us-central1-a")
        self.variable(
            "allowed_cidr",
            "Clients allowed to access HTTP.",
            "0.0.0.0/0" if self.config.is_public else "10.0.0.0/16",
        )
        self.resource(
            "google_compute_firewall",
            name=ref('"${var.project_name}-http"'),
            network=ref("google_compute_network.this.name"),
            source_ranges=[ref("var.allowed_cidr"), "35.191.0.0/16", "130.211.0.0/22"],
            target_tags=["terraforma-web"],
            children=[block("allow", protocol="tcp", ports=["80"])],
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
        disk = block(
            "boot_disk",
            children=[
                block(
                    "initialize_params",
                    image="debian-cloud/debian-12",
                    size=ref("var.boot_disk_size_gb"),
                    type=ref("var.boot_disk_type"),
                )
            ],
        )
        if balanced:
            self.resource(
                "google_compute_instance_template",
                name_prefix=ref('"${var.project_name}-"'),
                labels={"environment": ref("var.environment"), "managed_by": "terraforma"},
                machine_type=ref("var.machine_type"),
                tags=["terraforma-web"],
                metadata_startup_script=startup,
                children=[
                    block(
                        "disk",
                        source_image="debian-cloud/debian-12",
                        auto_delete=True,
                        boot=True,
                        disk_size_gb=ref("var.boot_disk_size_gb"),
                        disk_type=ref("var.boot_disk_type"),
                    ),
                    network,
                ],
            )
            self.resource(
                "google_compute_instance_group_manager",
                name=ref("var.project_name"),
                base_instance_name=ref("var.project_name"),
                zone=ref("var.zone"),
                target_size=2,
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
                labels={"environment": ref("var.environment"), "managed_by": "terraforma"},
                machine_type=ref("var.machine_type"),
                zone=ref("var.zone"),
                tags=["terraforma-web"],
                metadata_startup_script=startup,
                children=[disk, network],
                depends_on=[ref("google_compute_router_nat.this")],
            )
            endpoint = (
                "google_compute_instance.this.network_interface[0].access_config[0].nat_ip"
                if self.config.is_public
                else "google_compute_instance.this.network_interface[0].network_ip"
            )
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
    destination.mkdir(parents=True, exist_ok=True)
    created: list[Path] = []
    try:
        for name, content in files.items():
            path = destination / name
            with path.open("x", encoding="utf-8", newline="\n") as stream:
                created.append(path)
                stream.write(content)
    except BaseException:
        for path in created:
            path.unlink(missing_ok=True)
        raise
    return destination
