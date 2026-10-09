# Security and adoption overview

[Project home](../README.md) · [Getting started](GETTING_STARTED.md) · [Security policy](../SECURITY.md)

TerraForma-IaC is a local configuration-generation and review tool. Its supported launcher serves one user's browser on `127.0.0.1`; it is not a shared service. Released v0.3.0 generates files and performs optional checks. Expanded VM inputs on `main` are in development for v0.4.0.

## What it can authorize

**Nothing in TerraForma grants deployment approval.** Generation, local validation, target metadata checks, plan review and generation receipts supply information for a human review. The application does not run Terraform plan, apply or destroy, grant cloud permissions, or configure protected remote state.

## Data and network access

| Operation | Data handled | Network access / storage | User control |
| --- | --- | --- | --- |
| Generate and preview | Recipe selections and supported configuration inputs | Local browser and Python server; generated data stays in memory until saved/exported | Select the recipe and inputs |
| Remember choices | Non-secret questionnaire answers | Browser local storage | Optional; uncheck to remove stored choices |
| Export a project | Terraform, saved answers, receipts and instructions | Browser download or local CLI output directory | User chooses export and destination |
| Validate locally | Generated configuration, or a trusted CLI-selected directory | Temporary files; Terraform/provider/TFLint code runs with host authority and can download dependencies | Optional native check; only trusted files/tools/plugins |
| Check a cloud target | Declared account/subscription/project and optional VM metadata | Cloud CLI uses existing credentials and contacts provider services; credential caches may refresh | Explicit consent; default checks remain offline |
| Review plan/backend inputs | Supplied plan JSON or non-secret storage references | Local bounded processing; these files are not sent to AI by the review operations | User supplies the file; results do not approve deployment |
| Explain a validation failure | Redacted failed-tool logs, which may include source snippets | Sent to OpenAI using the server/CLI environment's API key | AI is off by default; separate opt-in; redaction is best effort |

Cloud passwords and API keys are not browser input fields. A project can still contain operational information such as identifiers, network ranges, labels and reviewed initialization content. Keep exports according to your organization's data classification.

## Implemented controls and their limits

| Control | What it provides | What it does not establish |
| --- | --- | --- |
| Loopback launcher, trusted-host checks and local session token | Controls for the local browser request flow | Shared-service authentication or tenant isolation |
| Strict input contracts and literal HCL escaping | Rejects unsupported fields and separates literal inputs from authored expressions | Compatibility with every SKU, image or organization policy |
| Bounded JSON, file reads and command capture | Limits input size, output volume and command duration; failures remain failures | Containment of hostile native tools, plugins or detached descendants |
| Temporary validation workspace | Separates copied/generated files from the original project | Isolation from host credentials, native configuration or network access |
| External secret references | Avoids collecting secret values in saved project answers | Secret-free Terraform state, plans or logs |
| Checksums and generation receipts | Detects differences against recorded bytes | Signed provenance, publisher identity or deployment authorization |
| Local plan policy review | Flags selected destructive and security concerns, with gaps visible | Exhaustive risk analysis or permission to apply |

## Adoption path

| Stage | Suggested boundary | Evidence or decision needed |
| --- | --- | --- |
| **Evaluate generation** | Local user workstation; non-secret example inputs; AI and cloud checks off | Confirm exported files, recipe scope and expected workflow |
| **Evaluate native checks** | Approved Terraform/TFLint binaries and plugins; trusted generated configuration | Review package sources, provider constraints and lockfiles; permit necessary dependency downloads |
| **Prepare a cloud test** | Dedicated account/subscription/project and least-privilege credentials | Explicit scope, cost controls, state protection, access method and cleanup plan |
| **Approve organizational use** | Your organization's established infrastructure/change process | Review generated code and plans, credentials, effective permissions, state recovery and live evidence |

The tool does not supply a protected execution service. Future hosted generation and approved runners are separate [roadmap phases](ROADMAP.md), with additional authentication, isolation and lifecycle gates.

## Verification status

Offline tests cover input rejection, generation, artifact handling, local request controls and diagnostic contracts. Native tests inspect provider schemas and lint behavior; mocked plans remain distinct from real deployment evidence. Exact results and source revisions appear in the [verification record](VERIFICATION.md) and [GitHub checks](https://github.com/chriswayneh/TerraForma-IaC/actions/workflows/ci.yml).

A scoped static source review of all 48 files under `src/terraforma` at `4ee27a7` completed without reportable findings. It does not certify the product, cover subsequent changes or replace runtime/cloud testing.

**Live Linux/Windows creation, login, initialization and cleanup for AWS, Azure and GCP remain pending dedicated accounts. v0.4.0 is unreleased.** A successful offline/native check does not establish cloud capacity, prices, compatibility, effective access or guest behavior.

## Before an external deployment

Use the organization's normal approval process. Review the intended resources and costs, provider authentication, public exposure, TLS, identity permissions and any initialization script that will run on a guest. Establish protected state/plan storage, a reviewed provider lockfile and a cleanup/recovery procedure. Sensitive variables can persist in state even when their console display is hidden.

The [security policy](../SECURITY.md) defines execution boundaries and vulnerability reporting. [Dependency trust](DEPENDENCIES.md), [state protection](STATE_PROTECTION.md), [plan review](PLAN_REVIEW.md) and [VM acceptance](VM_ACCEPTANCE.md) provide the detailed evidence and remaining requirements.
