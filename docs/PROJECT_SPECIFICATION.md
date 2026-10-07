# Project specifications

Available on `main` during v0.3 development. The v0.2.0 release does not include this workflow.

A project specification records a recipe and its non-secret Terraform inputs. The browser Configure step and terminal `terraforma wizard` ask about each declared variable using the same contract. Required answers must be supplied; defaults can be reviewed and changed. Generation, local validation, and download use those same answers. Sensitive fields show an external environment-variable reference instead of asking for a password.

If an answer fails a field check, the interfaces identify the declared field and a safe correction hint without repeating its submitted value. The browser focuses that field and clears its validation error when you edit it. Unknown or secret input names and malformed project files receive a generic error. No native validation starts for invalid project inputs.

```json
{
  "schema_version": 1,
  "template_version": "0.3.0.dev0",
  "recipe": {
    "provider": "aws",
    "project_name": "first-site",
    "architecture_type": "static_site",
    "is_public": false,
    "enable_encryption": true
  },
  "inputs": {
    "environment": "development",
    "aws_account_id": "123456789012",
    "region": "us-west-2",
    "index_html": "<html><body><h1>Hello</h1></body></html>"
  },
  "secret_references": {}
}
```

Save this as `terraforma.project.json`, then inspect the recipe's declared inputs and generate files:

```text
terraforma project-inputs --spec terraforma.project.json
terraforma generate --spec terraforma.project.json --dir first-site
```

Terminal generation writes the three Terraform files, the non-secret specification, a generation receipt, and checksums into a fresh output directory. It refuses to overwrite an existing Terraform configuration or metadata file and rolls back partial output on failure. Browser downloads include the same artifacts plus a project guide. See [artifact comparison](ARTIFACTS.md). Optional remembered browser choices still save only the original questionnaire selections; additional input answers are not retained in browser storage.

After generation or import, **Your configuration choices** lists the effective answers without requiring you to read Terraform. The ZIP guide includes the same summary. `answer` means a value recorded in the saved questionnaire, even when you accepted a suggested default; `default` means an omitted input resolved through the recipe; `recipe` means a controlled value such as the project name. External secret requirements show environment-variable names, never their values. Page content and SSH keys receive short descriptions rather than full content. Long text is shortened only for display; the configuration keeps the full accepted value.

To review a saved questionnaire from the terminal without running Terraform or writing files:

```text
terraforma describe --spec terraforma.project.json
terraforma describe --spec terraforma.project.json --json-output
```

Generation also rejects common state files, variable-value files, `.terraform`, and the Terraform lock file in the destination. This prevents mixing a new questionnaire with an initialized project or saved values. The terminal wizard checks an explicit destination before asking questions. Use a fresh output directory; existing-project migration and managed updates are later lifecycle workflows.

Replace the example account ID with your intended AWS account. Every AWS recipe now requires a 12-digit `aws_account_id` and writes the provider's [account allowlist](https://registry.terraform.io/providers/hashicorp/aws/latest/docs/html) to guard later provider operations against an unintended authenticated account. Azure recipes require a subscription ID; GCP recipes require a project ID. The compiled result records that target and explicitly marks identity unverified. These fields are account references, not credentials; generation does not sign in or prove access. Earlier development AWS manifests need this new input added before they can compile or import.

To reopen a project, extract `terraforma.project.json` from its ZIP and select **Load project** in the browser. The file is validated locally before its answers and preview are restored. Imports never start validation or deployment, and do not enable AI or save additional answers in browser storage. Unsupported schema/template versions, duplicate JSON keys, missing answers, and files larger than 64 KiB are rejected. The development [AWS web-server example](../examples/aws-web.project.json) can be loaded the same way.

## Secrets and validation

