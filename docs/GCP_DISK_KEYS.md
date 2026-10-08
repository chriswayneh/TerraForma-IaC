# Existing Google Cloud disk encryption keys

Development standalone Linux and Windows recipes can reference one existing Cloud KMS CryptoKey for the VM's boot disk and optional data disk. Google-managed encryption remains the default. This is generation with structural verification; key access and live disk creation remain unverified.

| Input | Purpose |
| --- | --- |
| Use an existing disk encryption key | Enable the existing-key reference for both managed disks |
| Existing Cloud KMS key resource name | Enter `projects/KEY_PROJECT/locations/LOCATION/keyRings/RING/cryptoKeys/KEY` |
| Optional data disk | Uses the same key when enabled; it remains a new empty disk |

Enter a resource reference, never raw encryption material, a private key, access token or credential. The input accepts CryptoKey names, including a key project different from the VM project. URLs, exact CryptoKeyVersion references and custom KMS service-account overrides are outside this initial scope. Generation checks the reference shape; it does not query the key or prove access.

Prepare the key and permissions separately using Google's [Compute Engine CMEK guidance](https://docs.cloud.google.com/compute/docs/disks/customer-managed-encryption). The Compute Engine service agent for the VM project needs appropriate key encryption/decryption access; this is separate from the guest workload service account. Regional disks can use a key in the same region, a compatible geographic multi-region or the global location. TerraForma does not establish that a selected key location is compatible, enable key-project APIs, create keys or grant IAM access.

Changing encryption can replace the VM or disks and delete data. Review backups, application recovery and the saved Terraform plan before changing an existing project. This recipe does not re-encrypt an existing disk in place, configure source-image decryption, rotate keys, migrate snapshots or configure automatic VM shutdown on key revocation.

Retaining a disk does not preserve its key. Revoked key access can prevent booting, attaching disks and recovering snapshots. Destroying key material can make recovery irreversible. Keep key ownership, enabled versions, IAM access and retention under a separately reviewed recovery process. This project references the key without managing its lifecycle.

Local plan review flags declared Cloud KMS references for access and recovery review, blocks changes to an existing reference and blocks inline customer-supplied key material. It checks VM boot disks and standalone persistent disks; source-image/snapshot decryption and other disk attachment shapes remain outside these rules. Plan review remains partial: it does not verify KMS access, key state, effective encryption or recoverability. A local validation or review result never approves deployment.
