# v0.4.0 VM release readiness

**v0.4.0 remains unreleased.** This audit maps the development implementation to the [VM configuration roadmap](ROADMAP.md#phase-2), [input contract requirements](VM_INPUTS.md) and [live acceptance gates](VM_ACCEPTANCE.md). Offline evidence cannot substitute for creation, guest access or cleanup in a dedicated account.

## Input completeness

The combined reference projects declare the following variables. Counts include defaults, conditional controls and recipe-controlled values; they are not the number of questions displayed at once. Every required non-secret field resolves to an actual generated value/default. Azure Windows leaves its password external.

| Provider | Linux variables | Windows variables | Unresolved required non-secret fields | External access requirement |
|---|---:|---:|---:|---|
| AWS | 46 | 45 | 0 | Private keys and Windows password recovery stay outside TerraForma |
| Azure | 40 | 43 | 0 | Windows requires external `TF_VAR_admin_password` |
| Google Cloud | 39 | 40 | 0 | OS Login / Windows guest-account operations stay outside TerraForma |

This inventory was checked against compiled combined-reference projects with custom images, identity, data disks, labels and reviewed initialization enabled. The [verification record](VERIFICATION.md) records tested source checkpoints, native checks and isolated-package results. For a saved project, use `terraforma project-inputs --spec project.json` for its actual contract and `terraforma describe --spec project.json` for answers and defaults.

Broader design-inventory choices remain outside the supported catalog where disclosed. This audit does not certify every machine type. [Architecture guards](MACHINE_ARCHITECTURE.md), format checks and image declarations do not establish selected-account or guest compatibility.

## Acceptance gates

| Requirement | Available evidence | Remaining acceptance work |
|---|---|---|
| Guided Linux/Windows configurations across AWS, Azure and GCP | Shared CLI/browser contracts and import/export tests | Exercise reference configurations in dedicated accounts |
| Required inputs resolve without editing HCL | Compiled inventory above and combined terminal tests | Verify actual targets and execution credentials |
| Answers affect output; invalid/stale values are rejected | Compiler, conditional-input, literal payload and round-trip tests | Verify cloud interpretation and guest behavior |
| VM/web recipes reuse generation primitives | Shared provider builders; web recipes collect documented image, size, disk and count settings | Broader composition and standalone-only options remain catalog limitations |
| Terraform syntax/provider schemas | Recorded native validation, lint and mocked plans | Complete latest-source CI and inspect authenticated real plans |
| Account/region/size/image prerequisites | Separately consented metadata adapters with synthetic tests | Confirm real identity, availability, quotas, permissions, licensing and missing compatibility fields |
| Network ownership and guest access | Existing/new subnet guards, declared SSH/RDP/IAP paths and local plan review | Prove effective routing, policy and authenticated login |
| Workload identity | Existing-reference validation and generated attachment choices; no role grants generated | Verify attachment, effective permissions and application access |
| Initialization | Reviewed bounded input, exact payload round trips and plan warnings | Prove guest execution, effect, repeat/reboot behavior and recovery |
| State and secrets | External-secret contracts, ignored state/plans, backend-intent and privacy checks | Configure protected state; verify access, locking and recovery before live tests |
| Creation and login for all six provider/OS cases | No TerraForma live evidence yet | Record actual creation plus authenticated access |
| Cleanup and preservation | Ownership, deletion and protection declarations/review warnings | Remove owned resources, preserve existing references and inventory residual resources/state/disks |
| v0.4.0 publication | Latest release remains v0.3.0 | Satisfy live gates and exact release checks before publication |

## GCP identity source review

In the provider version inspected locally, acceptance tests use an omitted `service_account` block as a no-attached-account configuration. TerraForma's disabled setting follows that form; enabling it requests the selected user-managed account and `cloud-platform` scope. This source review does not establish live attachment or permissions.

Reference: [Google provider v7.46.1 instance tests](https://github.com/hashicorp/terraform-provider-google/blob/v7.46.1/google/services/compute/resource_compute_instance_test.go), specifically `testAccComputeInstance_serviceAccount_update0` and its no-service-account assertion. These upstream tests were inspected, not executed against a live account. VM workload identity is separate from provisioning credentials and encryption service agents.

## Next milestone

Account-free package verification is recorded in the [verification record](VERIFICATION.md#v040-account-free-package-checkpoint): the installed development wheel passes the full default suite. This closes an offline package check, not any live acceptance gate. Hosted-generator work is a separate future milestone; the immediate release target remains v0.4.0.

When dedicated AWS, Azure and GCP test accounts are available, follow the [acceptance guide](VM_ACCEPTANCE.md) with separately approved targets, spending boundaries, protected state and operations. Account creation alone does not authorize an agent to authenticate, provision or destroy resources. Record sanitized dates, source versions and outcomes without committing credentials, raw plans or state.

The optional [Terragrunt exporter](TERRAGRUNT.md) does not change these gates. Remote state, dependencies and protected automation remain later roadmap work.
