# Documentation

[Project home](../README.md) · [Roadmap](ROADMAP.md) · [Release notes](RELEASE_0.3.0.md)

## Start here

| Your goal | Guide |
| --- | --- |
| Install and export a first project without a cloud account | [Getting started](GETTING_STARTED.md) |
| Understand unfamiliar Terraform terms | [Terminology](TERMINOLOGY.md) |
| Assess data handling, access boundaries and adoption requirements | [Security overview](SECURITY_OVERVIEW.md) |
| See the app before installing | [Screenshots](../README.md#screenshots) |

## Use the released workflow

These guides describe the local generation and review workflow. Each guide identifies development-only additions where applicable.

| Task | Guide |
| --- | --- |
| Run local checks or the GitHub Action | [Validation](VALIDATION.md) |
| Reuse saved questionnaire answers | [Project specifications](PROJECT_SPECIFICATION.md) |
| Understand exported files and compare their hashes | [Generated artifacts](ARTIFACTS.md) |
| Connect cloud CLI and Terraform authentication | [Cloud authentication](CLOUD_AUTHENTICATION.md) |
| Review an existing plan JSON locally | [Plan review](PLAN_REVIEW.md) |
| Prepare non-secret state-storage references | [State protection](STATE_PROTECTION.md) |
| Understand Windows VM prerequisites | [Windows VM guide](WINDOWS_VM.md) |

## Explore v0.4.0 development

Use a separate `main` installation for these VM enhancements and examples. Offline/native evidence does not establish live deployment success; v0.4.0 remains unreleased.

| Area | Guides |
| --- | --- |
| Complete VM questions and example inputs | [VM inputs](VM_INPUTS.md) · [Six synthetic examples](../examples/vm/README.md) |
| Images, sizes and compatibility checks | [Custom images](CUSTOM_IMAGES.md) · [Machine architecture](MACHINE_ARCHITECTURE.md) · [Image metadata checks](IMAGE_PREFLIGHT.md) |
| Existing networks | [AWS subnet](AWS_EXISTING_SUBNET.md) · [Azure subnet](AZURE_EXISTING_SUBNET.md) · [GCP subnet](GCP_EXISTING_SUBNET.md) |
| Access and identity | [Google IAP](GCP_IAP_ACCESS.md) · [Azure workload identity](AZURE_WORKLOAD_IDENTITY.md) |
| Storage and protection | [Boot-disk lifecycle](BOOT_DISK_LIFECYCLE.md) · [GCP disk keys](GCP_DISK_KEYS.md) · [Azure Windows credentials](AZURE_WINDOWS_DESIGN.md) |
| Operations | [Resource labels](VM_RESOURCE_LABELS.md) · [Initialization scripts](VM_INITIALIZATION.md) · [Outbound ports](VM_OUTBOUND_ACCESS.md) · [AWS tenancy](AWS_TENANCY.md) |
| Reuse across environments | [Optional Terragrunt export](TERRAGRUNT.md) |
| Review release readiness and missing live evidence | [VM readiness](VM_RELEASE_READINESS.md) · [Live acceptance](VM_ACCEPTANCE.md) |

## Review or contribute

| Task | Guide |
| --- | --- |
| Understand components and trust boundaries | [Architecture](ARCHITECTURE.md) |
| Inspect exact test evidence and limitations | [Verification record](VERIFICATION.md) |
| Review dependencies and update rules | [Dependency trust](DEPENDENCIES.md) |
| Understand versions and planned phases | [Roadmap](ROADMAP.md) · [Changelog](../CHANGELOG.md) |
| Prepare the future hosted generator | [Hosted generator design](HOSTED_GENERATOR.md) |
| Report a vulnerability privately | [Security policy](../SECURITY.md) |
| Submit a change or report a reproducible problem | [Contributing](../CONTRIBUTING.md) |
