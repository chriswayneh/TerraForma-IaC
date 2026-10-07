# TerraForma-IaC roadmap

Revised October 6, 2026. This roadmap supersedes the initial template-generator roadmap.

TerraForma-IaC is becoming a local infrastructure workspace for configuring, provisioning, and operating supported infrastructure across AWS, Azure, and Google Cloud. The interface explains the decisions and asks for the inputs needed by the selected resources. Simple mode offers safe defaults; advanced mode exposes supported provider-specific settings.

The platform will support a growing, explicitly documented resource catalog. It will not claim to provision every resource or accept arbitrary AI-generated commands as trusted automation. Unsupported requests should be identified clearly and become catalog work, rather than silently producing an incomplete configuration.

## Current checkpoint · v0.2.0.dev0

Implemented: local sky-blue web UI, terminal wizard, twelve provider/workload templates, file previews and downloads, resource explanations, optional saved non-secret choices, Terraform/TFLint validation, optional AI diagnostics, and Windows/Linux CI.

Limits: this is a generator and structural validator. It does not collect all VM settings, execute plans, apply infrastructure, manage state, or orchestrate Terragrunt. Templates have structural validation evidence; live cloud deployment and live OpenAI requests remain unverified. No release is tagged.

## Phase 1 · Security and project foundation · v0.3

Status: next implementation phase.

- Define a versioned project specification shared by the CLI, UI, generator, and automation API.
- Record provider, account identity, environment, resource selections, dependencies, and template versions without persisting credentials.
- Add explicit capability metadata so supported, unsupported, and unverified configurations are distinguishable.
- Add local policy review for Terraform plan JSON: destructive changes, broad network access, missing protections, and unresolved policy coverage.
- Apply resource-specific encryption and access defaults; explain unavoidable provider defaults.
- Bound request bodies, configuration sizes, subprocess duration, and job concurrency.
- Keep cloud credentials in provider credential chains; make AI transmission opt-in throughout the product.
- Specify artifact permissions, log redaction, state ownership, dependency trust, and recovery behavior before adding apply.

Exit criteria: invalid specifications fail closed; review reports expose no raw plan values; policy decisions have meaningful tests; current behavior and remaining security gaps are documented. No apply endpoint is introduced in this phase.

## Phase 2 · Complete VM configuration · v0.4

Status: planned after the foundation.

- Guided Linux and Windows VMs for EC2, Azure Virtual Machines, and Google Compute Engine.
- Provider identity and region/zone selection; image families, supported custom images, machine size, architecture, and count.
- Boot/data disk size, type, encryption, managed-key references, and deletion behavior.
- New or existing networks/subnets, private/public addresses, explicit inbound rules, and egress choices.
- SSH public keys, identity-based access, or references to external secret mechanisms for Windows administration.
- Tags/labels, initialization scripts from trusted local files, availability choices, and explanations of cost drivers.
- Provider-aware questions and validation; advanced options stay behind progressive disclosure.
- Existing web-server recipes become compositions of the same VM/network primitives.

Exit criteria: users can supply every required input for each documented VM pattern through the guided workflow. Structural/lint tests cover supported combinations. Dedicated test-account deployments verify Linux/Windows creation, access, and teardown; unsupported combinations are rejected explicitly.

## Phase 3 · Networks, storage, and identity · v0.5

Status: planned.

- Compose VPC/VNet networks, subnets, routing, security groups/firewalls, NAT, and private endpoints.
- Object storage, managed disks, access policies, lifecycle settings, and backup choices.
- VM roles/service accounts/managed identities with least-privilege examples.
- Distinguish creation from use of existing resource IDs; inspect account permissions without silently granting more access.
- Resource dependency graph, compatibility checks, and provider-specific required-input forms.

Exit criteria: multi-resource projects generate consistent references, networking decisions are explicit, and network/access policy tests catch documented unsafe cases.

## Phase 4 · State and plan workflow · v0.6

Status: planned; prerequisite for product-managed provisioning.

- Authenticated account preflight, environment selection, and clear target-account confirmation.
- Configure supported remote state backends with encryption, access controls, locking, and recovery documentation.
- Separate backend bootstrap from ordinary workloads; avoid storing backend credentials in configuration.
- Run trusted configurations through init, validate, lint, and saved-plan creation.
- Display creates, updates, replacements, deletes, costs/limitations, and policy findings in plain language.
- Protect plan/state artifacts and retain only necessary, redacted audit metadata.
- Bind review to the saved-plan digest, project/environment identity, configuration digest, and policy version; invalidate approval when those change.

Exit criteria: concurrent operations respect locks, drift and stale artifacts are handled, and review corresponds to the exact artifact intended for apply. Saved plans may contain secrets and must never be committed or sent to AI by default.

