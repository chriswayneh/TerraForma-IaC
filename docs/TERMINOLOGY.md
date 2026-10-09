# Terraform terms in plain language

[Getting started](GETTING_STARTED.md) · [All guides](README.md)

You can use TerraForma's questionnaire without writing Terraform. These terms help you read the resulting files and review reports.

| Term | Meaning in this project |
| --- | --- |
| **Infrastructure as code (IaC)** | Describing servers, networks and related resources in files that can be reviewed and reused. |
| **Terraform / HCL** | Terraform is the infrastructure tool. HCL is the configuration language used in its `.tf` files. |
| **Provider** | A Terraform plugin for a service such as AWS, Azure or Google Cloud. Installing it runs executable third-party code during checks. |
| **Recipe** | A built-in starting pattern, such as a VM, web tier, database or object-storage site. It supports a defined set of inputs. |
| **Resource** | An item Terraform would manage, such as a VM, subnet, bucket or firewall rule. |
| **Variable** | A named configuration input, such as region, VM size or network range. Required variables without defaults must be supplied before planning. |
| **Output** | A value Terraform would display after deployment, such as an address or resource identifier. |
| **Region / zone** | Cloud locations. A zone is a location within a region; availability and supported services vary. |
| **VM size / SKU** | A provider's machine configuration, usually including CPU and memory. A recognized name does not prove availability or image compatibility. |
| **CIDR** | A network range such as `10.0.0.0/24`. Access rules use it to identify allowed addresses. |
| **Plan** | Terraform's proposed changes. TerraForma can review a supplied JSON export but does not create a plan or approve applying it. |
| **Apply / destroy** | Operations that create/change resources or remove them. TerraForma does not run these operations. |
| **State / backend** | State records resources Terraform manages and can contain secrets. A backend is where that state is stored; protected storage and locking need separate setup. |
| **Sensitive variable** | A variable whose display is restricted. Its value may still be retained in state or saved plans. |
| **Lockfile** | `.terraform.lock.hcl` records selected provider versions and package checksums. Review and retain it for repeatable dependency selections. |
| **TFLint** | A lint tool that checks configured Terraform rules. Passing lint is not a security certification or deployment guarantee. |
| **CLI** | The command-line interface: commands entered in a terminal instead of a browser. |
| **Terragrunt** | An optional tool for organizing Terraform units and inputs across environments. TerraForma's development exporter writes files; it does not execute Terragrunt. |

See [generated artifacts](ARTIFACTS.md) for file details and [validation](VALIDATION.md) for what local checks establish.
