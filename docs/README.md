# Documentation

Start with the released guided workflow, then use the technical guides when you need more detail.

| I want to… | Read |
| --- | --- |
| Install and create my first configuration | [Getting started](GETTING_STARTED.md) |
| Connect existing cloud CLI and Terraform authentication | [Cloud authentication](CLOUD_AUTHENTICATION.md) |
| Generate a GCP VM with an administrator tunnel on main | [Google IAP access](GCP_IAP_ACCESS.md) |
| Review standalone VM boot-disk deletion and retention | [Boot disk lifecycle](BOOT_DISK_LIFECYCLE.md) |
| Reference an existing GCP disk encryption key on main | [Google Cloud disk keys](GCP_DISK_KEYS.md) |
| See the interface before installing | [Screenshots](../README.md#screenshots) |
| Understand what the release includes | [v0.3.0 release notes](RELEASE_0.3.0.md) and [changelog](../CHANGELOG.md) |
| See current progress and planned versions | [Roadmap](ROADMAP.md) |
| Understand how the components work together | [Architecture](ARCHITECTURE.md) |
| Review build dependencies and update rules | [Dependency trust](DEPENDENCIES.md) |
| Check validation and platform evidence | [Verification record](VERIFICATION.md) |
| Review a Terraform plan locally | [Plan review](PLAN_REVIEW.md) |
| Reuse a recipe's input answers on main | [Project specifications](PROJECT_SPECIFICATION.md) |
| Compare exported files to a generation receipt | [Generated artifacts](ARTIFACTS.md) |
| Understand future state storage and recovery requirements | [State protection design](STATE_PROTECTION.md) |
| Understand the future VM questions | [VM input design](VM_INPUTS.md) |
| Include a reviewed local script on development VMs | [VM initialization](VM_INITIALIZATION.md) |
| Choose outbound ports for a new standalone VM network | [VM outbound profiles](VM_OUTBOUND_ACCESS.md) |
| Prepare future dedicated-account VM release testing | [VM acceptance evidence](VM_ACCEPTANCE.md) |
| Review optional development image metadata checks | [Operating system image preflight](IMAGE_PREFLIGHT.md) |
| Review security boundaries or report a vulnerability | [Security policy](../SECURITY.md) |
| Contribute a change | [Contribution guide](../CONTRIBUTING.md) |

The current v0.3.0 release generates, reuses and validates supported recipes. Complete VM acceptance and product-managed provisioning remain later milestones.