## Phase 5 · Approved provisioning and lifecycle · v0.7

Status: planned; requires verified state and plan controls.

- Apply only an explicitly approved saved plan to the confirmed account/environment.
- Apply authorization separate from generation; no hidden auto-approve behavior in the beginner workflow.
- Bounded execution, progress, cancellation, failures, and safe recovery instructions.
- Redacted local operation history and clear outputs without exposing sensitive output values.
- Separate destroy planning and explicit destructive approval; protect production environments and protected resources.
- Drift review and rerun workflows, with state-aware behavior and no assumption that partial apply rolled back.

Exit criteria: tests prove rejected/stale approvals cannot execute, failure does not become success, wrong-target operations are blocked, and dedicated cloud tests verify creation, updates, and cleanup. Cancellation is not described as rollback.

## Phase 6 · Multi-environment automation and Terragrunt · v0.8

Status: planned; Terragrunt remains optional.

- Reusable project modules and dev/test/prod configuration overlays with isolated state.
- Generate Terragrunt units/stacks when resource dependencies and environment reuse justify them.
- Pin supported Terraform/Terragrunt versions and document generated layout.
- Dependency-aware planning and execution with an explicit selected scope; no accidental account-wide run-all.
- Per-unit plan review, approvals, failure reporting, and lock-aware concurrency.
- GitHub Actions with short-lived cloud identity via OIDC, pull-request plans, protected apply environments, and minimal token permissions.
- Scheduling integrates with the user's chosen runner; recurring destructive actions require an explicit policy.

Exit criteria: a sample multi-environment stack demonstrates ordering, independent state, approvals, retries/recovery, and target isolation. Plain Terraform projects remain fully supported.

## Phase 7 · Broader workload catalog · v0.9

Status: planned; add individually verified capabilities rather than one universal template.

- Expand managed databases, private connectivity, backups, and restore workflows.
- Add TLS-enabled load balancing, DNS, certificates, autoscaling, and observability.
- Add container registries and supported managed container/Kubernetes patterns.
- Add supported serverless and scheduled-job patterns.
- Publish a compatibility matrix covering providers, resource families, OS/image support, execution modes, and verification status.
- Allow reviewed module extensions with pinned sources and explicit trust boundaries; arbitrary imports remain a trusted-user operation.

Exit criteria: each catalog entry declares required inputs, policy coverage, cost drivers, tests, deployment evidence, and teardown/recovery instructions. Experimental entries are labeled visibly.

## Phase 8 · Stable platform · v1.0

Status: planned.

- Stable project schema, migrations, CLI/API contracts, and module compatibility policy.
- Windows, macOS, and Linux installation and end-to-end workflow evidence.
- Accessible web UI, export/import of non-secret specifications, recovery documentation, and reproducible examples.
- Dependency pinning and update process, supply-chain checks, supported versions, and security response process.
- Independently reviewed execution boundaries and policy gates; documented limits remain visible.
- Versioned releases, tested quickstart, complete architecture/runbooks, and contributor process.

Exit criteria: a clean installation reproduces supported generation, review, plan, approved apply, and cleanup workflows in test accounts. There are no claims of universal coverage or security certification.

## Security gates across every phase

1. Generation is separate from execution. AI assists with explanations and drafting; it cannot approve a plan, choose a hidden target, or execute arbitrary commands.
2. Credentials and sensitive values do not enter browser storage or Git. External secret references are preferred; sensitive Terraform state and plans still require protection.
3. Network exposure and destructive changes are explicit decisions. Broad administrative access is blocked by default, and exceptions require visible, scoped justification.
4. Filesystem isolation is not a process sandbox. Native plugins execute code; untrusted modules require stronger isolation before they can become a supported product workflow.
5. Defaults reduce risk but are not deployment certification. Unknown policy coverage and unverified account capabilities remain visible and block automated approval.
6. Each phase must pass its exit criteria before being described as released. Release numbers are targets, not published artifacts or dates.

## Session checkpoint protocol

Use the available account-usage meter to stop new work at 20% remaining. It does not expose an exact per-chat token balance. Check between work batches and reserve time for cleanup. At the threshold: finish only the smallest safe checkpoint, run appropriate verification, commit and push completed work, record unfinished items, stop owned preview/validation processes, and leave cloud resources untouched unless an approved lifecycle operation is already in progress. Never kill an apply and describe it as rolled back.

## Reference decisions

Terraform saved plans can include sensitive values and applying a saved plan executes its recorded changes without another Terraform prompt: [HashiCorp plan reference](https://developer.hashicorp.com/terraform/cli/commands/plan).

Terragrunt's run queue orders operations across dependent units; it supports the later multi-environment workflow rather than replacing the basic questionnaire: [Terragrunt run queue](https://docs.terragrunt.com/features/stacks/run-queue/).
