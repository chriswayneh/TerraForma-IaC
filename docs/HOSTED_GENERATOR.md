# Hosted generator preparation

**Status: design and implementation checklist, not a deployed website.** This is offline preparation for [Phase 8 / v0.10.0](ROADMAP.md#phase-8). Dedicated cloud accounts are not needed for the generator's non-executing acceptance tests. The separate v0.4.0 live VM gates remain outstanding.

## First hosted workflow

Select a supported provider and workload, enter provisioning variables, inspect explained resources, then export the project. Reuse shared input contracts and generation behavior so local and hosted output agree. Keep the local UI/CLI supported. Begin with transient requests; persistent projects, team accounts and runner connections belong to Phase 9.

The first public service does not accept cloud credentials, Terraform state or plan uploads. It does not authenticate to clouds, execute native tools, install providers, invoke AI diagnostics or run user-selected modules/scripts. Configuration generation is not deployment approval.

Project references and reviewed initialization content can still be confidential. The hosted UI must explain that inputs are transmitted to the service, discourage secrets in free-text/script inputs and offer the local application for private work. Schema validation cannot reliably detect every secret embedded in text.

## Existing operations and proposed exposure

These are current local route names used to plan reuse. This table does not change their current behavior or make them safe for public exposure.

| Existing operation | Initial hosted scope | Preparation required |
| --- | --- | --- |
| `/api/catalog`, `/api/input-contract` | Reuse supported recipe metadata and input contracts | Bounded responses and version consistency |
| `/api/projects/import` | Import bounded non-secret specifications | Strict schema/UTF-8 checks; no raw input logging or retained uploads |
| `/api/projects/compile`, `/api/generate` | Generate configuration and explanations | Keep processing free of native execution, host paths and cloud access |
| `/api/download` | Return generated project ZIP | Bound output size, fixed allowed filenames and no persistent project directory |
| `/api/session` | Redesign | Local process tokens do not establish public-service session isolation |
| `/api/validate` | Excluded | Native Terraform/TFLint and optional AI diagnostics stay local |
| `/api/projects/preflight` | Excluded | Cloud CLI reads require separately authorized credentials and targets |
| `/api/plans/review` | Excluded | Raw plans may contain sensitive values; use local review |
| `/api/backends/*` | Deferred | Backend-intent references need a separate scope/privacy decision; no backend execution |

Expose an explicit allowlist in a separate service composition. Do not host the existing local app by relaxing its trusted-host middleware or enabling hidden buttons. Excluded routes must be absent at the server, independent of UI state.

## Implementation sequence

| Step | Bounded change | Completion evidence |
| --- | --- | --- |
| 1 | Extract/reuse pure generation and export operations without importing execution adapters into the public composition | Catalog, contracts, compile and export retain local behavior |
| 2 | Build an export-only service composition | Excluded routes absent; subprocess, cloud and AI calls fail tests if attempted |
| 3 | Define request/session boundaries | Host/origin policy, session isolation, rate/concurrency limits, request and output budgets |
| 4 | Adapt the browser workflow | Clear hosted/local scope, input privacy notice, no execution controls and accessible form errors |
| 5 | Verify artifact parity | Compare each supported generated filename and byte content, including receipts/checksums; ZIP metadata is tested separately |
| 6 | Prepare hosting operations | HTTPS, minimal redacted logs, dependency updates, retention/deletion, failure recovery and rollback |

Choose the deployment platform after the export-only behavior and resource budgets are measured. No hosting account, paid plan, domain purchase or public deployment is authorized by this document.

## Offline acceptance checks

| Check | Required result |
| --- | --- |
| Generation | Supported recipes produce the same project artifacts through local and hosted compositions |
| Inputs | Invalid, duplicate-key, oversized, deeply nested and unsupported-field requests fail without echoing values |
| Execution exclusion | Requests cannot invoke native binaries, cloud authentication/metadata adapters, AI endpoints or arbitrary module downloads |
| Filesystem | No user-selected host path, traversal, retained upload or shared per-project directory |
| Sessions | One session cannot retrieve another's inputs, artifacts or status; no shared mutable project state |
| Privacy | Bodies, script content, generated HCL and account references are absent from ordinary logs and error traces |
| Resource bounds | Oversized outputs and excess concurrent work are rejected predictably; failure releases owned resources |
| Browser | Keyboard navigation, labels, error focus, narrow-screen forms and download recovery work |
| Scope | No plan/state upload, cloud credential field, native validation or deployment control in the hosted workflow |

These tests can be implemented with synthetic specifications and local test clients. Passing them does not prove a production hosting configuration, cloud deployment or tenant-security certification. Public launch still requires actual deployment checks and review of the hosting boundary.

## Accounts and evidence

Continue offline while dedicated AWS/Azure/GCP test accounts are pending. Future live VM testing follows [VM acceptance](VM_ACCEPTANCE.md) with separately approved targets, spending boundaries, state and operations. Record offline, native, mocked and live results as distinct evidence levels in [Verification](VERIFICATION.md).
