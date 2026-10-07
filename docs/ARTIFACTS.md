# Generated project artifacts

Available on `main` during v0.3 development. The v0.2.0 release does not include generation receipts or the comparison command.

Both terminal generation and browser exports preserve the non-secret questionnaire alongside its Terraform output.

| File | Purpose |
| --- | --- |
| `main.tf`, `variables.tf`, `outputs.tf` | Generated Terraform configuration |
| `terraforma.project.json` | Recipe and non-secret answers for reuse |
| `terraforma.receipt.json` | Generator/template versions, canonical specification digest, and hashes of the four files above |
| `SHA256SUMS.txt` | Hashes of exported files, including the receipt; excludes itself |
| `README.md` | Browser ZIP guide with required inputs, target context, resources, and review steps |
| `.gitignore` | Excludes common later state, plan, variable, crash log and local credential files from ordinary Git staging |

Receipt generation is deterministic for the same normalized specification and generated file bytes. The specification digest uses sorted JSON keys, UTF-8, and compact JSON separators; file digests use the exact UTF-8 bytes written by the tool. Dictionary key order does not change the normalized specification digest. Development templates can still change between commits sharing a development version; the receipt records hashes of the actual outputs.

## Local output permissions

Generated projects include ignore rules for common private artifacts, including nested Terraform caches, state/backup files, `.tfvars`/`.tfvars.json` files, `.tfplan`/`.plan` files and their JSON exports, `.env` files, crash logs and local CLI configuration. Terraform source, the questionnaire, receipt and `.terraform.lock.hcl` remain eligible for version control. Commit the lock file after initializing and reviewing provider selections.

Ignore rules do not remove already tracked files, prevent force-adds, encrypt data or cover every custom filename. Review `git status` and artifact names before committing. Existing `.gitignore` files are preserved by the fresh-directory overwrite checks. The checksum list covers the exported ignore file; the four-file generation receipt does not compare it.

On Unix filesystems supporting mode bits, terminal generation creates files with owner-only read/write permissions (`0600`) and a newly created destination directory with owner-only access (`0700`). A stricter process umask can remove additional permissions. Existing destination directories retain their permissions; newly created intermediate parent directories follow Python's normal defaults.

Windows access depends on the Python runtime, destination ACLs and filesystem. TerraForma does not apply or audit custom Windows ACLs, and Unix file modes do not establish a Windows privacy guarantee. Use a private destination folder. Python documents special handling for new `0700` directories on supported Windows runtimes in its [directory creation reference](https://docs.python.org/3/library/os.html#os.mkdir).

Browser downloads and extracted copies follow the browser, download-folder and extraction tool's permissions. Keep generated projects, later variable files, state and plan exports in folders with appropriate access controls. These creation defaults do not encrypt files or protect them from administrators, backups, cloud sync or an already accessible directory.

## Recover from interrupted generation

Terminal generation refuses to overwrite an existing project. If writing fails or a keyboard interrupt occurs, it attempts to remove every file created by that invocation, preserving pre-existing files and directories. A failed removal does not prevent the remaining cleanup attempts. Incomplete cleanup returns an error naming the partial artifacts that could not be removed; it does not report successful generation.

Each generated file is flushed from Python's buffer and synchronized through `os.fsync` before success is reported. A synchronization error or interrupt follows the same cleanup path as a write failure. [Python documents this sequence](https://docs.python.org/3/library/os.html#os.fsync) for Unix and Windows. This requests file synchronization from the operating system; hardware/filesystem guarantees vary. Directory entries and parent directories are not synchronized, and this remains a multi-file operation rather than an atomic project transaction. Browser ZIP downloads do not use this terminal writer.

Inspect the selected output directory before retrying. Preserve any work you need, then use a fresh directory or remove only the identified partial artifacts after review. Existing Terraform files prevent regeneration into that directory. The original write failure is retained internally as the exception cause; console recovery messages omit its details and file contents.

This is best-effort recovery from handled failures, not an atomic multi-file transaction. Forced process termination, power loss, filesystem failures and concurrent changes can leave partial output without a recovery message. No existing directory is deleted or permission-adjusted, and no state or cloud operation is rolled back.

## Compare a project

Extract the ZIP or use a directory created by `terraforma wizard` or `terraforma generate`, then run:

```text
terraforma verify-project --dir ./example-web
terraforma verify-project --dir ./example-web --json-output
```

Exit `0` means the three Terraform files and saved questionnaire match this receipt, its canonical questionnaire digest matches, and its template version agrees with the questionnaire. A modified, missing, unreadable, linked, nonregular, or oversized file returns a mismatch and exit `1`. An invalid/missing receipt returns a nonzero command error. The receipt is limited to 64 KiB, each compared file to 8 MiB, and filenames to the four declared artifacts. Reports omit file contents. `specification_status` reports `match`, `digest_mismatch`, `template_mismatch`, `invalid`, or `unavailable`. Metadata parsing rejects duplicate JSON keys, non-finite numbers and unsupported JSON shapes. This checks receipt consistency rather than schema compatibility, template authenticity or live configuration behavior.

The command does not compare the ZIP guide or authenticate the checksum list. It does not execute Terraform, use cloud credentials, call AI, or upload files.

## What matching hashes establish

Receipts are unsigned local records. Anyone able to replace both files and receipt can produce a matching set. Keep a trusted original receipt or independently trusted artifact hashes when comparing copies. A match does not authenticate the generator, prove account identity, bind a binary Terraform plan, certify security, or approve deployment. The report always sets `receipt_authenticated` and `approval_granted` to `false`.

Receipts supplement source review and [local plan review](PLAN_REVIEW.md). The protected state, plan-integrity, signing/provenance, and approval workflows remain future roadmap work.

## Local validation copies

Validation works in a temporary copy of a trusted configuration. Common state, variable-value, saved plan (`.tfplan`/`.plan`) and plan JSON filenames are omitted, along with `.tfbackend`, `.terraformrc`/`terraform.rc`, crash logs and `.env` files. Filename matching is case-insensitive, including the existing excluded cache and credential directories. Provider locks, linter configuration, local modules and other assets remain available. These exclusions are naming rules, not a secret scanner; inspect other assets before validation.

Each included file is checked for a regular file before opening and on the opened descriptor, then read with an 8 MiB limit plus one overflow byte. The actual copied bytes count toward the 32 MiB workspace limit, so growth after the first size check cannot silently bypass the byte budget. POSIX nonblocking open avoids waiting on a named pipe substituted at open. Ordinary filesystem races and untrusted execution are not fully contained. Raw/generated HCL also has an 8 MiB per-file limit. No source files, state or cloud resources are modified by these copy checks.

An existing `.terraform.lock.hcl` is used with `terraform init -lockfile=readonly`, retaining its provider selections and checksum requirements. Changes to provider requirements, unsupported locked versions or platform checksum gaps can fail initialization. Review any lock update separately in the real project; validation never upgrades or retries with a writable lock. Without a lock, validation can select a matching provider and discard its temporary lock on cleanup. This does not pin remote module contents, authenticate a template or sandbox native plugin execution. See [Terraform initialization](https://developer.hashicorp.com/terraform/cli/commands/init).
