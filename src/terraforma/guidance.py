from terraforma.generator import WizardConfig


def infrastructure_guide(config: WizardConfig) -> dict:
    provider = config.provider
    compute = {
        "aws": "Amazon EC2",
        "azure": "Azure virtual machines",
        "gcp": "Google Compute Engine",
    }[provider]
    storage = {"aws": "Amazon S3", "azure": "Azure Blob Storage", "gcp": "Google Cloud Storage"}[
        provider
    ]
    database = {
        "aws": "Amazon RDS",
        "azure": "Azure Database for PostgreSQL",
        "gcp": "Google Cloud SQL",
    }[provider]
    network = "Azure virtual network" if provider == "azure" else "Virtual private cloud"
    entry = "Public internet" if config.is_public else "Private / authenticated access"
    components = []
    if config.architecture_type != "static_site":
        components.append(
            {
                "name": network,
                "explanation": "A separate cloud network groups your resources. Subnets divide its address space into smaller sections.",
            }
        )
    if config.architecture_type in {"single_web_server", "load_balanced_tier"}:
        balanced = config.architecture_type == "load_balanced_tier"
        components.append(
            {
                "name": compute,
                "explanation": f"{'The configured virtual machines share' if balanced else 'One virtual machine handles'} your web workload. Each runs nginx, which serves web traffic over HTTP.",
            }
        )
        components.append(
            {
                "name": "Network access rules",
                "explanation": "Only the configured HTTP traffic is permitted by the generated ingress rules. Public access does not automatically open SSH.",
            }
        )
        if balanced:
            components.append(
                {
                    "name": "Load balancer",
                    "explanation": "A front door distributes traffic across the configured web servers and checks whether they are responding.",
                }
            )
        route = [
            entry,
            "Load balancer" if balanced else "HTTP access rules",
            "Configured web server tier" if balanced else "Web server",
        ]
    elif config.architecture_type == "secure_database":
        components.append(
            {
                "name": database,
                "explanation": "A managed PostgreSQL service stores application data. A standby and backups help with availability and recovery; they add ongoing cost.",
            }
        )
        components.append(
            {
                "name": "Restricted connections",
                "explanation": "The database is private by default. Public mode still requires you to supply a permitted client address or network.",
            }
        )
        components.append(
            {
                "name": "Deletion protection",
                "explanation": "The template makes accidental deletion harder. Review the provider's protection and final-backup settings before intentionally removing the database.",
            }
        )
        route = [entry, "Restricted database connection", "PostgreSQL + standby"]
    else:
        components.append(
            {
                "name": storage,
                "explanation": "Object storage holds files such as index.html. It does not run application code or include a database.",
            }
        )
        components.append(
            {
                "name": "Object access",
                "explanation": "Public mode lets anyone read the site objects. Private mode requires authenticated access and does not expose a public website.",
            }
        )
        components.append(
            {
                "name": "Stored-data encryption",
                "explanation": "These storage services encrypt stored data by default. That protects data at rest; it does not replace access controls or HTTPS.",
            }
        )
        route = [entry, "Object access policy", "Website files"]
    return {"route": route, "components": components}
