# Validate a trusted configuration

[Getting started](GETTING_STARTED.md) · [Security overview](SECURITY_OVERVIEW.md) · [All guides](README.md)

Local validation checks Terraform structure and configured lint rules. It does not create cloud resources, run a plan, or approve deployment. You can generate and export without these checks.

## Install the optional tools

Install Terraform using [HashiCorp's installation guide](https://developer.hashicorp.com/terraform/install) and TFLint using [its official installation guide](https://github.com/terraform-linters/tflint#installation). Choose executables for your operating system and CPU architecture. Put them on PATH, open a new terminal and check:

```text
terraform -version
tflint --version
```

Restart the TerraForma server after changing PATH. The local UI shows tool availability; TerraForma does not automatically install tools. Project native CI currently uses Terraform 1.14.0 and TFLint 0.61.0; a PATH check does not verify binary trust or version compatibility.

Choose **Validate locally** in the browser, or run from the repository folder on Windows:

```powershell
.venv/Scripts/python.exe -m terraforma.cli run --dir ./output/first-project --no-ai
```

On macOS/Linux use `.venv/bin/python`. A first initialization may take several minutes to download providers. No cloud credentials are required for the built-in structural checks.

## What the command does

| Order | Operation | Purpose |
| --- | --- | --- |
| 1 | Find Terraform and TFLint on PATH | Select the installed native tools |
| 2 | Copy eligible files to a temporary workspace | Preserve the original configuration during checks |
| 3 | `terraform init -backend=false -input=false` | Initialize providers/modules without initializing a state backend |
| 4 | `terraform validate -json` | Check configuration structure |
| 5 | `tflint --init` and recursive lint checks | Initialize configured lint plugins and run their rules |
| 6 | Collect results and remove the temporary workspace | Return readable diagnostics |

Dependent checks stop if initialization fails. A failed, missing, timed-out or incomplete check returns failure. The command captures stdout/stderr with a 512 KiB limit per stream and uses a per-command timeout (`--timeout`, default 120 seconds). AI advice cannot turn a failed result into a passing result.

Native binaries, providers, modules and linter plugins still execute with host authority and network access. Temporary files are not containment for untrusted code. Process-group cleanup reduces leftover helpers but cannot guarantee containment of hostile descendants. Validate trusted configurations and plugins only.

## Files, modules and dependency locks

Local modules and referenced assets must fit inside the selected Terraform root. External/sibling paths, linked files and directory junctions are unsupported. Limits are 8 MiB per file and 32 MiB per copied workspace, including checks of actual bytes read.

The copy excludes common state files, saved plans and plan JSON, `.tfbackend`, local Terraform CLI configuration, crash logs, `.env`, variable-value files, Terraform caches, Git directories and virtual environments. Matching is case-insensitive; custom filenames can still contain sensitive material. Existing `.terraform.lock.hcl` and `.tflint.hcl` are preserved.

An existing provider lock is used in read-only mode. Changed requirements, incompatible selections or missing checksums may fail initialization; TerraForma does not retry with an upgrade. Review the real project and its lockfile instead. Without a lock, temporary provider selections are unpinned and the new temporary lock is discarded. Initialize the reviewed project separately and retain its reviewed lockfile in Git.

Built-in TFLint Terraform rules run by default. Cloud-specific rules require explicit plugin configuration. TFsec is not implemented. The browser validates regenerated built-in templates; arbitrary HCL and host-directory import are not exposed by its API.

## Optional AI explanations

The browser's **Explain failures with AI** and the CLI's `--ai` option are off by default. If enabled, failed logs are sent to OpenAI using `OPENAI_API_KEY` from the server/CLI environment. Redaction is best effort; logs can include source snippets or unrecognized sensitive data. Leave AI off where external diagnostic transmission is inappropriate. The model defaults to `gpt-4o`; set `TERRAFORMA_OPENAI_MODEL` in the same environment to use a different OpenAI chat-completions model that supports structured JSON output.

Suggestions are advice only. TerraForma does not apply suggested edits or execute suggested commands. No key is needed for local validation.

## GitHub Action

The released Action installs Python, Terraform, TFLint and the package, then validates a trusted target directory. This example keeps AI off:

```yaml
steps:
  - uses: actions/checkout@v4
  - uses: chriswayneh/TerraForma-IaC@v0.3.0
    with:
      target_dir: infrastructure
      explain_with_ai: 'false'
```

For organizational use, replace version tags with reviewed full commit SHAs and review the [dependency trust guidance](DEPENDENCIES.md). Cloud-specific plugins and checks require their own review.

> **Warning: do not run this Action on untrusted code with secrets or write access.** Validation runs `terraform init` and `tflint --init` on the target directory, which downloads and executes the providers, modules and TFLint plugins that directory declares, including a `.tflint.hcl` it supplies. Do not use it in `pull_request_target` or `workflow_run` workflows that check out fork code, and do not pass `openai_api_key` or cloud credentials to jobs that validate forks. For fork pull requests, use the plain `pull_request` trigger with read-only `permissions: contents: read` and no secrets.

## Troubleshooting

| Result | Next step |
| --- | --- |
| Missing executable | Check PATH in a new terminal and restart the server. |
| Initialization fails | Review network/proxy access, registry availability, disk space and dependency/lockfile diagnostics. |
| Timeout | Review the failing stage; increase `--timeout` only for a trusted operation with an understood download/runtime delay. |
| File or output bound exceeded | Review the configuration and reduce unnecessary assets/output; bounds are not a success condition. |
| Provider lock mismatch | Review the real project's provider requirements and lockfile; do not silently upgrade to bypass the failure. |
| "Text file busy" or a cached-package checksum mismatch with `TF_PLUGIN_CACHE_DIR` set | Terraform's shared plugin cache is not safe for concurrent `init` runs. Validation keeps your cache setting for speed, so avoid running several validations (or other `terraform init` runs) against the same cache at once, then retry. |
| Validation passes | Continue human review; account permissions, costs, capacity, connectivity and guest behavior remain unverified. |
