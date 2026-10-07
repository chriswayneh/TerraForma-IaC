from __future__ import annotations

from typing import TYPE_CHECKING

from terraforma.hcl import block, ref

if TYPE_CHECKING:
    from terraforma.generator import TerraformGenerator


def build_gcp(builder: TerraformGenerator) -> None:
    builder.variable("gcp_project_id", "Existing Google Cloud project ID with billing enabled.")
    builder.variable("region", "Google Cloud region.", "us-central1")
    builder.main.append(
        block("provider", "google", project=ref("var.gcp_project_id"), region=ref("var.region"))
    )
    if builder.config.architecture_type == "static_site":
        build_static(builder)
        return
    builder.resource(
        "google_project_service",
        "compute",
        service="compute.googleapis.com",
        disable_on_destroy=False,
    )
    builder.resource(
        "google_compute_network",
        name=ref("var.project_name"),
        auto_create_subnetworks=False,
        depends_on=[ref("google_project_service.compute")],
    )
    builder.resource(
        "google_compute_subnetwork",
        name=ref("var.project_name"),
        ip_cidr_range=ref("var.network_cidr")
        if builder.config.architecture_type == "virtual_machine"
        else "10.0.1.0/24",
        region=ref("var.region"),
        network=ref("google_compute_network.this.id"),
        private_ip_google_access=True,
    )
    if builder.config.architecture_type == "secure_database":
        build_database(builder)
        return
    builder.variable("zone", "Compute zone in the chosen region.", "us-central1-a")
    standalone = builder.config.architecture_type == "virtual_machine"
    if standalone:
        builder.variable(
            "protect_vm",
            "Enable Google Compute Engine VM deletion protection. Turn this off and apply that change before intentionally deleting or replacing the VM. This is not a backup and does not protect the whole project from deletion.",
            True,
            type_name="bool",
        )
    if not standalone:
        builder.variable(
            "allowed_cidr",
            "Clients allowed to access HTTP.",
            "0.0.0.0/0" if builder.config.is_public else "10.0.0.0/16",
        )
    builder.resource(
        "google_compute_firewall",
        name=ref('"${var.project_name}-ssh"' if standalone else '"${var.project_name}-http"'),
        network=ref("google_compute_network.this.name"),
        source_ranges=[ref("var.allowed_cidr")]
        if standalone
        else [ref("var.allowed_cidr"), "35.191.0.0/16", "130.211.0.0/22"],
        target_tags=["terraforma-web"],
        children=[block("allow", protocol="tcp", ports=["22" if standalone else "80"])],
    )
    builder.resource(
        "google_compute_router",
        name=ref("var.project_name"),
        region=ref("var.region"),
        network=ref("google_compute_network.this.id"),
    )
    builder.resource(
        "google_compute_router_nat",
        name=ref("var.project_name"),
        router=ref("google_compute_router.this.name"),
        region=ref("var.region"),
        nat_ip_allocate_option="AUTO_ONLY",
        source_subnetwork_ip_ranges_to_nat="ALL_SUBNETWORKS_ALL_IP_RANGES",
    )
    startup = "#!/bin/bash\nset -eu\napt-get update\napt-get install -y nginx\nsystemctl enable --now nginx\n"
    balanced = builder.config.architecture_type == "load_balanced_tier"
    network = block(
        "network_interface",
        subnetwork=ref("google_compute_subnetwork.this.id"),
        **{"network_ip": ref('var.private_ip_address == "" ? null : var.private_ip_address')}
        if standalone
        else {},
        children=[block("access_config")] if builder.config.is_public and (not balanced) else [],
    )
    builder.variable(
        "machine_type",
        "Google Compute Engine machine type; zone availability requires account preflight.",
        "e2-micro",
    )
    builder.variable(
        "boot_disk_size_gb",
        "Boot disk size in GiB; review image requirements and storage cost.",
        20,
        type_name="number",
        minimum=20,
        maximum=2048,
    )
    builder.variable(
        "boot_disk_type",
        "Google persistent boot disk class.",
        "pd-balanced",
        choices=("pd-balanced", "pd-standard", "pd-ssd"),
    )
    builder.variable(
        "image_version",
        "Use latest to resolve the selected GCP image family at planning time, or enter an exact published Debian 12 Bookworm / Ubuntu 24.04 Noble AMD64 image name. The publisher project stays fixed. Verify availability, deprecation and compatibility before planning. Changing the image can replace a VM and destroy boot-disk data; pinning does not apply security patches automatically.",
        "latest",
        pattern="^(latest|debian-12-bookworm-v[0-9]{8}|ubuntu-2404-noble(-amd64)?-v[0-9]{8})$",
    )
    image_source = ref(
        'var.image_version == "latest" ? (var.os_image == "debian-12" ? "debian-cloud/debian-12" : "ubuntu-os-cloud/ubuntu-2404-lts-amd64") : (var.os_image == "debian-12" ? "debian-cloud/${var.image_version}" : "ubuntu-os-cloud/${var.image_version}")'
    )
    image_lifecycle = block(
        "lifecycle",
        children=[
            block(
                "precondition",
                condition=ref(
                    'var.image_version == "latest" || (var.os_image == "debian-12" ? startswith(var.image_version, "debian-12-bookworm-v") : startswith(var.image_version, "ubuntu-2404-noble"))'
                ),
                error_message="Choose an exact image name matching the selected Linux operating system.",
            )
        ]
        + (builder._identity_precondition().children if standalone else []),
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
        builder.variable(
            "enable_secure_boot",
            "Verify signed boot components with Google Shielded VM Secure Boot. Unsigned kernel modules or drivers can prevent booting; review workload compatibility before changing this setting. Changing Shielded VM options requires a stopped VM; automatic stopping is disabled. vTPM and integrity monitoring remain enabled.",
            True,
            type_name="bool",
        )
        builder.resource(
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
        builder.output(
            "data_disk_id",
            "var.enable_data_disk ? google_compute_disk.data[0].id : null",
            "Optional empty persistent disk ID, attached as data-disk. Formatting, mounting, backups and recovery are not configured.",
        )
    if balanced:
        builder.resource(
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
        builder.resource(
            "google_compute_instance_group_manager",
            name=ref("var.project_name"),
            base_instance_name=ref("var.project_name"),
            zone=ref("var.zone"),
            target_size=ref("var.instance_count"),
            children=[
                block("version", instance_template=ref("google_compute_instance_template.this.id")),
                block("named_port", name="http", port=80),
            ],
            depends_on=[ref("google_compute_router_nat.this")],
        )
        if builder.config.is_public:
            builder.resource(
                "google_compute_health_check",
                name=ref("var.project_name"),
                children=[block("http_health_check", port=80)],
            )
            builder.resource(
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
            builder.resource(
                "google_compute_url_map",
                name=ref("var.project_name"),
                default_service=ref("google_compute_backend_service.this.id"),
            )
            builder.resource(
                "google_compute_target_http_proxy",
                name=ref("var.project_name"),
                url_map=ref("google_compute_url_map.this.id"),
            )
            builder.resource(
                "google_compute_global_forwarding_rule",
                name=ref("var.project_name"),
                target=ref("google_compute_target_http_proxy.this.id"),
                port_range="80",
            )
            endpoint = "google_compute_global_forwarding_rule.this.ip_address"
        else:
            builder.resource(
                "google_compute_region_health_check",
                name=ref("var.project_name"),
                region=ref("var.region"),
                children=[block("tcp_health_check", port=80)],
            )
            builder.resource(
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
            builder.resource(
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
        builder.resource(
            "google_compute_instance",
            name=ref("var.project_name"),
            **{"deletion_protection": ref("var.protect_vm")} if standalone else {},
            labels={"environment": ref("var.environment"), "managed_by": "terraforma"},
            machine_type=ref("var.machine_type"),
            zone=ref("var.zone"),
            **{"allow_stopping_for_update": False} if standalone else {},
            tags=["terraforma-web"],
            **{
                "metadata": {
                    "enable-oslogin": "TRUE",
                    "block-project-ssh-keys": "TRUE",
                    "serial-port-enable": "FALSE",
                }
            }
            if standalone
            else {"metadata_startup_script": startup, "metadata": {"serial-port-enable": "FALSE"}},
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
                        for_each=ref("var.enable_workload_identity ? [var.workload_identity] : []"),
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
            if builder.config.is_public
            else "google_compute_instance.this.network_interface[0].network_ip"
        )
    if standalone:
        builder.output(
            "vm_id",
            "google_compute_instance.this.id",
            "GCP VM resource path for cloud operations; available after provisioning.",
        )
        builder.output(
            "vm_name",
            "google_compute_instance.this.name",
            "GCP instance name within its project and zone.",
        )
        builder.output(
            "vm_location",
            "google_compute_instance.this.zone",
            "GCP compute zone; project ID is supplied in the project inputs.",
        )
        builder.output(
            "vm_address",
            endpoint,
            "VM IPv4 address; use OS Login with the required IAM role and allowed client network. Private VMs require routed access.",
        )
    else:
        builder.output("endpoint", f'"http://${{{endpoint}}}"', "Web workload HTTP endpoint.")


def build_database(builder: TerraformGenerator) -> None:
    builder.variable(
        "database_password",
        "PostgreSQL user password; supply through TF_VAR_database_password.",
        sensitive=True,
    )
    builder.resource(
        "google_project_service", "sql", service="sqladmin.googleapis.com", disable_on_destroy=False
    )
    builder.resource(
        "google_project_service",
        "networking",
        service="servicenetworking.googleapis.com",
        disable_on_destroy=False,
    )
    builder.resource(
        "google_compute_global_address",
        name=ref('"${var.project_name}-sql"'),
        purpose="VPC_PEERING",
        address_type="INTERNAL",
        prefix_length=16,
        network=ref("google_compute_network.this.id"),
    )
    builder.resource(
        "google_service_networking_connection",
        network=ref("google_compute_network.this.id"),
        service="servicenetworking.googleapis.com",
        reserved_peering_ranges=[ref("google_compute_global_address.this.name")],
        depends_on=[ref("google_project_service.networking")],
    )
    ip = {
        "ipv4_enabled": builder.config.is_public,
        "private_network": ref("google_compute_network.this.id"),
        "ssl_mode": "ENCRYPTED_ONLY",
    }
    allowed = []
    if builder.config.is_public:
        builder.variable(
            "allowed_cidr",
            "IPv4 client network permitted to connect to the database.",
            network_policy="database_cidr",
        )
        allowed.append(block("authorized_networks", name="client", value=ref("var.allowed_cidr")))
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
    builder.resource(
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
    builder.resource(
        "google_sql_database", name="app", instance=ref("google_sql_database_instance.this.name")
    )
    builder.resource(
        "google_sql_user",
        name="terraforma",
        instance=ref("google_sql_database_instance.this.name"),
        password=ref("var.database_password"),
    )
    builder.output(
        "database_endpoint",
        "google_sql_database_instance.this.connection_name",
        "Cloud SQL connection name; use Cloud SQL Auth Proxy or private networking.",
    )


def build_static(builder: TerraformGenerator) -> None:
    builder.variable(
        "index_html", "Initial website HTML.", "<html><body><h1>TerraForma-IaC</h1></body></html>"
    )
    builder.resource("random_id", "suffix", byte_length=4)
    builder.resource(
        "google_storage_bucket",
        name=ref('"${var.gcp_project_id}-${var.project_name}-${random_id.suffix.hex}"'),
        labels={"environment": ref("var.environment"), "managed_by": "terraforma"},
        location=ref("var.region"),
        uniform_bucket_level_access=True,
        public_access_prevention="inherited" if builder.config.is_public else "enforced",
        children=[
            block("versioning", enabled=True),
            block("website", main_page_suffix="index.html"),
        ],
    )
    builder.resource(
        "google_storage_bucket_object",
        name="index.html",
        bucket=ref("google_storage_bucket.this.name"),
        content=ref("var.index_html"),
        content_type="text/html",
    )
    if builder.config.is_public:
        builder.resource(
            "google_storage_bucket_iam_member",
            bucket=ref("google_storage_bucket.this.name"),
            role="roles/storage.objectViewer",
            member="allUsers",
        )
        endpoint = '"https://storage.googleapis.com/${google_storage_bucket.this.name}/index.html"'
    else:
        endpoint = '"gs://${google_storage_bucket.this.name}/index.html"'
    builder.output(
        "endpoint", endpoint, "Site object endpoint; organization policy may forbid public access."
    )
