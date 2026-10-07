# TerraForma-IaC roadmap

TerraForma-IaC helps people create and understand Terraform before they have learned its syntax. The product is a lightweight local workspace: deterministic infrastructure templates, guided decisions, visible code, and local validation.

Features are shipped in small, reviewable milestones. These are targets, not promised dates.

## Phase 1 · Backend foundation · v0.1

Status: implemented and tested; this is a historical milestone, not a published release.

- Python CLI questionnaire and reusable generation modules.
- AWS, Azure, and Google Cloud templates for web servers, load-balanced tiers, PostgreSQL, and static sites.
- Filesystem-isolated Terraform and TFLint validation with timeouts and error capture.
- Optional OpenAI explanations with strict response validation, bounded retries, and known-secret redaction.
- Automated tests, native provider checks, package build checks, and reusable GitHub Action.

Exit criteria: all template combinations pass structural validation and lint; failure paths preserve unsuccessful exit codes. Completed locally. Cloud deployments and live OpenAI requests have not been verified.

## Phase 2 · Local visual workspace · v0.2.0

Status: in progress.

- FastAPI server bound to loopback, with buildless HTML, CSS, and JavaScript.
- Three-step cloud/workload/configuration questionnaire.
- File preview, copy, and ZIP download with project-specific instructions.
- Required-input guidance, access explanations, and qualitative cost information.
- Local validation results and an explicit opt-in for AI explanations.
- API tests, browser walkthrough, installation documentation, and a public GitHub repository.

Exit criteria: a user can generate, inspect, validate, and download a project through the UI; the installed wheel contains the UI assets; the documented launch command works. No cloud credentials are entered in the browser, and the app does not apply infrastructure.

## Phase 3 · Beginner onboarding · v0.3

Status: planned.

- First-run tool checks with platform-specific installation instructions.
- Guided setup for required inputs and provider authentication.
- Resource explanations and a diagram of the generated infrastructure.
- Saved non-secret project preferences and a sample walkthrough for each provider.
- Accessible keyboard navigation and broader mobile/tablet testing.
- Short demo recording, screenshots, and contributor-friendly issue templates.

Exit criteria: a new user can complete the documented example without prior Terraform knowledge and explain the generated resources.

## Phase 4 · Safer infrastructure patterns · v0.4

Status: planned.

- HTTPS patterns and certificate/domain guidance for web workloads.
- More precise network restrictions and provider-specific security lint profiles.
- Documented state-storage options and secret-handling practices.
- Explicit availability/cost tradeoffs, including NAT and standby resources.
- Verified deployment examples in dedicated cloud test accounts, with teardown instructions.

Exit criteria: the reference patterns have documented deployment evidence, access checks, and cleanup evidence. Structural validation alone is never presented as deployment or security certification.

## Phase 5 · Power-user workflow · v0.5

Status: planned; prioritize after feedback from the beginner workflow.

- Controlled code editing and validation of trusted imported configurations.
- Explicit boundaries for local modules and referenced assets.
- Project persistence and a configuration migration policy.
- Versioned template metadata and reproducible provider selections.
- Optional cost-estimation integration if it adds useful information without requiring a heavy runtime.

Exit criteria: editing and import work without obscuring the beginner path, and local execution risks are explained clearly.

## Phase 6 · Stable release · v1.0

Status: planned.

- Stable CLI/API contracts and documented compatibility policy.
- Tested installation on Windows, macOS, and Linux.
- Repeatable browser, package, native-validation, and integration checks.
- Complete user guides, architecture documentation, release notes, and contributor process.
- Tagged package and GitHub Action releases with a tested quickstart.

Exit criteria: a clean installation can reproduce the complete guided workflow, published examples have verification evidence, and known limitations are visible.

## Scope and engineering choices

- Keep the local UI lightweight; a React toolchain is unnecessary for the current workflow.
- Generate infrastructure from reviewed templates; use AI for explanations, not automatic deployment decisions.
- Keep generation usable without cloud credentials, an OpenAI key, or installed Terraform binaries.
- Do not implement automatic apply/destroy as part of the beginner workflow.
- Treat the current sandbox as filesystem isolation, not containment of untrusted plugins or code.
- Use `0.x` versions while interfaces evolve. Mark features as shipped only after the corresponding checks pass.

## Release evidence

Each release should include the working product, a concise architecture diagram, automated test and CI evidence, an honest list of limitations, and the reasoning behind major tradeoffs. Never claim live deployment, security certification, or API verification that has not been performed.
