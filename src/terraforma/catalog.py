from terraforma.generator import LINUX_IMAGE_CHOICES, WizardConfig

PROVIDERS = ("aws", "azure", "gcp")
WORKLOADS = {
    "virtual_machine": "Linux virtual machine",
    "windows_virtual_machine": "Windows virtual machine (AWS)",
    "single_web_server": "Single web server",
    "load_balanced_tier": "Load-balanced application",
    "secure_database": "Managed PostgreSQL",
    "static_site": "Object-storage website",
}


def recipe_capabilities(config: WizardConfig) -> dict:
    compute = config.architecture_type in {
        "virtual_machine",
        "windows_virtual_machine",
        "single_web_server",
        "load_balanced_tier",
    }
    windows = config.architecture_type == "windows_virtual_machine"
    standalone = config.architecture_type in {"virtual_machine", "windows_virtual_machine"}
    fixed = []
    unsupported = [
        "Automatic provisioning",
        "Existing-network attachment",
        "Custom resource composition",
    ]
    if compute:
        image = {
            "aws": "Amazon Linux 2023 or Ubuntu 24.04 LTS from Amazon/Canonical",
            "azure": "Ubuntu 22.04 or 24.04 LTS Gen2 from Canonical",
            "gcp": "Debian 12 or Ubuntu 24.04 LTS from debian-cloud/ubuntu-os-cloud",
        }[config.provider]
        if windows:
            image = "Windows Server 2022 English Full Base from Amazon"
        fixed.extend(
            [
                f"Operating system choices: {image}; x86_64/AMD64 only. "
                + (
                    "Marketplace version is configurable: latest (default) or an exact Major.Minor.Build version. Version availability remains unverified."
                    if config.provider == "azure"
                    else "Image version is configurable: latest (default) or an exact supported published image name. Availability and deprecation remain unverified."
                    if config.provider == "gcp"
                    else "Image version is configurable: latest (default) or an exact AMI ID matching the trusted owner and selected x86 OS filters. Regional availability remains unverified."
                ),
                (
                    "No application initialization is configured; RDP is restricted to the supplied administrator CIDR."
                    if windows
                    else "No application initialization is configured; SSH is restricted to the supplied administrator CIDR."
                )
                if standalone
                else "Startup installs nginx and serves HTTP on port 80.",
                "Creates a new network with a configurable private IPv4 range; subnet count and derivation are fixed by this recipe. Connected-network overlap requires manual preflight."
                if standalone
                else "Creates a new network and subnets with fixed address ranges.",
                "Creates one server."
                if config.architecture_type
                in {"virtual_machine", "windows_virtual_machine", "single_web_server"}
                else "Creates a tier with 2–20 instances (default 2); placement is fixed and automatic scaling is not configured.",
            ]
        )
        if config.provider == "azure":
            fixed.append(
                "Administrator username is configurable (default terraforma); password authentication is disabled."
            )
        elif standalone and config.provider == "aws":
            fixed.append(
                "Imports an RSA public key for EC2 Windows password recovery. The administrator is Administrator; recover the password through EC2 using the matching private key after provisioning. TerraForma neither collects nor decrypts passwords/private keys."
                if windows
                else "Imports the supplied public key into EC2; image username is ec2-user for Amazon Linux or ubuntu for Ubuntu. No private key is generated or stored."
            )
        elif standalone:
            fixed.append(
                "Uses Google OS Login with project SSH keys blocked. OS Login IAM roles and organization policy must be checked before access; no metadata SSH key is collected."
            )
        else:
            fixed.append("Administrator access is not configured by this recipe.")
        if config.provider == "gcp":
            fixed.append(
                "Interactive serial console access is explicitly disabled on generated VMs/templates, overriding project metadata inheritance. Read-only serial logs and IAM/organization policy require separate review."
            )
            unsupported.append("Interactive serial console access")
        unsupported.extend(
            [
                "Other Windows versions or publishers" if windows else "Windows VMs",
                "ARM64 VMs",
                "Custom images",
                "Multiple data disks" if standalone else "Data disks",
                "Custom initialization",
                "TLS setup",
            ]
        )
        if standalone:
            fixed.append(
                {
                    "aws": "Optional workload identity attaches an existing IAM instance profile; no roles or policy grants are created. Pass-role permission and existing policies require preflight.",
                    "azure": "Optional system-assigned managed identity is tied to this VM; no role assignments are created.",
                    "gcp": "Optional workload identity attaches an existing user-managed service account with cloud-platform scope; IAM roles and attachment permissions require preflight. Account changes require a stopped VM; automatic stopping is disabled.",
                }[config.provider]
            )
            fixed.append(
                "One optional empty data disk is configurable (default off); formatting, mounting, backups and recovery are not configured. Teardown can delete this managed disk."
            )
            unsupported.extend(
                [
                    "Existing disks or snapshots",
                    "Automatic disk formatting/mounting",
                    "Data disk backup policy",
                    "Custom performance for non-gp3 disks or above template limits"
                    if config.provider == "aws"
                    else "Custom disk IOPS/throughput",
                ]
            )
        if standalone and config.provider in {"aws", "gcp"}:
            if config.provider == "aws":
                fixed.append(
                    "gp3 boot/data disks expose 3,000–16,000 IOPS and 125–1,000 MiB/s throughput, defaulting to the included baseline. Extra performance adds charges; size/IOPS ratios are checked. Instance EBS performance and pricing require separate review."
                )
            fixed.append(
                "VM deletion protection is configurable (default enabled); disable and apply that change before deliberate deletion or replacement. It is not a backup."
            )
        elif standalone:
            unsupported.append("Azure VM deletion locks")
        if standalone and config.provider == "gcp":
            fixed.append(
                "Shielded VM Secure Boot is configurable (default enabled); vTPM and integrity monitoring stay enabled. Unsigned drivers/modules can prevent booting. Shielded setting changes require a stopped VM; automatic stopping is disabled."
            )
        if standalone and config.provider == "azure":
            fixed.append(
                "Accelerated networking is optional (default off). Check selected VM-size and guest-driver support; changing an existing VM's setting can require stopping and deallocating it. Firewall access is unchanged."
            )
            fixed.append(
                "Trusted Launch Secure Boot is configurable (default enabled); vTPM stays enabled. Check selected VM-size support and unsigned driver compatibility. Guest attestation and Defender monitoring are not configured."
            )
            fixed.append(
                "Optional boot diagnostics use Azure-managed storage (default off). Console output/screenshots can contain sensitive data; retention is not configurable and managed diagnostic blobs are currently not billed; application logging, alerts and custom diagnostic storage are not configured."
            )
    elif config.architecture_type == "secure_database":
        fixed.extend(
            [
                "Creates managed PostgreSQL with a standby, backups, and deletion protection.",
                "Database capacity, version selection, and backup settings are fixed by this recipe.",
            ]
        )
        unsupported.extend(
            ["Other database engines", "Database migrations", "Custom backup policy"]
        )
    else:
        fixed.append(
            "Creates cloud object storage and one index.html object; storage policy is fixed by this recipe."
        )
        unsupported.extend(["Custom domains", "CDN and TLS setup", "Dynamic application hosting"])
    return {
        "id": f"{config.provider}/{config.architecture_type}",
        "provider": config.provider,
        "workload": config.architecture_type,
        "name": WORKLOADS[config.architecture_type],
        "workflow": "offline_generation",
        "access_modes": ["private", "public"],
        "fixed_choices": fixed,
        "image_choices": list(LINUX_IMAGE_CHOICES[config.provider]) if compute else [],
        "unsupported": unsupported,
        "account_checks": "unverified",
        "deployment_checks": "unverified",
        "preflight_required": [
            "Cloud account identity and permissions",
            "Region, image, machine and disk availability",
            "Quotas, organization policy and expected costs",
            "Network access, Terraform plan and protected state storage",
        ],
    }


def recipe_catalog() -> list[dict]:
    return [
        recipe_capabilities(
            WizardConfig(provider=provider, project_name="catalog", architecture_type=workload)
        )
        for provider in PROVIDERS
        for workload in WORKLOADS
        if workload != "windows_virtual_machine" or provider == "aws"
    ]
