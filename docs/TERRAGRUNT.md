# Optional Terragrunt environment export

Terragrunt helps organize repeated infrastructure configurations. TerraForma's development CLI can export several saved projects as independently configured units. Matching recipes share one local Terraform module, so environment-specific answers do not require copying the module's code.

Plain Terraform generation remains the default. This export is an early part of the [multi-environment roadmap](ROADMAP.md#phase-6), not a deployment workflow.

## Export saved projects

Create each project through the questionnaire, configure its actual environment, account, region and resource names, then save its project JSON. Export the selected files into a new directory:

```shell
terraforma export-terragrunt --unit dev=dev.project.json --unit test=test.project.json --dir environment-bundle
```

The command accepts up to twelve units. Names use lowercase letters, numbers and hyphens, starting with a letter; paths and reserved Windows device names are rejected. Unit names organize directories; naming a unit `prod` does not change the project's environment or cloud target. Review each saved project's answers first.

| Output | Purpose |
|---|---|
| `modules/<digest>/` | Shared Terraform code for each distinct recipe |
| `units/<name>/terragrunt.hcl` | Local module reference and effective non-secret inputs |
| `units/<name>/terraforma.project.json` | Original validated project specification |
| `terraforma.units.json` | Unit targets and required external secret variables |
| `SHA256SUMS.txt` | Checksums covering every exported file except the checksum file itself |

Each module retains Terraform variable types, validation and recipe safeguards. Input strings escape HCL interpolation; reviewed script content is preserved. Secret values are never collected: supply the listed `TF_VAR_*` variables externally. Saved specifications and public SSH keys remain readable project inputs; keep operational identifiers appropriately private.

## Review before execution

The generated configuration pins **Terragrunt 1.1.6**, the locally tested version, and requires Terraform **1.6 or later, below 2.0**. Terragrunt is an optional external tool, not a Python package dependency. Generation needs neither Terragrunt nor cloud credentials.

For local configuration inspection with installed tools, select Terraform explicitly and one unit only:

```shell
terragrunt render --config environment-bundle/units/dev/terragrunt.hcl --json --tf-path terraform
```

Use the full path to Terraform if it is not on PATH. Render evaluates the generated configuration; it does not prove that the cloud account supports it. CI's native job installs checksum-verified Terragrunt 1.1.6 and runs this render check (`tests/test_terragrunt.py`) for AWS, Azure and GCP Linux and Windows units; `init`, `plan` and `apply` through Terragrunt are not exercised. With these generated files, there are no hooks, external module downloads, dependencies or remote-state reads. Review any edits before rendering: arbitrary Terragrunt configurations can contain executable functions and hooks.

**State is local in each unit's `.terragrunt-cache`.** Preserve this directory across runs; deleting it can lose the state needed to manage infrastructure. Separate unit directories do not guarantee distinct cloud targets or resource names. Configure reviewed remote state before production or team use. The exporter does not set up a bucket, change permissions, migrate state or enable backend bootstrapping.

Environment `TF_VAR_*` values can override Terragrunt inputs; review the execution environment. State and plans can contain secrets and must stay out of Git. Provider lock files belong to the execution workspace and should be reviewed and preserved for reproducibility; a generation checksum is not a provider lock.

Dependency discovery, shared remote-state configuration, cross-unit plan review and protected execution remain planned. TerraForma does not execute Terragrunt, plan, apply or destroy. Exporting units does not authorize a run across all units.

Primary references: [Terragrunt units](https://docs.terragrunt.com/features/units/), [configuration blocks and local sources](https://docs.terragrunt.com/reference/hcl/blocks/), [input precedence](https://docs.terragrunt.com/reference/hcl/attributes/#variable-precedence), and [Terragrunt releases](https://github.com/gruntwork-io/terragrunt/releases/tag/v1.1.6).
