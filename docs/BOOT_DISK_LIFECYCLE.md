# Boot disk lifecycle

GCP standalone disks can optionally reference an [existing Cloud KMS key](GCP_DISK_KEYS.md). Disk retention does not preserve key state or access; key recovery and permissions remain separate responsibilities.

Development standalone AWS and GCP Linux/Windows recipes expose **Delete boot disk when VM is deleted**. This controls the VM's boot-disk deletion setting. Azure and web-tier recipes do not offer this option.

| Choice | Generated behavior | Review before use |
| --- | --- | --- |
| Enabled, the existing default | AWS `root_block_device.delete_on_termination = true`; GCP `boot_disk.auto_delete = true` | Deletion or replacement can permanently remove boot data. Arrange backups and recovery separately. |
| Disabled | Requests preservation of the old boot disk when the VM is deleted | Storage charges continue. Recovery, reattachment, encryption-key preservation and cleanup remain separate. A replacement VM does not automatically reuse this disk. |

The provider contracts document these defaults: [AWS instance root disks](https://github.com/hashicorp/terraform-provider-aws/blob/v6.0.0/website/docs/r/instance.html.markdown) and [Google instance boot disks](https://github.com/hashicorp/terraform-provider-google/blob/v7.0.0/website/docs/r/compute_instance.html.markdown). Generation sets the value explicitly for standalone VMs and preserves the earlier default. Imported projects retain any explicit answer.

Retention is limited to the boot disk. Separately managed data disks, VM identities, networks and encryption keys remain under their own Terraform lifecycle. Review every destructive change in the plan. Turning off this option does not block Terraform destroy, provide a backup, reserve a replacement disk name or prove that the filesystem is recoverable. VM deletion protection is a separate setting and may prevent the VM deletion altogether.

AWS encrypted boot disks use a project-managed KMS key. A full teardown can schedule that key for deletion while retaining the disk. A key pending deletion cannot perform cryptographic operations, and permanent deletion makes its encrypted data unrecoverable; see [AWS KMS key deletion](https://docs.aws.amazon.com/kms/latest/developerguide/deleting-keys.html). Arrange preservation of the key and its access policy separately before teardown. Boot-disk retention alone is insufficient for recovery of encrypted data.

On GCP, retaining an automatically initialized boot disk can leave a disk name that conflicts with replacement creation. Review the retained disk, intended names and recovery procedure before replacing the VM. This recipe does not adopt an existing boot disk or attach one as the replacement's boot source.

Record disk identifiers and encryption-key references in your protected operational records before deletion or replacement. Verify backups and recovery through a separate approved workflow. The local plan reviewer blocks destructive changes but has partial coverage; it does not certify boot-disk or key retention. Terraform validation and TFLint cover generated configuration only. Actual disk retention, key preservation, restoration and live teardown remain unverified.