Answers use the type declared by the recipe contract. Boolean questions require actual JSON `true` or `false`; strings such as `"false"` and numeric values are rejected. AWS VM and web-tier recipes expose `detailed_monitoring`, disabled by default, and retain that choice through both questionnaires and project import/export. See [monitoring behavior and costs](LINUX_VM.md#provider-access).

Sensitive variables remain required Terraform variables without generated defaults. The contract identifies their `TF_VAR_...` environment variable. A database recipe can record `"secret_references": {"database_password": "TF_VAR_database_password"}`; it must not include the password value in `inputs`. The tool does not read that environment variable during generation.

Unknown input names, private keys, secret values in declared sensitive fields, missing required non-secret inputs, invalid UUID/CIDR formats, and incompatible GCP region/zone combinations are rejected. Request/CLI errors omit input values. This is not a general detector for secrets hidden in arbitrary non-secret text such as website HTML; review manifests and generated files before sharing them.

Azure SSH inputs accept OpenSSH Ed25519 or RSA public keys, matching [Microsoft's supported formats](https://learn.microsoft.com/en-us/azure/virtual-machines/linux/create-ssh-keys-detailed). The validator checks base64 encoding, algorithm identity, binary field lengths, and RSA integers with a minimum 2048-bit modulus. This is structural validation, not proof of key ownership, cryptographic validity, or successful VM authentication. Private keys, authorized-keys options, ECDSA, truncated blobs, and trailing fields are rejected.

## Current scope

The contract is derived from the actual variables declared by the existing recipes, so their questions and HCL variables stay aligned. It does not expose settings still hardcoded in those recipes, such as all image, OS, network, and availability choices. The complete VM adapter work remains on the roadmap.

Existing compute recipes now expose VM size, boot-disk size, and supported disk classes. Boot sizes are whole numbers in a bounded range: 20–2048 GiB for AWS/GCP and 30–2048 GiB for Azure. These are the current recipe limits, not universal cloud limits. Both the contract and generated Terraform enforce them. The selected image can impose a higher minimum, and live account/SKU/storage compatibility still requires preflight.

Standalone Linux VMs also expose `enable_data_disk`, default `false`. Its dependent `data_disk_size_gb` and `data_disk_type` questions appear only when enabled, using contract `visible_when` metadata. Sizes are 32–2048 GiB; available types depend on the provider. The CLI skips inactive questions; browser exports omit inactive answers and use recipe defaults for their unused Terraform variables. All supplied manifest values are still validated, including inactive fields. The configuration summary omits inactive disk size/type choices. See [data disk behavior and limits](LINUX_VM.md#optional-data-disk).

Generation is offline. Provider permissions, account identity, live image/SKU availability, quotas, and deployment are not established by the input checks. Schema/template versions are recorded; the current development workflow does not yet promise cross-version migration or reproducible generation across changing development commits.

## Environment labels

Every recipe exposes a defaulted `environment` input, using 3–20 lowercase letters, digits, or hyphens. The contract and Terraform enforce the same format. AWS uses provider default tags for supported resources; Azure tags the resource group only, whose tags do not automatically propagate to its resources; GCP labels the generated VM/template, Cloud SQL settings, or storage bucket. Network/supporting resources without label support are not covered.

The label appears in compiled target metadata and the project guide. It does not isolate credentials or state and does not change resource names. Use distinct project names for distinct environments until the multi-environment/state workflow is implemented.

## Recipe capabilities

### Azure administrator username

Azure compute recipes ask for `admin_username`, defaulting to `terraforma`. This recipe accepts 3–32 lowercase letters, digits, underscores, or hyphens, starting with a letter and ending with a letter or digit. Both the questionnaire and Terraform reject the [Azure reserved-name list](https://learn.microsoft.com/en-us/azure/virtual-machines/linux/faq), including `root` and `admin`. The narrower character/length format is a recipe choice. The answer configures the VM or scale set and its SSH public-key username; standalone VMs also return it as `ssh_username`. Password authentication remains disabled.

### Linux image selection

Compute recipes expose `os_image` as a supported choice, shared by terminal and browser forms. The selected image also determines the AWS package-manager startup script.

| Provider | Choices | Publisher constraint |
| --- | --- | --- |
| AWS | `amazon-linux-2023` (default), `ubuntu-24.04` | Amazon-owned AL2023 x86_64 AMIs, or Canonical owner `099720109477` with the Ubuntu Noble AMD64 server filter |
| Azure | `ubuntu-22.04` (default), `ubuntu-24.04` | Canonical marketplace Gen2 AMD64 server offers; Ubuntu 24.04 uses `ubuntu-24_04-lts:server` |
| GCP | `debian-12` (default), `ubuntu-24.04` | `debian-cloud/debian-12` or `ubuntu-os-cloud/ubuntu-2404-lts-amd64` |

The catalog accepts these image selectors only. Windows, ARM64, arbitrary image IDs, and custom publishers require future adapters. The generated image references resolve to the latest matching image at planning time; they do not pin an immutable image build. A matching specification or receipt cannot prove which image a future plan will select. Verify regional availability, machine architecture, publisher trust, organizational policy, and the exact resolved image in your Terraform plan before deployment. AWS Ubuntu ownership here is for the standard AWS partition; other partitions require separately reviewed identifiers.

Reference identifiers are based on the official [HashiCorp AWS tutorial](https://docs.hashicorp.com/terraform/tutorials/aws-get-started/aws-create), [Canonical Azure catalog](https://ubuntu.com/azure/docs/azure-how-to/instances/find-ubuntu-images/), and [Google Compute Engine OS documentation](https://docs.cloud.google.com/compute/docs/images/os-details?hl=en). Local schema and selector checks do not establish cloud availability or successful boot/access.

![Choosing a supported Linux image](images/linux-images.png)

### Tier capacity

Load-balanced compute recipes ask for `instance_count`, a whole number from 2 to 20 with a default of 2. The answer controls EC2 instances and target attachments, Azure scale-set instances, or the GCP managed instance-group target size. Single-server recipes keep exactly one VM and reject this extra input. This is initial capacity; autoscaling and custom placement are not configured. AWS distributes instances across its two generated subnets; Azure and GCP retain their existing recipe placement. Check quotas, availability, and per-instance compute/disk costs before deploying.

![Configuring tier capacity](images/tier-capacity.png)

### Database client access

Database recipes constrain client networks in both questionnaires and generated Terraform. AWS database client CIDRs and public GCP database client CIDRs accept an RFC1918 private subnet (`10/8`, `172.16/12`, or `192.168/16`) or an IPv4 `/24`–`/32` network. Prefer `/32` for a single public client. Larger public ranges require a separately reviewed configuration; this is a TerraForma recipe policy, not a cloud provider limit. Public HTTP web-server ranges use their own policy and can still accept `0.0.0.0/0`.

The public Azure database recipe accepts one client IPv4 address and rejects `0/8`, loopback, multicast, and reserved `224/3` addresses. In particular, it rejects `0.0.0.0`, which Azure interprets as [access from Azure services](https://learn.microsoft.com/en-ie/azure/postgresql/flexible-server/security-firewall-rules). Syntax and range checks do not establish that an address belongs to the user or is reachable. Private cloud networking and connection routing still need review.

The Configure step includes an expandable **Recipe defaults and limits** section. It identifies supported operating systems, fixed initialization/network layouts, capacity limits, and features outside the selected recipe. ZIP project guides include the same information.

Use `terraforma catalog` for a readable catalog or `terraforma catalog --json-output` for structured metadata. The local API exposes the same catalog at `/api/catalog` and includes selected capabilities in input contracts and compiled project responses. Account and deployment checks remain explicitly unverified until a future account preflight workflow establishes them.
