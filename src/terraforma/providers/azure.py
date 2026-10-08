from __future__ import annotations

from typing import TYPE_CHECKING

from terraforma.azure_identity import azure_identity_precondition
from terraforma.configuration import AZURE_RESERVED_USERNAMES
from terraforma.custom_images import custom_image_preconditions
from terraforma.hcl import block, ref, value_hcl

if TYPE_CHECKING:
    from terraforma.generator import TerraformGenerator


def build_azure(builder: TerraformGenerator) -> None:
    builder.variable("location", "Azure region.", "eastus")
    builder.variable("subscription_id", "Azure subscription ID.")
    builder.main.append(
        block(
            "provider",
            "azurerm",
            subscription_id=ref("var.subscription_id"),
            children=[block("features")],
        )
    )
    builder.resource(
        "azurerm_resource_group",
        name=ref("var.project_name"),
        location=ref("var.location"),
        tags={"Environment": ref("var.environment"), "ManagedBy": "TerraForma-IaC"},
    )
    common = {
        "resource_group_name": ref("azurerm_resource_group.this.name"),
        "location": ref("azurerm_resource_group.this.location"),
        "tags": {"Environment": ref("var.environment"), "ManagedBy": "TerraForma-IaC"},
    }
    if builder.config.architecture_type == "static_site":
        build_static(builder, common)
        return
    builder.resource(
        "azurerm_virtual_network",
        name=ref('"${var.project_name}-vnet"'),
        address_space=[ref("var.network_cidr")]
        if builder.config.architecture_type in {"virtual_machine", "windows_virtual_machine"}
        else ["10.0.0.0/16"],
        **common,
    )
    subnet = {
        "name": "workload",
        "resource_group_name": common["resource_group_name"],
        "virtual_network_name": ref("azurerm_virtual_network.this.name"),
        "address_prefixes": [ref("cidrsubnet(var.network_cidr, 8, 1)")]
        if builder.config.architecture_type in {"virtual_machine", "windows_virtual_machine"}
        else ["10.0.1.0/24"],
    }
    if builder.config.architecture_type == "secure_database":
        build_database(builder, common, subnet)
        return
    builder.resource("azurerm_subnet", **subnet)
    windows = builder.config.architecture_type == "windows_virtual_machine"
    vm_resource = "azurerm_windows_virtual_machine" if windows else "azurerm_linux_virtual_machine"
    standalone = builder.config.architecture_type in {"virtual_machine", "windows_virtual_machine"}
    zone = ref('var.availability_zone == "regional" ? null : var.availability_zone')
    zones = ref('var.availability_zone == "regional" ? null : [var.availability_zone]')
    if standalone:
        builder.variable(
            "availability_zone",
            "Azure placement: regional (default) requests no specific availability zone; 1, 2 or 3 places the VM, optional data disk, Standard NAT gateway and generated public IPs in that zone. The opt-in size check reports listed VM zones; it does not establish disk/network zone support or capacity. One zone is not a highly available deployment. Changing placement replaces resources and can delete OS/data disks or change public addresses; review backups and the Terraform plan first.",
            "regional",
            choices=("regional", "1", "2", "3"),
        )
    builder.variable(
        "admin_username",
        "Windows administrator username: 3–20 lowercase letters, digits, underscores or hyphens. Start with a letter and end with a letter or digit. Reserved names are rejected. Supply the password externally and protect Terraform state and plans."
        if windows
        else "Linux administrator username: 3–32 lowercase letters, digits, underscores or hyphens. Start with a letter and end with a letter or digit. Azure reserved names are rejected; password authentication stays disabled.",
        "terraforma",
        pattern="^[a-z][a-z0-9_\\-]{1,18}[a-z0-9]$"
        if windows
        else "^[a-z][a-z0-9_\\-]{1,30}[a-z0-9]$",
        forbidden_values=AZURE_RESERVED_USERNAMES,
    )
    if windows:
        builder.variable(
            "admin_password",
            "Supply TF_VAR_admin_password externally before planning. Never enter a password in this project. AzureRM stores this password in Terraform state even though it is sensitive; protect state, saved plans and access before use. This generator does not configure a protected backend. Password changes replace the VM.",
            sensitive=True,
        )
        condition = (
            "length(var.admin_password) >= 12 && length(var.admin_password) <= 123 && ("
            + " + ".join(
                f"(length(regexall({value_hcl(pattern)}, var.admin_password)) > 0 ? 1 : 0)"
                for pattern in ("[A-Z]", "[a-z]", "[0-9]", "[^A-Za-z0-9]")
            )
            + ") >= 3"
        )
        builder.variables[-1].children.append(
            block(
                "validation",
                condition=ref(condition),
                error_message="Use 12–123 characters and at least three categories: uppercase, lowercase, digits and symbols. Provider restrictions also apply.",
            )
        )
        builder.variable(
            "computer_name",
            "Windows computer name, separate from the Azure resource name: 3–15 lowercase letters, digits or hyphens, starting with a letter and ending with a letter or digit. Changing it replaces the VM. Check hostname uniqueness on connected networks.",
            "terraforma",
            pattern="^[a-z][a-z0-9-]{1,13}[a-z0-9]$",
        )
        builder.variable(
            "license_type",
            "Use None for standard Azure Windows licensing. Windows_Server requests Azure Hybrid Benefit only if you hold qualifying licenses; eligibility is not checked by this tool.",
            "None",
            choices=("None", "Windows_Server"),
        )
        builder.variable(
            "enable_patch_assessment",
            "Request automatic platform assessment of available Windows updates. When off, keep the image's default assessment behavior. This is independent of patch installation: automatic OS updates remain enabled. The VM Agent stays enabled; image support, guest-agent health and assessment success need cloud verification. No maintenance schedule or custom patch installation workflow is configured.",
            False,
            type_name="bool",
        )
    else:
        builder.variable(
            "ssh_public_key",
            "Administrator SSH public key for the selected user. Keep the matching private key outside this project."
            if standalone
            else "Administrator SSH public key. SSH is not exposed by the generated firewall.",
        )
    if not standalone:
        builder.variable(
            "allowed_cidr",
            "Clients allowed to access HTTP.",
            "0.0.0.0/0" if builder.config.is_public else "10.0.0.0/16",
        )
    builder.resource(
        "azurerm_network_security_group",
        name=ref('"${var.project_name}-nsg"'),
        children=[
            block(
                "security_rule",
                name="RDP" if windows else "SSH" if standalone else "HTTP",
                priority=100,
                direction="Inbound",
                access="Allow",
                protocol="Tcp",
                source_port_range="*",
                destination_port_range="3389" if windows else "22" if standalone else "80",
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
    builder.resource(
        "azurerm_subnet_network_security_group_association",
        subnet_id=ref("azurerm_subnet.this.id"),
        network_security_group_id=ref("azurerm_network_security_group.this.id"),
    )
    builder.resource(
        "azurerm_public_ip",
        "egress",
        name=ref('"${var.project_name}-egress"'),
        allocation_method="Static",
        sku="Standard",
        **{"zones": zones} if standalone else {},
        **common,
    )
    builder.resource(
        "azurerm_nat_gateway",
        name=ref('"${var.project_name}-nat"'),
        sku_name="Standard",
        **{"zones": zones} if standalone else {},
        **common,
    )
    builder.resource(
        "azurerm_nat_gateway_public_ip_association",
        nat_gateway_id=ref("azurerm_nat_gateway.this.id"),
        public_ip_address_id=ref("azurerm_public_ip.egress.id"),
    )
    builder.resource(
        "azurerm_subnet_nat_gateway_association",
        subnet_id=ref("azurerm_subnet.this.id"),
        nat_gateway_id=ref("azurerm_nat_gateway.this.id"),
    )
    balanced = builder.config.architecture_type == "load_balanced_tier"
    if builder.config.is_public:
        builder.resource(
            "azurerm_public_ip",
            "web",
            name=ref('"${var.project_name}-web"'),
            allocation_method="Static",
            sku="Standard",
            **{"zones": zones} if standalone else {},
            **common,
        )
    builder.variable(
        "vm_size",
        "Azure VM size; availability and encryption-at-host support require account preflight.",
        "Standard_D2s_v5" if windows else "Standard_B1s",
    )
    builder.variable(
        "boot_disk_size_gb",
        "OS disk size in GiB; cannot be smaller than the selected image.",
        128 if windows else 30,
        type_name="number",
        minimum=128 if windows else 30,
        maximum=2048,
    )
    builder.variable(
        "boot_disk_type",
        "Azure managed OS disk class.",
        "Standard_LRS",
        choices=("Standard_LRS", "StandardSSD_LRS", "Premium_LRS"),
    )
    if standalone:
        builder.variable(
            "boot_disk_caching",
            "Azure OS disk host cache mode. ReadWrite is the default; None disables the cache, and ReadOnly caches reads. ReadWrite can acknowledge writes before they reach the managed disk, so review guest/application flush behavior and recovery. VM and disk capabilities, performance and safe cache changes require separate verification.",
            "ReadWrite",
            choices=("None", "ReadOnly", "ReadWrite"),
        )
    disk = block(
        "os_disk",
        caching=ref("var.boot_disk_caching") if standalone else "ReadWrite",
        storage_account_type=ref("var.boot_disk_type"),
        disk_size_gb=ref("var.boot_disk_size_gb"),
    )
    if standalone:
        builder.variable(
            "enable_accelerated_networking",
            "Enable accelerated networking on the VM's network interface for supported Azure VM sizes and guest images. This can reduce latency and CPU overhead; it does not change firewall access. Leave it off unless the selected size supports it. Changing an existing VM's setting can require stopping and deallocating the VM; this generator does not perform that operation. The optional VM-size metadata check can report support, but does not prove guest-driver compatibility or capacity.",
            False,
            type_name="bool",
        )
        builder.variable(
            "enable_secure_boot",
            "Enable Azure Trusted Launch Secure Boot for the selected Gen2 image. vTPM stays enabled. Changing this setting replaces the VM and can delete its OS disk; review the plan and backups first. Unsigned kernel drivers can prevent booting; check VM-size support and workload compatibility before deployment. This recipe does not configure guest attestation or Defender monitoring."
            + (
                " Protect BitLocker recovery keys before changing boot settings; guest encryption and recovery are not configured by this recipe."
                if windows
                else ""
            ),
            True,
            type_name="bool",
        )
        builder.variable(
            "enable_boot_diagnostics",
            "Capture boot console output and screenshots in Azure-managed diagnostic storage for startup troubleshooting. Managed diagnostic blobs are currently not billed by Azure; verify current pricing. Retention is not configurable and logs are overwritten above 1 GB. Console output can contain sensitive data; restrict cloud access and avoid writing secrets to the console. This does not configure application logs, alerts or guest attestation, and no custom storage account or public log URL is created by this recipe.",
            False,
            type_name="bool",
        )
    builder.variable(
        "image_version",
        "Azure Windows marketplace version for MicrosoftWindowsServer/windowsserver2022 with the selected desktop 2022-datacenter-g2 or Core 2022-datacenter-core-g2 SKU: latest or exact Major.Minor.Build. The refreshed offer excludes deprecated .NET 6 packages. Regenerating older WindowsServer-offer projects changes the image reference and can replace the VM and delete boot data. Verify the exact version in the new offer, region and application dependencies; old-offer pins are not automatically translated. Review backups and the Terraform plan before migration."
        if windows
        else "Azure marketplace image version for the selected Canonical offer/SKU. Use latest to resolve at planning time, or an exact Major.Minor.Build version to pin the image. A version number does not prove availability or compatibility; check the selected image and location before planning. Changing a VM image can replace the VM and destroy its boot-disk data. Custom publishers and gallery images are unsupported.",
        "latest",
        pattern="^(latest|[0-9]{1,10}\\.[0-9]{1,10}\\.[0-9]{1,10})$",
    )
    image = block(
        "source_image_reference",
        publisher="MicrosoftWindowsServer" if windows else "Canonical",
        offer="windowsserver2022"
        if windows
        else ref(
            'var.os_image == "ubuntu-22.04" ? "0001-com-ubuntu-server-jammy" : "ubuntu-24_04-lts"'
        ),
        sku=ref(
            '{"windows-server-2022" = "2022-datacenter-g2", "windows-server-2022-core" = "2022-datacenter-core-g2"}[var.os_image]'
        )
        if windows
        else ref('var.os_image == "ubuntu-22.04" ? "22_04-lts-gen2" : "server"'),
        version=ref("var.image_version"),
    )
    key = (
        None
        if windows
        else block(
            "admin_ssh_key",
            username=ref("var.admin_username"),
            public_key=ref("var.ssh_public_key"),
        )
    )
    startup = "#cloud-config\npackage_update: true\npackages:\n  - nginx\nruncmd:\n  - [systemctl, enable, --now, nginx]\n"
    compute = {
        "name": ref("var.project_name"),
        "admin_username": ref("var.admin_username"),
        "disable_password_authentication": True,
        "custom_data": ref(f"base64encode({value_hcl(startup)})"),
        "encryption_at_host_enabled": builder.config.enable_encryption,
        "depends_on": [
            ref("azurerm_subnet_nat_gateway_association.this"),
            ref("azurerm_nat_gateway_public_ip_association.this"),
            ref("azurerm_subnet_network_security_group_association.this"),
        ],
        **common,
    }
    if standalone:
        compute.pop("custom_data")
        compute["zone"] = zone
        compute["source_image_id"] = ref("var.use_custom_image ? var.custom_image : null")
        image = block(
            "dynamic",
            "source_image_reference",
            for_each=ref("var.use_custom_image ? [] : [1]"),
            children=[block("content", **image.attributes)],
        )
    if windows:
        compute.pop("disable_password_authentication")
        compute.update(
            admin_password=ref("var.admin_password"),
            computer_name=ref("var.computer_name"),
            license_type=ref("var.license_type"),
            automatic_updates_enabled=True,
            patch_mode="AutomaticByOS",
            patch_assessment_mode=ref(
                'var.enable_patch_assessment ? "AutomaticByPlatform" : "ImageDefault"'
            ),
            provision_vm_agent=True,
        )
    if balanced:
        frontend = {"name": "frontend"}
        if builder.config.is_public:
            frontend["public_ip_address_id"] = ref("azurerm_public_ip.web.id")
        else:
            frontend.update(
                subnet_id=ref("azurerm_subnet.this.id"), private_ip_address_allocation="Dynamic"
            )
        builder.resource(
            "azurerm_lb",
            name=ref('"${var.project_name}-lb"'),
            sku="Standard",
            children=[block("frontend_ip_configuration", **frontend)],
            **common,
        )
        builder.resource(
            "azurerm_lb_backend_address_pool", name="web", loadbalancer_id=ref("azurerm_lb.this.id")
        )
        builder.resource(
            "azurerm_lb_probe",
            name="http",
            loadbalancer_id=ref("azurerm_lb.this.id"),
            protocol="Http",
            port=80,
            request_path="/",
        )
        builder.resource(
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
            load_balancer_backend_address_pool_ids=[ref("azurerm_lb_backend_address_pool.this.id")],
        )
        builder.resource(
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
            if builder.config.is_public
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
        if builder.config.is_public:
            ip["public_ip_address_id"] = ref("azurerm_public_ip.web.id")
        builder.resource(
            "azurerm_network_interface",
            name=ref('"${var.project_name}-nic"'),
            **{"accelerated_networking_enabled": ref("var.enable_accelerated_networking")}
            if standalone
            else {},
            children=[block("ip_configuration", **ip)],
            **common,
        )
        builder.resource(
            vm_resource,
            size=ref("var.vm_size"),
            network_interface_ids=[ref("azurerm_network_interface.this.id")],
            **{"secure_boot_enabled": ref("var.enable_secure_boot"), "vtpm_enabled": True}
            if standalone
            else {},
            children=[disk, image]
            + ([] if windows else [key])
            + (
                [
                    block(
                        "lifecycle",
                        children=[
                            builder._private_ip_precondition(),
                            azure_identity_precondition(),
                            *custom_image_preconditions("azure", windows),
                        ],
                    )
                ]
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
                        children=[
                            block(
                                "content",
                                type=ref(
                                    'var.workload_identity_type == "existing_user_assigned" ? "UserAssigned" : "SystemAssigned"'
                                ),
                                identity_ids=ref(
                                    'var.workload_identity_type == "existing_user_assigned" ? [var.workload_identity_resource_id] : null'
                                ),
                            )
                        ],
                    )
                ]
                if standalone
                else []
            ),
            **compute,
        )
        endpoint = (
            "azurerm_public_ip.web.ip_address"
            if builder.config.is_public
            else "azurerm_network_interface.this.private_ip_address"
        )
    if standalone:
        builder.output(
            "managed_identity_principal_id",
            f'var.enable_workload_identity && var.workload_identity_type == "system_assigned" ? {vm_resource}.this.identity[0].principal_id : null',
            "Optional system-assigned identity principal. No role assignments are created; the identity is removed with the VM.",
        )
        builder.output(
            "user_assigned_identity_resource_id",
            'var.enable_workload_identity && var.workload_identity_type == "existing_user_assigned" ? var.workload_identity_resource_id : null',
            "Declared existing user-assigned identity resource ID. Existence, principal, permissions and attachment remain unverified; no identity or role grant is created by this reference.",
        )
        builder.resource(
            "azurerm_managed_disk",
            "data",
            count=ref("var.enable_data_disk ? 1 : 0"),
            name=ref('"${var.project_name}-data"'),
            create_option="Empty",
            disk_size_gb=ref("var.data_disk_size_gb"),
            storage_account_type=ref("var.data_disk_type"),
            zone=zone,
            network_access_policy="DenyAll",
            public_network_access_enabled=False,
            **common,
        )
        builder.resource(
            "azurerm_virtual_machine_data_disk_attachment",
            "data",
            count=ref("var.enable_data_disk ? 1 : 0"),
            managed_disk_id=ref("azurerm_managed_disk.data[0].id"),
            virtual_machine_id=ref(f"{vm_resource}.this.id"),
            lun=0,
            caching=ref("var.data_disk_caching"),
        )
        builder.output(
            "data_disk_id",
            "var.enable_data_disk ? azurerm_managed_disk.data[0].id : null",
            "Optional empty data disk ID, attached at LUN 0. Formatting, mounting, backups and recovery are not configured.",
        )
    if standalone:
        builder.output(
            "vm_id",
            f"{vm_resource}.this.id",
            "Azure VM resource ID for cloud operations; available after provisioning.",
        )
        builder.output(
            "vm_name",
            f"{vm_resource}.this.name",
            "Azure VM name within its resource group.",
        )
        builder.output(
            "vm_location",
            f"{vm_resource}.this.location",
            "Azure VM location; this recipe does not select an availability zone.",
        )
        builder.output(
            "vm_resource_group",
            "azurerm_resource_group.this.name",
            "Azure resource group name used with the VM name for cloud operations.",
        )
        builder.output(
            "vm_address",
            endpoint,
            "VM IPv4 address; RDP requires the allowed administrator network and externally supplied password. Protect state and plans; private VMs require routed access."
            if windows
            else "VM IPv4 address; SSH requires the allowed client network and matching private key.",
        )
        builder.output(
            "administrator_username" if windows else "ssh_username",
            "var.admin_username",
            "Windows administrator username; the password is supplied externally and retained in sensitive Terraform state."
            if windows
            else "Administrator username; password authentication is disabled.",
        )
    else:
        builder.output("endpoint", f'"http://${{{endpoint}}}"', "Web workload HTTP endpoint.")


def build_database(builder: TerraformGenerator, common: dict, subnet: dict) -> None:
    builder.variable(
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
        "public_network_access_enabled": builder.config.is_public,
        **common,
    }
    if not builder.config.is_public:
        builder.resource(
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
        builder.resource(
            "azurerm_private_dns_zone",
            name=ref('"${var.project_name}.postgres.database.azure.com"'),
            resource_group_name=common["resource_group_name"],
            tags=common["tags"],
        )
        builder.resource(
            "azurerm_private_dns_zone_virtual_network_link",
            name="postgres",
            resource_group_name=common["resource_group_name"],
            private_dns_zone_name=ref("azurerm_private_dns_zone.this.name"),
            virtual_network_id=ref("azurerm_virtual_network.this.id"),
            tags=common["tags"],
        )
        attributes.update(
            delegated_subnet_id=ref("azurerm_subnet.this.id"),
            private_dns_zone_id=ref("azurerm_private_dns_zone.this.id"),
            depends_on=[ref("azurerm_private_dns_zone_virtual_network_link.this")],
        )
    builder.resource(
        "azurerm_postgresql_flexible_server",
        children=[
            block("high_availability", mode="SameZone"),
            block("lifecycle", prevent_destroy=True),
        ],
        **attributes,
    )
    if builder.config.is_public:
        builder.variable(
            "database_client_ip",
            "Single public IPv4 client permitted by the database firewall.",
            network_policy="database_address",
        )
        builder.resource(
            "azurerm_postgresql_flexible_server_firewall_rule",
            name="client",
            server_id=ref("azurerm_postgresql_flexible_server.this.id"),
            start_ip_address=ref("var.database_client_ip"),
            end_ip_address=ref("var.database_client_ip"),
        )
    builder.output(
        "database_endpoint",
        "azurerm_postgresql_flexible_server.this.fqdn",
        "PostgreSQL hostname; connect with TLS.",
    )


def build_static(builder: TerraformGenerator, common: dict) -> None:
    builder.variable(
        "index_html", "Initial website HTML.", "<html><body><h1>TerraForma-IaC</h1></body></html>"
    )
    builder.resource("random_id", "suffix", byte_length=4)
    builder.resource(
        "azurerm_storage_account",
        name=ref('"${substr(replace(var.project_name, "-", ""), 0, 16)}${random_id.suffix.hex}"'),
        account_tier="Standard",
        account_replication_type="LRS",
        min_tls_version="TLS1_2",
        allow_nested_items_to_be_public=builder.config.is_public,
        **common,
    )
    if builder.config.is_public:
        builder.resource(
            "azurerm_storage_account_static_website",
            storage_account_id=ref("azurerm_storage_account.this.id"),
            index_document="index.html",
        )
        container = '"$web"'
    else:
        builder.resource(
            "azurerm_storage_container",
            name="site",
            storage_account_id=ref("azurerm_storage_account.this.id"),
            container_access_type="private",
        )
        container = "azurerm_storage_container.this.name"
    builder.resource(
        "azurerm_storage_blob",
        name="index.html",
        storage_account_name=ref("azurerm_storage_account.this.name"),
        storage_container_name=ref(container),
        type="Block",
        source_content=ref("var.index_html"),
        content_type="text/html",
        **{"depends_on": [ref("azurerm_storage_account_static_website.this")]}
        if builder.config.is_public
        else {},
    )
    endpoint = (
        "azurerm_storage_account.this.primary_web_endpoint"
        if builder.config.is_public
        else '"${azurerm_storage_account.this.primary_blob_endpoint}site/index.html"'
    )
    builder.output(
        "endpoint", endpoint, "Website endpoint; private objects require authenticated access."
    )
