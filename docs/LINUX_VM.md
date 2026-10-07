# Linux virtual machines

Available on `main` during development. The v0.2.0 release does not include the standalone VM recipe. Cloud creation, login, and teardown remain unverified.

Choose **A Linux virtual machine** in the browser or terminal wizard. This generates one VM in a new cloud network, with a selected supported Linux image, VM size, boot disk, and restricted SSH access. Application startup is left for your workload setup. Every configurable field is collected through the shared input contract.

![Standalone Linux VM configuration and outputs](images/linux-vm.png)

## Questions and defaults

| Decision | What you provide | What stays fixed |
| --- | --- | --- |
| Target | AWS account ID, Azure subscription UUID, or Google Cloud project ID; environment label | Credentials use the cloud provider's normal credential chain; identity remains unverified offline |
| Placement | Region/location, plus zone for GCP; new private network address range | Subnet layout is derived by the recipe; existing-network attachment is not supported |
| Operating system | Supported provider-specific Linux choice | x86_64/AMD64 only; latest matching publisher image at planning time |
| Capacity and storage | VM size, boot-disk size/type, supported encryption choice | One VM; no autoscaling, custom images, or custom initialization |
| Data storage | Enable one data disk, size from 32–2048 GiB, supported disk class | Disabled by default; one new empty disk, no formatting/mounting, backup, or recovery policy |
| Monitoring | AWS: enable or disable detailed EC2 monitoring; disabled by default | No monitoring agent, log collection, or alarms; Azure/GCP monitoring options remain planned |
| Deletion protection | AWS/GCP: protect the standalone VM from specified deletion paths; enabled by default | No backup, whole-project protection, or Azure VM deletion lock is configured |
| Network access | Public/private address choice and administrator CIDR | SSH port 22; no web ingress; private access needs an existing routed path |
| Authentication | AWS/Azure: an existing Ed25519 or RSA public key; Azure: administrator username (default `terraforma`); GCP: OS Login IAM prerequisites | No private key is generated or collected; password authentication stays disabled |

Public mode requires an explicit single IPv4 `/32` client address or RFC1918 private subnet. Private mode defaults to `10.0.0.0/16`; review it against your actual routed client network. Broader public administrator ranges, including `0.0.0.0/0`, are rejected in both forms and generated Terraform. Firewall permission alone does not provide routing or prove successful login.

## Provider access

