# State and recovery design

This is the design boundary for future managed provisioning. TerraForma currently generates configuration, validates trusted copies and reviews existing plan exports. It does not configure a remote backend, migrate state, acquire a deployment lock or run apply/destroy. A generated project is not a protected deployment workspace.

## Keep operational artifacts private

Terraform state and saved plans can contain credentials and resource secrets. Marking a variable `sensitive` hides ordinary console output but does not remove its value from state or plans. Ephemeral values and write-only arguments require compatible Terraform/provider features and permitted contexts; they cannot be assumed for every recipe. See [Terraform sensitive data handling](https://developer.hashicorp.com/terraform/language/manage-sensitive-data).

The current Azure Windows password reference avoids storing a password in questionnaire answers. It does not prevent the provider from retaining a supplied password in Terraform artifacts. Keep state, backups, binary plans, JSON exports and crash logs outside public Git, screenshots and AI requests. Removing a value from configuration does not remove it from older state versions, plans or backups.

Generated ignore rules and file permissions reduce accidental exposure; they do not encrypt files, remove tracked content, cover arbitrary filenames or audit Windows ACLs. Follow the [artifact handling guide](ARTIFACTS.md) for current behavior. Use a private workspace and separately reviewed storage access before running Terraform yourself.

## Planned backend choices

Users should select an existing, separately administered backend and enter its non-secret location. Backend credentials must come from supported external authentication, with backend and provider identities verified separately. TerraForma must not silently create storage or grant permissions while initializing a workload.

| Provider | Planned backend | Non-secret location inputs | Locking and recovery requirements |
| --- | --- | --- | --- |
| AWS | S3 | State account, bucket, region, object key and environment | Explicit S3 lockfile support, restricted state/lock access, reviewed encryption and bucket versioning |
| Azure | Azure Blob Storage | Tenant/subscription, storage account, container and blob key | Native backend locking, restricted data-plane access, reviewed encryption and version/retention recovery |
| GCP | Cloud Storage | State project, bucket and prefix | Native backend locking, restricted object access, reviewed encryption and object versioning |

The [S3 backend](https://developer.hashicorp.com/terraform/language/backend/s3) requires opting into `use_lockfile`; DynamoDB locking is deprecated. Lock object permissions need separate review. The [Azure backend](https://developer.hashicorp.com/terraform/language/backend/azurerm) supports native locking and warns that hardcoded or backend-config credentials can enter cached backend metadata and plans. The [GCS backend](https://developer.hashicorp.com/terraform/language/backend/gcs) supports locking and recommends object versioning for recovery. Compatibility must be verified against the selected Terraform version before any backend is advertised as supported.

## Required decisions before deployment

| Decision | Required evidence |
| --- | --- |
| State owner | Named team/operator responsible for access, retention, migration and recovery |
| Environment boundary | Explicit account/project/subscription and unique state location for each environment; no accidental shared state |
| Authentication | Verified backend identity and workload identity; no browser credential collection or persisted tokens |
| Storage protection | Reviewed encryption, private access, least-privilege reads/writes and separate key ownership when applicable |
| Concurrent operations | Backend locking verified with contention tests; bounded waits and no automatic force-unlock |
| Recovery | Version/backup retention plus a tested restore procedure and key-access continuity |
| Plan integrity | Trusted configuration/dependency versions, target identity and state context bound to the exact saved plan |
| Approval | Explicit reviewed artifact and intended operation; local review exit zero cannot authorize apply |

These are acceptance requirements, not checks implemented by the current interface. Questionnaire references and receipt hashes do not establish effective permissions, authenticated provenance or state ownership.

## Migration and failure handling

Existing local or remote state must be detected before selecting a new backend. Migration requires a separate reviewed operation, protected backups, confirmed source/destination identity and recovery evidence. Never initialize a different state location as an automatic retry or use an empty state to bypass a failure.

After interruption, lock contention or an uncertain apply outcome, preserve private artifacts and establish the actual state before retrying. Cancellation is not rollback. Force-unlock, state deletion, state editing, restore and backend migration require their own explicit workflow; they are outside today's product capabilities.

State recovery and disk recovery are different responsibilities. Restoring a state version does not restore deleted VM data or destroyed encryption keys. Review [boot disk lifecycle](BOOT_DISK_LIFECYCLE.md) and [GCP disk key ownership](GCP_DISK_KEYS.md) alongside backend retention.

The [roadmap](ROADMAP.md#phase-4) schedules backend integration, saved-plan integrity and recovery testing before approved provisioning. This design does not change that sequence or authorize cloud operations.
