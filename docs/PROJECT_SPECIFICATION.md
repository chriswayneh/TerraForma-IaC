# Project specifications

Available on `main` during v0.3 development. The v0.2.0 release does not include this workflow.

A project specification records a recipe and its non-secret Terraform inputs. The browser Configure step and terminal `terraforma wizard` ask about each declared variable using the same contract. Required answers must be supplied; defaults can be reviewed and changed. Generation, local validation, and download use those same answers. Sensitive fields show an external environment-variable reference instead of asking for a password.

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

The terminal command writes the three Terraform files and refuses to overwrite an existing Terraform configuration. Browser downloads also include the non-secret specification for reuse. Optional remembered browser choices still save only the original questionnaire selections; additional input answers are not retained in browser storage.

Replace the example account ID with your intended AWS account. Every AWS recipe now requires a 12-digit `aws_account_id` and writes the provider's [account allowlist](https://registry.terraform.io/providers/hashicorp/aws/latest/docs/html) to guard later provider operations against an unintended authenticated account. Azure recipes require a subscription ID; GCP recipes require a project ID. The compiled result records that target and explicitly marks identity unverified. These fields are account references, not credentials; generation does not sign in or prove access. Earlier development AWS manifests need this new input added before they can compile or import.

To reopen a project, extract `terraforma.project.json` from its ZIP and select **Load project** in the browser. The file is validated locally before its answers and preview are restored. Imports never start validation or deployment, and do not enable AI or save additional answers in browser storage. Unsupported schema/template versions, duplicate JSON keys, missing answers, and files larger than 64 KiB are rejected. The development [AWS web-server example](../examples/aws-web.project.json) can be loaded the same way.

## Secrets and validation

Sensitive variables remain required Terraform variables without generated defaults. The contract identifies their `TF_VAR_...` environment variable. A database recipe can record `"secret_references": {"database_password": "TF_VAR_database_password"}`; it must not include the password value in `inputs`. The tool does not read that environment variable during generation.

Unknown input names, private keys, secret values in declared sensitive fields, missing required non-secret inputs, invalid UUID/CIDR formats, and incompatible GCP region/zone combinations are rejected. Request/CLI errors omit input values. This is not a general detector for secrets hidden in arbitrary non-secret text such as website HTML; review manifests and generated files before sharing them.

Azure SSH inputs accept OpenSSH Ed25519 or RSA public keys, matching [Microsoft's supported formats](https://learn.microsoft.com/en-us/azure/virtual-machines/linux/create-ssh-keys-detailed). The validator checks base64 encoding, algorithm identity, binary field lengths, and RSA integers with a minimum 2048-bit modulus. This is structural validation, not proof of key ownership, cryptographic validity, or successful VM authentication. Private keys, authorized-keys options, ECDSA, truncated blobs, and trailing fields are rejected.

## Current scope

The contract is derived from the actual variables declared by the existing recipes, so their questions and HCL variables stay aligned. It does not expose settings still hardcoded in those recipes, such as all image, OS, network, and availability choices. The complete VM adapter work remains on the roadmap.

Existing compute recipes now expose VM size, boot-disk size, and supported disk classes. Boot sizes are whole numbers in a bounded range: 20–2048 GiB for AWS/GCP and 30–2048 GiB for Azure. These are the current recipe limits, not universal cloud limits. Both the contract and generated Terraform enforce them. The selected image can impose a higher minimum, and live account/SKU/storage compatibility still requires preflight.

Generation is offline. Provider permissions, account identity, live image/SKU availability, quotas, and deployment are not established by the input checks. Schema/template versions are recorded; the current development workflow does not yet promise cross-version migration or reproducible generation across changing development commits.

## Environment labels

Every recipe exposes a defaulted `environment` input, using 3–20 lowercase letters, digits, or hyphens. The contract and Terraform enforce the same format. AWS uses provider default tags for supported resources; Azure tags the resource group only, whose tags do not automatically propagate to its resources; GCP labels the generated VM/template, Cloud SQL settings, or storage bucket. Network/supporting resources without label support are not covered.

The label appears in compiled target metadata and the project guide. It does not isolate credentials or state and does not change resource names. Use distinct project names for distinct environments until the multi-environment/state workflow is implemented.

## Recipe capabilities

The Configure step includes an expandable **Recipe defaults and limits** section. It identifies fixed operating systems, initialization, network layouts, instance counts, and features outside the selected recipe. ZIP project guides include the same information.

Use `terraforma catalog` for a readable catalog or `terraforma catalog --json-output` for structured metadata. The local API exposes the same catalog at `/api/catalog` and includes selected capabilities in input contracts and compiled project responses. Account and deployment checks remain explicitly unverified until a future account preflight workflow establishes them.
