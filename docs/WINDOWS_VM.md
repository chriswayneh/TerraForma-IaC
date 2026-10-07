# Windows virtual machines

Development on `main` includes an initial **AWS Windows Server 2022** recipe in the local workspace and terminal wizard. Azure and Google Cloud Windows recipes remain planned. This is Terraform generation with structural verification; cloud creation, password recovery, RDP access and teardown have not been tested.

| Choice | Supported behavior |
| --- | --- |
| Image | Amazon-published Windows Server 2022 English Full Base, x86_64/HVM |
| Image version | Latest matching image at planning time, or a matching AMI ID in the selected region |
| VM size | Configurable; defaults to `t3.small`. Memory, availability, licensing and price require review |
| Boot disk | 50 GiB default, 30–2,048 GiB; gp3 or gp2 |
| gp3 performance | Same guided IOPS/throughput limits and ratio checks as the Linux recipe |
| Data disk | One optional new empty disk; initialization, formatting, backup and retention stay separate |
| Network | New configurable private IPv4 network; public/private access and optional fixed private address |
| Administrator access | RDP on TCP 3389 from a private administrator subnet or one public IPv4 /32 address |
| Credentials | Existing RSA public key only; password recovery happens separately in EC2 |
| Workload identity | Optional existing IAM instance profile; policies and pass-role permission require review |
| Protection | EC2 termination protection enabled by default; IMDSv2 required |
| Outputs | Instance ID, Name tag, availability zone, address, `Administrator` username and optional disk ID |

## Access after provisioning

Keep the RSA private key outside the project. The public key must match it and use a structurally valid OpenSSH RSA encoding with at least a 2,048-bit modulus. Ed25519 is rejected for this recipe because [EC2 Windows instances support RSA key pairs](https://docs.aws.amazon.com/AWSEC2/latest/UserGuide/create-key-pairs.html).

After a separately reviewed deployment, use the EC2 console's password recovery workflow or the [AWS CLI `get-password-data` command](https://docs.aws.amazon.com/cli/latest/reference/ec2/get-password-data.html), with the instance ID, region and matching private-key file. EC2 can take up to 15 minutes to make the initial encrypted password available. Do not copy the recovered password or private key into a TerraForma manifest, browser form, AI diagnostics or Git repository.

TerraForma does not retrieve or decrypt password data, generate a private key, or place either credential in its generated Terraform inputs or outputs. Terraform state still contains infrastructure information and requires protected storage. The initial password is not a password rotation or recovery policy.

Private VMs require an existing routed access path such as a VPN or bastion; this recipe creates neither. A public address alone does not satisfy the restricted administrator rule. Application installation, domain joining, custom images, Windows patching, certificate configuration, backup and automatic disk initialization remain outside this recipe.

The image query retains the Amazon owner, Windows Server 2022 name, x86_64 and HVM filters even when an AMI ID is pinned. Image pins do not install security updates and image changes can replace the VM. The selected base image does not add a configurable Secure Boot or TPM guarantee. Verify account policy, image availability, guest compatibility and costs before planning.

AWS publishes [Windows AMI version history](https://docs.aws.amazon.com/ec2/latest/windows-ami-reference/ec2-windows-ami-version-history.html), including the 30 GiB root volume used by Core and Full Base images. A larger disk does not replace guest filesystem verification or backups.
