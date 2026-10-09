from __future__ import annotations

from typing import TYPE_CHECKING

from terraforma.aws_network_attachment import add_aws_attachment_data
from terraforma.aws_tenancy import declare_aws_tenancy
from terraforma.custom_images import custom_image_preconditions
from terraforma.hcl import block, ref, value_hcl
from terraforma.initialization import aws_initialization_payload
from terraforma.outbound import aws_outbound_rules
from terraforma.resource_labels import resource_labels

if TYPE_CHECKING:
    from terraforma.generator import TerraformGenerator


def build_aws(builder: TerraformGenerator) -> None:
    standalone = builder.config.architecture_type in {"virtual_machine", "windows_virtual_machine"}
    builder.variable("region", "AWS region.", "us-east-1")
    builder.variable(
        "aws_account_id",
        "Target AWS account ID: 12 digits. Terraform checks this against its authenticated account before provider operations.",
        pattern="^[0-9]{12}$",
    )
    builder.main.append(
        block(
            "provider",
            "aws",
            region=ref("var.region"),
            allowed_account_ids=[ref("var.aws_account_id")],
            children=[
                block(
                    "default_tags",
                    tags=resource_labels(
                        {"Environment": ref("var.environment"), "ManagedBy": "TerraForma-IaC"}
                    )
                    if standalone
                    else {"Environment": ref("var.environment"), "ManagedBy": "TerraForma-IaC"},
                )
            ],
        )
    )
    if builder.config.architecture_type == "static_site":
        build_static(builder)
        return
    standalone = builder.config.architecture_type in {"virtual_machine", "windows_virtual_machine"}
    owned_network = {"count": ref("var.use_existing_network ? 0 : 1")} if standalone else {}
    subnet_count = ref("var.use_existing_network ? 0 : 2") if standalone else 2
    vpc_id = ref("aws_vpc.this[0].id" if standalone else "aws_vpc.this.id")
    gateway_id = ref(
        "aws_internet_gateway.this[0].id" if standalone else "aws_internet_gateway.this.id"
    )
    zone_expression = "data.aws_availability_zones.available.names[count.index]"
    zone_checks = []
    if standalone:
        builder.variable(
            "availability_zone",
            "AWS availability zone name, such as us-east-1b. For a new network, leave blank to use the first available standard zone reported for the account; the recipe creates public/private subnets in two standard zones, with the selected zone first. Existing-subnet mode inherits its zone; an entered zone must match subnet metadata. Names are account-specific; zone IDs, Local Zones and Wavelength Zones are unsupported. Changing placement can replace resources and delete disks. Optional VM metadata preflight checks a supplied zone's reported instance-type offering; capacity remains unverified. Offline generation does not check cloud availability.",
            "",
            pattern="^$|^[a-z]{2,4}(?:-[a-z0-9]+)+-[0-9]+[a-z]$",
        )
        zone_expression = (
            'var.availability_zone == "" ? data.aws_availability_zones.available.names[count.index] : '
            "concat([var.availability_zone], [for zone in data.aws_availability_zones.available.names : zone if zone != var.availability_zone])[count.index]"
        )
        zone_checks = [
            block(
                "lifecycle",
                children=[
                    block(
                        "precondition",
                        condition=ref("length(data.aws_availability_zones.available.names) >= 2"),
                        error_message="This network recipe requires two available standard AWS availability zones.",
                    ),
                    block(
                        "precondition",
                        condition=ref(
                            'var.availability_zone == "" || contains(data.aws_availability_zones.available.names, var.availability_zone)'
                        ),
                        error_message="Choose a standard availability zone available to the authenticated account in the selected region, or leave placement blank.",
                    ),
                ],
            )
        ]
    builder.main.append(
        block(
            "data",
            "aws_availability_zones",
            "available",
            state="available",
            children=[block("filter", name="opt-in-status", values=["opt-in-not-required"])]
            if standalone
            else [],
        )
    )
    builder.resource(
        "aws_vpc",
        **owned_network,
        cidr_block=ref("var.network_cidr")
        if builder.config.architecture_type in {"virtual_machine", "windows_virtual_machine"}
        else "10.0.0.0/16",
        enable_dns_support=True,
        enable_dns_hostnames=True,
        tags={"Name": ref("var.project_name")},
    )
    builder.resource(
        "aws_subnet",
        "public",
        count=subnet_count,
        vpc_id=vpc_id,
        cidr_block=ref(
            "cidrsubnet(aws_vpc.this[0].cidr_block, 8, count.index)"
            if standalone
            else "cidrsubnet(aws_vpc.this.cidr_block, 8, count.index)"
        ),
        availability_zone=ref(zone_expression),
        map_public_ip_on_launch=True,
        children=zone_checks,
    )
    builder.resource(
        "aws_subnet",
        "private",
        count=subnet_count,
        vpc_id=vpc_id,
        cidr_block=ref(
            "cidrsubnet(aws_vpc.this[0].cidr_block, 8, count.index + 10)"
            if standalone
            else "cidrsubnet(aws_vpc.this.cidr_block, 8, count.index + 10)"
        ),
        availability_zone=ref(zone_expression),
        children=zone_checks,
    )
    builder.resource("aws_internet_gateway", **owned_network, vpc_id=vpc_id)
    builder.resource(
        "aws_route_table",
        "public",
        **owned_network,
        vpc_id=vpc_id,
        children=[block("route", cidr_block="0.0.0.0/0", gateway_id=gateway_id)],
    )
    builder.resource(
        "aws_route_table_association",
        "public",
        count=subnet_count,
        subnet_id=ref("aws_subnet.public[count.index].id"),
        route_table_id=ref(
            "aws_route_table.public[0].id" if standalone else "aws_route_table.public.id"
        ),
    )
    if builder.config.enable_encryption:
        builder.resource(
            "aws_kms_key",
            description="TerraForma storage encryption",
            enable_key_rotation=True,
            deletion_window_in_days=30,
        )
    if builder.config.architecture_type == "secure_database":
        build_database(builder)
        return
    windows = builder.config.architecture_type == "windows_virtual_machine"
    standalone = builder.config.architecture_type in {"virtual_machine", "windows_virtual_machine"}
    if not standalone:
        builder.variable(
            "allowed_cidr",
            "Clients allowed to access HTTP.",
            "0.0.0.0/0" if builder.config.is_public else "10.0.0.0/16",
        )
    balanced = builder.config.architecture_type == "load_balanced_tier"
    private = balanced or not builder.config.is_public
    if private:
        builder.resource("aws_eip", "nat", **owned_network, domain="vpc")
        builder.resource(
            "aws_nat_gateway",
            **owned_network,
            allocation_id=ref("aws_eip.nat[0].id" if standalone else "aws_eip.nat.id"),
            subnet_id=ref("aws_subnet.public[0].id"),
            depends_on=[ref("aws_internet_gateway.this")],
        )
        builder.resource(
            "aws_route_table",
            "private",
            **owned_network,
            vpc_id=vpc_id,
            children=[
                block(
                    "route",
                    cidr_block="0.0.0.0/0",
                    nat_gateway_id=ref(
                        "aws_nat_gateway.this[0].id" if standalone else "aws_nat_gateway.this.id"
                    ),
                )
            ],
        )
        builder.resource(
            "aws_route_table_association",
            "private",
            count=subnet_count,
            subnet_id=ref("aws_subnet.private[count.index].id"),
            route_table_id=ref(
                "aws_route_table.private[0].id" if standalone else "aws_route_table.private.id"
            ),
        )
    egress = block("egress", from_port=0, to_port=0, protocol="-1", cidr_blocks=["0.0.0.0/0"])
    ingress = block(
        "ingress",
        from_port=3389 if windows else 22 if standalone else 80,
        to_port=3389 if windows else 22 if standalone else 80,
        protocol="tcp",
        **{"security_groups": [ref("aws_security_group.lb.id")]}
        if balanced
        else {"cidr_blocks": [ref("var.allowed_cidr")]},
    )
    builder.resource(
        "aws_security_group",
        "web",
        **owned_network,
        name_prefix=ref('"${var.project_name}-web-"'),
        vpc_id=vpc_id,
        children=[ingress] + (aws_outbound_rules() if standalone else [egress]),
    )
    if standalone:
        add_aws_attachment_data(builder)
    builder.variable(
        "image_version",
        "Use latest to resolve the selected AWS image at planning time, or an exact AMI ID in the chosen region. The AMI must match the selected OS name, trusted owner, x86_64 architecture and HVM filters; custom publishers are unsupported. Verify availability, access and compatibility before planning. Changing an image can replace the VM and destroy boot-disk data. Pinning does not automatically patch the VM.",
        "latest",
        pattern="^(latest|ami-([0-9a-f]{8}|[0-9a-f]{17}))$",
    )
    builder.main.append(
        block(
            "data",
            "aws_ami",
            "windows" if windows else "linux",
            most_recent=True,
            **{"count": ref("var.use_custom_image ? 0 : 1")} if standalone else {},
            owners=["amazon"]
            if windows
            else ref('var.os_image == "amazon-linux-2023" ? ["amazon"] : ["099720109477"]'),
            children=[
                block(
                    "filter",
                    name="name",
                    values=ref(
                        '[{ "windows-server-2022" = "Windows_Server-2022-English-Full-Base-*", "windows-server-2022-core" = "Windows_Server-2022-English-Core-Base-*" }[var.os_image]]'
                    )
                    if windows
                    else ref(
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
    if standalone:
        builder.main.append(
            block(
                "data",
                "aws_ami",
                "custom",
                count=ref("var.use_custom_image ? 1 : 0"),
                owners=[ref("var.custom_image_owner_account_id")],
                most_recent=False,
                children=[
                    block("filter", name="image-id", values=[ref("var.custom_image")]),
                    block("filter", name="architecture", values=["x86_64"]),
                    block("filter", name="virtualization-type", values=["hvm"]),
                    block("filter", name="root-device-type", values=["ebs"]),
                    block("filter", name="is-public", values=["false"]),
                    block(
                        "lifecycle",
                        children=[
                            *custom_image_preconditions("aws", windows),
                            block(
                                "postcondition",
                                condition=ref(
                                    'self.platform == "windows"'
                                    if windows
                                    else 'self.platform == ""'
                                ),
                                error_message="Choose a custom AMI matching this Linux or Windows recipe.",
                            ),
                            block(
                                "postcondition",
                                condition=ref("length(self.product_codes) == 0"),
                                error_message="Marketplace and product-code custom images are unsupported.",
                            ),
                        ],
                    ),
                ],
            )
        )
    builder.variable(
        "instance_type",
        "EC2 instance size. Verify Windows licensing, memory and image requirements before planning."
        if windows
        else "EC2 instance size.",
        "t3.small" if windows else "t3.micro",
    )
    if standalone:
        declare_aws_tenancy(builder)
        builder.variable(
            "metadata_hop_limit",
            "IMDSv2 token response network hops. provider_default leaves the hop limit unmanaged, preserving account/AMI/provider behavior; verify the effective setting. one_hop restricts responses to one hop; containers can fail to obtain tokens. two_hops supports an additional container network hop and expands metadata reachability. Require compatible SDKs and restrict workload access to instance credentials. Returning to provider_default does not reset an existing VM's setting. IMDSv2 remains required; this does not configure container isolation or IAM permissions.",
            "provider_default",
            choices=("provider_default", "one_hop", "two_hops"),
        )
        builder.variable(
            "cpu_credit_mode",
            "CPU credit setting for supported x86 T2, T3, T3a and T8i instances. provider_default leaves this setting unmanaged; verify the effective setting in your account. standard can reduce performance when credits run out. unlimited can add surplus-credit charges. Returning to provider_default stops managing this setting and does not reset an existing VM's mode. Other instance families require provider_default. This does not estimate cost or verify capacity.",
            "provider_default",
            choices=("provider_default", "standard", "unlimited"),
        )
        builder.variable(
            "protect_vm",
            "Enable EC2 API termination protection. Turn this off and apply that change before intentionally deleting or replacing the VM. This does not prevent stopping the VM and is not a backup or a guarantee against every deletion path.",
            True,
            type_name="bool",
        )
    builder.variable(
        "detailed_monitoring",
        "Publish most EC2 metrics every minute instead of the basic five-minute interval. Detailed monitoring can add CloudWatch charges per instance; status checks already use one-minute periods. This does not install an agent or configure logs/alarms.",
        False,
        type_name="bool",
    )
    builder.variable(
        "boot_disk_size_gb",
        "Boot disk size in GiB; review the image minimum and ongoing storage cost.",
        50 if windows else 20,
        type_name="number",
        minimum=30 if windows else 20,
        maximum=2048,
    )
    builder.variable("boot_disk_type", "EBS boot disk class.", "gp3", choices=("gp3", "gp2"))
    if standalone:
        builder._gp3_inputs("boot_disk", {"boot_disk_type": "gp3"})
    disk = {
        "volume_type": ref("var.boot_disk_type"),
        "volume_size": ref("var.boot_disk_size_gb"),
        "encrypted": builder.config.enable_encryption,
    }
    if standalone:
        disk.update(
            delete_on_termination=ref("var.delete_boot_disk_with_vm"),
            iops=ref('var.boot_disk_type == "gp3" ? var.boot_disk_iops : null'),
            throughput=ref('var.boot_disk_type == "gp3" ? var.boot_disk_throughput : null'),
        )
    if builder.config.enable_encryption:
        disk["kms_key_id"] = ref("aws_kms_key.this.arn")
    if standalone:
        builder.resource(
            "aws_key_pair",
            key_name_prefix=ref('"${var.project_name}-"'),
            public_key=ref("var.ssh_public_key"),
        )
    builder.resource(
        "aws_instance",
        "web",
        count=ref("var.instance_count") if balanced else 1,
        ami=ref(
            f"var.use_custom_image ? data.aws_ami.custom[0].id : data.aws_ami.{'windows' if windows else 'linux'}[0].id"
            if standalone
            else "data.aws_ami.windows.id"
            if windows
            else "data.aws_ami.linux.id"
        ),
        instance_type=ref("var.instance_type"),
        monitoring=ref("var.detailed_monitoring"),
        **{
            "tenancy": ref(
                'var.instance_tenancy == "provider_default" ? null : var.instance_tenancy'
            )
        }
        if standalone
        else {},
        **{
            "iam_instance_profile": ref(
                "var.enable_workload_identity ? var.workload_identity : null"
            )
        }
        if standalone
        else {},
        **{"disable_api_termination": ref("var.protect_vm")} if standalone else {},
        subnet_id=ref(
            f"var.use_existing_network ? data.aws_subnet.existing[0].id : aws_subnet.{('private' if private else 'public')}[count.index % 2].id"
            if standalone
            else f"aws_subnet.{('private' if private else 'public')}[count.index % 2].id"
        ),
        associate_public_ip_address=not private,
        **{"private_ip": ref('var.private_ip_address == "" ? null : var.private_ip_address')}
        if standalone
        else {},
        vpc_security_group_ids=ref(
            "var.use_existing_network ? [data.aws_security_group.existing[0].id] : [aws_security_group.web[0].id]"
        )
        if standalone
        else [ref("aws_security_group.web.id")],
        **{"key_name": ref("aws_key_pair.this.key_name")}
        | {
            "user_data_base64": aws_initialization_payload(windows),
            "user_data_replace_on_change": True,
        }
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
        },
        tags={"Name": ref("var.project_name")},
        children=[
            block("root_block_device", **disk),
            block(
                "metadata_options",
                http_tokens="required",
                **{
                    "http_put_response_hop_limit": ref(
                        '{ "provider_default" = null, "one_hop" = 1, "two_hops" = 2 }[var.metadata_hop_limit]'
                    )
                }
                if standalone
                else {},
            ),
        ]
        + (
            [
                block(
                    "dynamic",
                    "credit_specification",
                    for_each=ref(
                        'var.cpu_credit_mode == "provider_default" ? [] : [var.cpu_credit_mode]'
                    ),
                    children=[block("content", cpu_credits=ref("credit_specification.value"))],
                )
            ]
            if standalone
            else []
        )
        + ([builder._identity_precondition()] if standalone else []),
        **{"depends_on": [ref("aws_route_table_association.private")]} if private else {},
    )
    if standalone:
        builder.resource(
            "aws_ebs_volume",
            "data",
            count=ref("var.enable_data_disk ? 1 : 0"),
            availability_zone=ref("aws_instance.web[0].availability_zone"),
            size=ref("var.data_disk_size_gb"),
            type=ref("var.data_disk_type"),
            iops=ref('var.data_disk_type == "gp3" ? var.data_disk_iops : null'),
            throughput=ref('var.data_disk_type == "gp3" ? var.data_disk_throughput : null'),
            encrypted=True,
            children=[block("lifecycle", children=[builder._gp3_precondition("data_disk")])],
            **{"kms_key_id": ref("aws_kms_key.this.arn")}
            if builder.config.enable_encryption
            else {},
        )
        builder.resource(
            "aws_volume_attachment",
            "data",
            count=ref("var.enable_data_disk ? 1 : 0"),
            device_name="/dev/sdf",
            volume_id=ref("aws_ebs_volume.data[0].id"),
            instance_id=ref("aws_instance.web[0].id"),
            force_detach=False,
            stop_instance_before_detaching=True,
        )
        builder.output(
            "data_disk_id",
            "var.enable_data_disk ? aws_ebs_volume.data[0].id : null",
            "Optional data volume ID. Identify the new empty disk in Windows Disk Management before initializing it; formatting, backups and recovery are not configured. AWS attachment changes may stop the VM."
            if windows
            else "Optional data volume ID. Map the actual Linux device before formatting; this project does not mount or back it up. AWS attachment changes may stop the VM.",
        )
    if balanced:
        builder.resource(
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
        builder.resource(
            "aws_lb",
            name=ref("var.project_name"),
            internal=not builder.config.is_public,
            load_balancer_type="application",
            subnets=ref(
                f"aws_subnet.{('public' if builder.config.is_public else 'private')}[*].id"
            ),
            security_groups=[ref("aws_security_group.lb.id")],
        )
        builder.resource(
            "aws_lb_target_group",
            port=80,
            protocol="HTTP",
            vpc_id=ref("aws_vpc.this.id"),
            children=[block("health_check", path="/")],
        )
        builder.resource(
            "aws_lb_target_group_attachment",
            count=ref("var.instance_count"),
            target_group_arn=ref("aws_lb_target_group.this.arn"),
            target_id=ref("aws_instance.web[count.index].id"),
            port=80,
        )
        builder.resource(
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
        builder.output(
            "endpoint",
            '"http://${aws_lb.this.dns_name}"',
            "HTTP endpoint; add TLS before serving sensitive traffic.",
        )
    else:
        address = "public_ip" if builder.config.is_public else "private_ip"
        if standalone:
            builder.output(
                "vm_id",
                "aws_instance.web[0].id",
                "EC2 instance ID for cloud operations; available after provisioning.",
            )
            builder.output(
                "vm_name",
                'aws_instance.web[0].tags["Name"]',
                "EC2 Name tag; it is not a unique instance identifier. Use vm_id for operations.",
            )
            builder.output(
                "vm_location",
                "aws_instance.web[0].availability_zone",
                "EC2 availability zone; the region is supplied in the project inputs.",
            )
            builder.output(
                "vm_address",
                f"aws_instance.web[0].{address}",
                "VM IPv4 address; RDP requires the allowed client network and an Administrator password recovered separately through EC2 with the matching private key."
                if windows
                else "VM IPv4 address; SSH requires the allowed client network and matching private key.",
            )
            builder.output(
                "administrator_username" if windows else "ssh_username",
                '"Administrator"'
                if windows
                else 'var.use_custom_image ? var.custom_image_admin_username : (var.os_image == "amazon-linux-2023" ? "ec2-user" : "ubuntu")',
                "Administrator username from the catalog or the declared existing custom-image account. Guest access remains unverified.",
            )
            return
        builder.output(
            "endpoint", f'"http://${{aws_instance.web[0].{address}}}"', "Web server HTTP endpoint."
        )


def build_database(builder: TerraformGenerator) -> None:
    builder.variable(
        "database_password",
        "PostgreSQL administrator password; supply through TF_VAR_database_password.",
        sensitive=True,
    )
    builder.variable(
        "allowed_cidr",
        "Network permitted to connect to PostgreSQL.",
        "10.0.0.0/16",
        network_policy="database_cidr",
    )
    builder.resource(
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
    builder.resource(
        "aws_db_subnet_group",
        subnet_ids=ref(f"aws_subnet.{('public' if builder.config.is_public else 'private')}[*].id"),
    )
    attributes = {
        "identifier": ref("var.project_name"),
        "engine": "postgres",
        "instance_class": "db.t3.micro",
        "allocated_storage": 20,
        "storage_type": "gp3",
        "storage_encrypted": builder.config.enable_encryption,
        "username": "terraforma",
        "password": ref("var.database_password"),
        "db_name": "app",
        "db_subnet_group_name": ref("aws_db_subnet_group.this.name"),
        "vpc_security_group_ids": [ref("aws_security_group.database.id")],
        "publicly_accessible": builder.config.is_public,
        "multi_az": True,
        "backup_retention_period": 7,
        "deletion_protection": True,
        "skip_final_snapshot": False,
        "final_snapshot_identifier": ref('"${var.project_name}-final"'),
    }
    if builder.config.enable_encryption:
        attributes["kms_key_id"] = ref("aws_kms_key.this.arn")
    builder.resource("aws_db_instance", **attributes)
    builder.output(
        "database_endpoint", "aws_db_instance.this.endpoint", "PostgreSQL hostname and port."
    )


def build_static(builder: TerraformGenerator) -> None:
    builder.variable(
        "index_html", "Initial website HTML.", "<html><body><h1>TerraForma-IaC</h1></body></html>"
    )
    builder.resource("aws_s3_bucket", bucket_prefix=ref('"${var.project_name}-"'))
    builder.resource(
        "aws_s3_bucket_public_access_block",
        bucket=ref("aws_s3_bucket.this.id"),
        block_public_acls=True,
        ignore_public_acls=True,
        block_public_policy=not builder.config.is_public,
        restrict_public_buckets=not builder.config.is_public,
    )
    builder.resource(
        "aws_s3_bucket_versioning",
        bucket=ref("aws_s3_bucket.this.id"),
        children=[block("versioning_configuration", status="Enabled")],
    )
    builder.resource(
        "aws_s3_bucket_server_side_encryption_configuration",
        bucket=ref("aws_s3_bucket.this.id"),
        children=[
            block(
                "rule",
                children=[block("apply_server_side_encryption_by_default", sse_algorithm="AES256")],
            )
        ],
    )
    builder.resource(
        "aws_s3_object",
        bucket=ref("aws_s3_bucket.this.id"),
        key="index.html",
        content=ref("var.index_html"),
        content_type="text/html",
    )
    if builder.config.is_public:
        builder.resource(
            "aws_s3_bucket_website_configuration",
            bucket=ref("aws_s3_bucket.this.id"),
            children=[block("index_document", suffix="index.html")],
        )
        policy = 'jsonencode({ Version = "2012-10-17", Statement = [{ Effect = "Allow", Principal = "*", Action = "s3:GetObject", Resource = "${aws_s3_bucket.this.arn}/*" }] })'
        builder.resource(
            "aws_s3_bucket_policy",
            bucket=ref("aws_s3_bucket.this.id"),
            policy=ref(policy),
            depends_on=[ref("aws_s3_bucket_public_access_block.this")],
        )
        builder.output(
            "endpoint",
            '"http://${aws_s3_bucket_website_configuration.this.website_endpoint}"',
            "Public S3 website endpoint; account-level public-access blocks must permit hosting.",
        )
    else:
        builder.output(
            "endpoint",
            '"s3://${aws_s3_bucket.this.id}/index.html"',
            "Private site object; authenticated access required.",
        )