AWS/GCP standalone VMs ask **Protect this VM from accidental deletion**. AWS maps this to EC2 API termination protection; GCP maps it to VM deletion protection. Before intentionally deleting or replacing a protected VM, disable this choice and apply that configuration change through your Terraform workflow. Protection does not cover every deletion path, connected resource, or data-loss scenario. See [AWS termination protection](https://docs.aws.amazon.com/AWSEC2/latest/UserGuide/Using_ChangingDisableAPITermination.html) and [GCP provider deletion-protection requirements](https://registry.terraform.io/providers/hashicorp/google/latest/docs/resources/compute_instance).

For AWS VMs and web tiers, **Enable detailed EC2 monitoring** changes most EC2 metrics from five-minute to one-minute periods. Status checks already use one-minute periods. Detailed monitoring can add CloudWatch charges for each instance, including every VM in a tier; it does not provide guest memory metrics, application logs, or alarms. Review [AWS monitoring behavior](https://docs.aws.amazon.com/AWSEC2/latest/UserGuide/manage-detailed-monitoring.html) and [CloudWatch pricing](https://aws.amazon.com/cloudwatch/pricing/) before enabling it.

| Provider | Generated authentication | Outputs and prerequisites |
| --- | --- | --- |
| AWS | Imports the supplied public key as an EC2 key pair; attaches it to the VM; requires IMDSv2 | `vm_address` and `ssh_username`: `ec2-user` for Amazon Linux, `ubuntu` for Ubuntu. Keep the matching private key locally and verify the image's actual access behavior. |
| Azure | Public-key login for the selected administrator username (default `terraforma`), with password authentication disabled; SSH allow rule followed by a deny rule for other inbound traffic | `vm_address` and `ssh_username`. Subscription/SKU support for optional host encryption still needs review. |
| GCP | Enables OS Login and blocks project metadata SSH keys; no instance SSH public key is collected | `vm_address`. Establish the required OS Login IAM access and organization-policy prerequisites before connecting. This recipe does not create IAM role assignments. |

Private VMs need connectivity into the generated network, such as a reviewed VPN, peering, or bastion route. Those resources are not created here. Compute, disks, outbound NAT, and public addresses can incur charges. Public/private selection controls addressing, not an assurance of end-to-end reachability.

The generated output has no application startup script or HTTP endpoint. Review the exported project guide, [supported image choices](PROJECT_SPECIFICATION.md#linux-image-selection), artifact receipt, cloud policy, and a Terraform plan before provisioning through your own workflow. TerraForma currently generates and validates; it does not execute apply or destroy.

Reference behavior: [EC2 key pairs](https://docs.aws.amazon.com/AWSEC2/latest/UserGuide/ec2-key-pairs.html), [Google SSH connections](https://docs.cloud.google.com/compute/docs/instances/ssh), and [project SSH-key restrictions](https://docs.cloud.google.com/compute/docs/connect/restrict-ssh-keys?hl=en).

## Optional data disk

Choose **Attach a data disk** to reveal size and storage-class questions. These questions are hidden when the option is off; inactive disk settings are omitted from browser exports and the configuration summary. The CLI asks size/type only when enabled. Existing manifests without these inputs continue with no data disk.

![Choosing an optional data disk and its storage class](images/linux-vm-data-disk.png)

| Provider | Supported classes | Attachment and encryption |
| --- | --- | --- |
| AWS | `gp3` (default), `gp2` | One encrypted EBS volume in the VM's availability zone; uses the recipe KMS key when enabled, otherwise the account's default EBS encryption key. Requests `/dev/sdf`; Nitro Linux device names may differ. Forced detach is disabled, and attachment changes may stop the VM before detaching. |
| Azure | `StandardSSD_LRS` (default), `Standard_LRS`, `Premium_LRS` | One empty managed disk at LUN 0, with caching set to None. Azure storage encryption applies; the VM's optional host encryption still requires subscription support. |
| GCP | `pd-balanced` (default), `pd-standard`, `pd-ssd` | One zonal persistent disk attached as `data-disk`, with provider-managed encryption. No customer-managed disk key is configured. |

The `data_disk_id` output identifies the disk when enabled. Attachment alone does not provide a mounted filesystem: identify the actual device, then arrange filesystem setup, mounting, backups, and recovery through your reviewed workload workflow. The tool performs none of those guest operations. Disk class and size compatibility, quotas, permissions, and costs require account preflight.

This disk is managed by the exported Terraform project. Teardown can delete it, and VM deletion protection does not protect every disk or connected resource. Review data preservation before detaching, replacing, disabling, or removing it. Multiple disks, existing volumes/snapshots, custom IOPS/throughput, disk shrinking, and web-tier data disks remain unsupported.

Provider references: [EBS volumes](https://registry.terraform.io/providers/hashicorp/aws/latest/docs/resources/ebs_volume), [Azure disk attachments](https://registry.terraform.io/providers/hashicorp/azurerm/latest/docs/resources/virtual_machine_data_disk_attachment), and [GCP persistent disks](https://registry.terraform.io/providers/hashicorp/google/latest/docs/resources/compute_disk).

## New network address range

Choose a private IPv4 range that does not overlap networks you intend to connect. TerraForma checks the input format and recipe bounds; it does not inspect existing networks or account connectivity. Only canonical RFC1918 ranges (`10/8`, `172.16/12`, `192.168/16`) are supported here. Host bits, IPv6, public ranges and carrier-grade NAT ranges are rejected.

![Configuring the new private network range](images/linux-vm-network.png)

| Provider | Recipe range | Generated subnets |
| --- | --- | --- |
| AWS | `/16` through `/20`, default `10.0.0.0/16` | Two public and two private subnets in two available zones. Eight prefix bits are added; subnet indices are 0, 1, 10 and 11. A `/16` yields `/24` subnets; a `/20` yields `/28` subnets. |
| Azure | `/16` through `/20`, default `10.0.0.0/16` | One workload subnet adds eight prefix bits at index 1. The default yields `10.0.1.0/24`. |
| GCP | `/16` through `/28`, default `10.0.1.0/24` | One regional subnet uses the selected range directly. The VPC itself has no enclosing CIDR. |

These are recipe bounds rather than the providers' complete capabilities. Individual subnet sizing, additional ranges, IPv6 and attachment to existing networks remain planned. Changing an exported project's range can replace network and dependent resources; review the Terraform plan and access/data preservation before applying changes. The administrator CIDR remains a separate access decision and is not automatically changed to match this range.

Provider references: [AWS VPC address ranges](https://docs.aws.amazon.com/vpc/latest/userguide/vpc-cidr-blocks.html), [Azure networking FAQ](https://learn.microsoft.com/en-us/azure/virtual-network/virtual-networks-faq), and [GCP subnets](https://docs.cloud.google.com/vpc/docs/subnets).
