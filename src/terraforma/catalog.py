from terraforma.generator import WizardConfig

PROVIDERS = ("aws", "azure", "gcp")
WORKLOADS = {
    "single_web_server": "Single web server",
    "load_balanced_tier": "Load-balanced application",
    "secure_database": "Managed PostgreSQL",
    "static_site": "Object-storage website",
}


def recipe_capabilities(config: WizardConfig) -> dict:
    compute = config.architecture_type in {"single_web_server", "load_balanced_tier"}
    fixed = []
    unsupported = [
        "Automatic provisioning",
        "Existing-network attachment",
        "Custom resource composition",
    ]
    if compute:
        image = {
            "aws": "Amazon Linux 2023 x86_64; latest matching Amazon image",
            "azure": "Ubuntu 22.04 LTS Gen2; latest Canonical image",
            "gcp": "Debian 12 from debian-cloud",
        }[config.provider]
        fixed.extend(
            [
                f"Operating system: {image}.",
                "Startup installs nginx and serves HTTP on port 80.",
                "Creates a new network and subnets with fixed address ranges.",
                "Creates one server."
                if config.architecture_type == "single_web_server"
                else "Creates a tier with 2–20 instances (default 2); placement is fixed and automatic scaling is not configured.",
            ]
        )
        if config.provider == "azure":
            fixed.append(
                "Administrator username is terraforma; password authentication is disabled."
            )
        else:
            fixed.append("Administrator access is not configured by this recipe.")
        unsupported.extend(
            ["Windows VMs", "Custom images", "Data disks", "Custom initialization", "TLS setup"]
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
    ]
