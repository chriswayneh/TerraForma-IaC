# VM acceptance evidence

Status: live acceptance is pending for v0.4.0. Offline checks cannot establish creation, login, guest initialization or cleanup. No cloud test accounts are configured for this work.

## Release gates

| Provider | Linux creation and login | Windows creation and login | Initialization and lifecycle | Cleanup |
| --- | --- | --- | --- | --- |
| AWS | Pending dedicated-account evidence | Pending dedicated-account evidence | Pending | Pending |
| Azure | Pending dedicated-account evidence | Pending dedicated-account evidence | Pending | Pending |
| GCP | Pending dedicated-account evidence | Pending dedicated-account evidence | Pending | Pending |

Record each tested OS/image and input combination separately. Six default VM cases alone do not establish every optional feature or image variant. The supported catalog and [roadmap coverage](ROADMAP.md#phase-2) define the scope; unsupported choices do not become supported through a successful unrelated test.

## Before any live test

Use a dedicated account/subscription/project, independent authenticated cloud tooling and an approved spending boundary. Confirm region, size, image availability, licensing, quotas and permissions for that target. Existing subnet, image, identity and key references require their own ownership and effective-access review.

Prepare protected state storage and a recovery plan before handling a real plan or provisioning. Azure Windows credentials must use the external environment reference and can be retained by the provider in state/plans. AWS Windows password recovery and GCP Windows account setup remain separate authenticated operations. Keep private keys, passwords, raw plans and state out of this repository.

Review the generated receipt and exact files, provider lock, Terraform plan, destructive actions, cost drivers and policy gaps. A local report never approves deployment. Live creation, login, state access and cleanup require separate authorization; this guide does not authorize the agent to perform them.

## Evidence to collect

| Stage | Record privately | Public verification summary |
| --- | --- | --- |
| Configuration | Source commit, package version, generated receipt, provider lock, selected non-secret inputs, exact target and credential-chain identity | Tested commit/version, provider, OS/image family and input variant; omit credentials and target identifiers |
| Preflight and plan | Region/size/image availability, quota/permission checks, approved state protection, exact plan digest and reviewed changes | Which prerequisites were verified and which gaps remain |
| Creation | Resources created, service/API outcomes and guest boot status | Creation result with actual test date |
| Access | Successful authenticated SSH/RDP or documented IAP path; verify the actual guest OS and intended identity | Login method and result without addresses, passwords or tokens |
| Initialization | Guest-agent logs, script exit status, expected observable effect, repeat/reboot behavior and recovery effects | Whether the reviewed script ran and its effect was verified; never publish raw script logs that contain sensitive data |
| Feature variants | Existing/new network ownership, custom image compatibility, identity access, disks/encryption, placement, boot protection and operational choices actually exercised | Exact features tested; distinguish schema checks from live behavior |
| Cleanup | Protection changes deliberately reviewed, removal of owned test resources, independently preserved existing resources, retained-disk/state recovery and residual-resource inventory | Cleanup result and any remaining resources or unverified obligations |

Test data-disk attachment separately from formatting, mounting and backups. Test boot-disk retention and recovery separately from ordinary VM deletion. Deletion protection can block cleanup or replacement and must be handled through the reviewed workflow. Existing network mode must preserve independently managed network resources; switching ownership modes in deployed state requires its own destructive review.

An initialization payload can execute elevated guest commands and make network requests. Use a reviewed non-secret script with explicit failure handling and repeat-safe operations. A successful exit code or VM readiness alone does not prove application health. Disabling initialization does not reverse guest changes or establish removal of existing AWS user data.

## Current offline evidence

AWS [tenancy](AWS_TENANCY.md) needs separate evidence for supported size/region, effective placement, licensing, costs, changes and cleanup. Neither an image/size metadata check nor a mocked plan verifies dedicated capacity.

For the restricted [outbound profile](VM_OUTBOUND_ACCESS.md), test effective HTTPS/DNS access, rejection of another outbound port, required platform/Windows activation traffic, guest updates and initialization dependencies. Confirm private application connectivity and inherited policy effects separately. Local rule declarations cannot establish these outcomes.

The [verification record](VERIFICATION.md) contains structural validation, lint, input round trips, literal payload checks, provider-mocked plans and report-privacy evidence. The combined-input matrix exercises custom images, identity, data disks, labels and initialization across 24 provider/OS/access/network configurations. All mocked runs use plan only; no guest or cloud resource is created.

When dedicated accounts and separately authorized testing are available, append sanitized outcomes to the verification record with tested commit, date and scope. Preserve failures and incomplete checks. Release v0.4.0 only after its documented gates have evidence; v0.3.0 remains the latest release meanwhile.
