# Static scanner results for generated recipes

[Project home](../README.md) · [Documentation](README.md) · [Security overview](SECURITY_OVERVIEW.md)

Generated recipes are starter configurations. They pass `terraform validate`, TFLint and `terraform fmt -check`, but a general-purpose policy scanner such as [Checkov](https://www.checkov.io/) still reports hardening checks that the recipes intentionally leave to the adopting team. This page lists those checks so a reviewer can tell deliberate scope from an oversight.

Source: Checkov 3.3.26 run with `--framework terraform` against all 36 default projects (3 clouds × 6 recipes × public/private, encryption on) generated from `main` on 2026-10-09. Results depend on the Checkov version and on the inputs you choose.

## Not configured by design

| Area | Example checks | Why the recipe leaves it out |
| --- | --- | --- |
| Network flow logs and default security groups | `CKV2_AWS_11`, `CKV_GCP_26`, `CKV2_AWS_12`, `CKV2_GCP_18` | Flow-log destinations, retention and cost are organization decisions. The recipes do not attach workloads to the default VPC security group or default GCP firewall. |
| Public subnets assign public IPs | `CKV_AWS_130`, `CKV_AWS_88`, `CKV_GCP_40`, `CKV_AZURE_119` | Public subnets exist for load balancers, NAT and the explicit public recipes. Private recipes place compute in private subnets. |
| Instance monitoring, EBS optimization, instance profiles | `CKV_AWS_126`, `CKV_AWS_135`, `CKV2_AWS_41` | Detailed monitoring is an input on standalone VMs; current instance families are EBS-optimized by default; no IAM role is created unless the workload needs one. |
| Security-group descriptions and unrestricted egress | `CKV_AWS_23`, `CKV_AWS_382` | Rules are small and generated from reviewed inputs. Standalone VMs offer an HTTPS/DNS-only outbound profile. |
| Availability-zone pinning | `CKV_AWS_394` | Zones come from the `aws_availability_zones` data source; standalone VMs filter to opt-in-not-required zones and accept an explicit zone. |
| Project-wide SSH keys, Shielded VM on web tiers | `CKV_GCP_32`, `CKV_GCP_39` | Reported on the GCP web tiers and Windows VM. Linux standalone VMs enable OS Login, and Shielded VM settings are exposed on standalone VMs only. If your project uses project-wide SSH keys, add `block-project-ssh-keys = "TRUE"` metadata. |
| VM extensions | `CKV_AZURE_50` | Azure VMs keep the provider default that allows extension operations, so the VM agent can run Azure-managed extensions and, on Windows, reviewed initialization through the Custom Script Extension. |
| Database logging, audit flags, monitoring and IAM auth | `CKV_AWS_129`, `CKV_AWS_118`, `CKV_AWS_353`, `CKV_AWS_161`, `CKV_AWS_226`, `CKV2_AWS_30`, `CKV2_AWS_60`, `CKV_GCP_51`–`CKV_GCP_54`, `CKV_GCP_108`–`CKV_GCP_111`, `CKV2_GCP_13` | Log volume, retention and audit policy vary by organization. Storage encryption, standby/HA, backups and deletion protection are configured, and placement is private by default. |
| Database private endpoints and geo-redundant backups | `CKV2_AZURE_57`, `CKV_AZURE_136` | Private networking for Azure Flexible Server and cross-region backups add cost and network design that a starter recipe cannot assume. |
| Load balancer TLS, WAF, access logs and deletion protection | `CKV_AWS_2`, `CKV_AWS_103`, `CKV_AWS_378`, `CKV2_AWS_20`, `CKV2_AWS_28`, `CKV_AWS_91`, `CKV_AWS_150`, `CKV_AWS_131` | The web recipes serve HTTP. Add a certificate, HTTPS listener and WAF before sensitive use, as the README states. |
| Object-storage logging, replication, lifecycle and notifications | `CKV_AWS_18`, `CKV_AWS_144`, `CKV2_AWS_61`, `CKV2_AWS_62`, `CKV_GCP_62`, `CKV_AZURE_206`, `CKV_AZURE_33`, `CKV2_AZURE_21` | Static-site storage uses provider-managed encryption with object versioning (AWS, GCP) or soft delete (Azure); logging targets and replication are left to the adopter. |
| Customer-managed keys for object storage | `CKV_AWS_145`, `CKV2_AZURE_1`, `CKV_GCP_38` | Static sites use provider-managed encryption. AWS compute and databases use a generated KMS key when the encryption option is on. |
| Public static-site access | `CKV_AWS_54`, `CKV_AWS_56`, `CKV_AWS_70`, `CKV2_AWS_6`, `CKV_GCP_28`, `CKV_GCP_114`, `CKV_AZURE_190`, `CKV2_AZURE_47`, `CKV_AWS_260`, `CKV_GCP_106` | Reported only for the explicit **public** recipes, which serve content to anonymous visitors by design. |

## Azure static-site storage account

The storage account sets HTTPS-only traffic, TLS 1.2, no anonymous blob access in private mode, no cross-tenant replication, no local users or SFTP, and 7-day blob and container soft delete.

Checkov still reports `CKV_AZURE_59` (public network access), `CKV2_AZURE_40` (shared-key authorization), `CKV2_AZURE_33` (private endpoint) and `CKV2_AZURE_41` (SAS expiration policy). These remain at provider defaults because Terraform uploads `index.html` through the blob data plane:

- Turning off public network access blocks that upload unless Terraform runs from a network with a private endpoint or an allowed network rule.
- Turning off shared-key authorization requires `storage_use_azuread = true` in the provider block and a data-plane role (such as Storage Blob Data Contributor) for the identity running Terraform, which the recipe does not grant.

Private mode therefore means "no anonymous access", not "unreachable from the internet". Add these controls when your deployment identity and network path support them.

## Possible false positives

- `CKV_GCP_6` (Cloud SQL SSL): the recipe sets `ssl_mode = "ENCRYPTED_ONLY"`; some Checkov versions only look at the older `require_ssl` argument.
- `CKV_GCP_79` (latest PostgreSQL major version): all three clouds pin PostgreSQL 16 for consistent, reproducible plans.
- `CKV2_AWS_5`, `CKV2_AWS_19`, `CKV2_AZURE_31`: the security group, NAT Elastic IP and subnet are attached (to the VM, NAT gateway and NSG association respectively), but through `count` or separate association resources that Checkov's graph does not always resolve.
