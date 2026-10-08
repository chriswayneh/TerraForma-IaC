# VM input contract design

This is the required design inventory for the expanded VM wizard in roadmap v0.4. It is not a statement that the released templates implement every setting. The goal is a provisioning workflow that requires infrastructure knowledge, not Terraform syntax. Current development coverage is tracked in the [roadmap](ROADMAP.md), including guided [AWS](AWS_EXISTING_SUBNET.md), [Azure](AZURE_EXISTING_SUBNET.md) and [Google Cloud](GCP_EXISTING_SUBNET.md) existing-subnet inputs.

Each resource adapter must declare questions, types, defaults, validation, visibility conditions, whether the value is a secret/reference, and how it maps to Terraform. The UI and CLI consume that contract. Required-variable completeness is checked after generation; the list must not be maintained independently from the adapter. Choices that require live account data are checked during preflight, with offline verification status shown clearly.

## Shared decisions

| Group | Inputs and conditional questions |
| --- | --- |
| Scope | Provider, account/subscription/project, environment, project/resource names, region, zone, ownership, tags/labels, intended cost constraints. |
| OS and image | Linux/Windows, supported distribution/version, architecture, standard image/custom image reference, image owner/trust, marketplace terms/license prerequisites, Windows licensing choice. |
| Capacity | VM SKU/machine type, CPU/memory/GPU requirements, count, reserved/spot/on-demand mode where supported, interruption behavior, placement/availability requirements, scaling choice. |
| Boot disk | Image-derived defaults, size, disk class, encryption, provider-managed/customer-managed key reference, key permissions, deletion on termination, disk protection. |
| Data disks | Number, sizes, types, attach mode, mount/drive intent, IOPS/throughput when configurable, encryption/key references, persistence and backup expectations. |
| Network | New/existing VPC/VNet and subnet IDs, address spaces/CIDRs, availability zones, private IP allocation, additional NICs, public IP choice, routing, NAT/egress, DNS, IPv6 when supported. |
| Access | SSH/RDP/remote-management method, administrator username, public key or external secret reference, identity-based login, approved source ranges, VPN/bastion/IAP/Session Manager prerequisites. |
| Workload rules | Required inbound ports and protocols, source groups/tags/CIDRs, outbound restrictions, HTTP/HTTPS/domain/certificate questions when exposing a web service. |
| Identity | Existing/create role/service account/managed identity, required permissions, scope, permissions boundaries, instance metadata restrictions. No broad permissions as hidden defaults. |
| Startup | Optional trusted initialization file, supported cloud-init/user-data mechanism, extensions/agents, secret retrieval at runtime. Warn about sensitive values retained in state or metadata. |
| Operations | Backups/retention, monitoring/logging destination, patch management, boot diagnostics, availability, shutdown policy, deletion protection, maintenance and recovery intent. |
| State/lifecycle | Backend/environment identity, state locking, existing-resource references versus new resources, replacement/deletion impact, import workflow where explicitly supported. |

Simple mode presents only necessary questions and explains defaults; advanced mode exposes supported additional settings. It must never silently ignore an answer. An incompatible choice is rejected with a reason and valid alternatives. Administrator passwords are not retained in browser storage or ordinary project manifests.

## Provider-specific contracts

### AWS EC2

Account identity and role/profile are verified through the existing credential chain. Questions include region/AZ, AMI ID or reviewed image selector, AMI owner and CPU architecture, instance type, subnet, security groups, public/private IP, key-pair strategy, EBS volume settings, KMS reference, instance profile, IMDSv2 policy, monitoring, tenancy/placement, spot behavior, and termination protection. Image/SKU/architecture compatibility and account quotas require provider preflight. Access via Session Manager also needs its agent, instance permissions, and egress or private endpoints.

### Azure Virtual Machines

Questions include subscription/tenant context, resource group create/use, location/zone, VM size, marketplace image tuple or gallery/custom-image reference, applicable image plan/license settings, OS/admin authentication, VNet/subnet/NIC/public-IP/NSG choices, managed OS/data disk settings, encryption/key references, managed identities, boot diagnostics, availability set/zone, Trusted Launch/Secure Boot/vTPM where compatible, extensions, and accelerated networking support. Windows secret requirements and region/SKU/feature compatibility must be checked without collecting a persistent password in the browser.

### Google Compute Engine

Questions include project, region/zone, enabled-service prerequisites, machine family/type or supported custom sizing, image family/project or image reference, service account and IAM requirements, VPC/subnetwork, private/public addressing, tags/firewall rules, boot/data disks, encryption/key references, OS Login/IAP prerequisites, shielded-VM options where compatible, spot/provisioning model, scheduling/maintenance behavior, startup metadata, and deletion protection. Image, disk, zone, GPU, and machine-family compatibility require account/provider checks.

## Required tests before release

- Every declared question maps to a real generated value or explicit external reference; unsupported settings produce an error rather than being dropped.
- Every generated required variable is resolved or visibly deferred to an external secret mechanism; defaulted variables are documented.
- Conditional inputs appear when applicable and stale values from earlier choices are rejected or explicitly cleared.
- Secrets never enter saved browser preferences, manifests, source control, or ordinary logs.
- Both Linux and Windows reference configurations have real deployment/access/cleanup evidence for each supported provider.
- Free reused modules are pinned, licensed, and adapted through the same input contract. Their required variables, provider constraints, and execution hooks are reviewed before use.

See the [roadmap](ROADMAP.md) for sequence and release gates.
