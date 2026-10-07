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

Receipt generation is deterministic for the same normalized specification and generated file bytes. The specification digest uses sorted JSON keys, UTF-8, and compact JSON separators; file digests use the exact UTF-8 bytes written by the tool. Dictionary key order does not change the normalized specification digest. Development templates can still change between commits sharing a development version; the receipt records hashes of the actual outputs.

## Local output permissions

On Unix filesystems supporting mode bits, terminal generation creates files with owner-only read/write permissions (`0600`) and a newly created destination directory with owner-only access (`0700`). A stricter process umask can remove additional permissions. Existing destination directories retain their permissions; newly created intermediate parent directories follow Python's normal defaults.

Windows access depends on the Python runtime, destination ACLs and filesystem. TerraForma does not apply or audit custom Windows ACLs, and Unix file modes do not establish a Windows privacy guarantee. Use a private destination folder. Python documents special handling for new `0700` directories on supported Windows runtimes in its [directory creation reference](https://docs.python.org/3/library/os.html#os.mkdir).

Browser downloads and extracted copies follow the browser, download-folder and extraction tool's permissions. Keep generated projects, later variable files, state and plan exports in folders with appropriate access controls. These creation defaults do not encrypt files or protect them from administrators, backups, cloud sync or an already accessible directory.

## Compare a project

Extract the ZIP or use a directory created by `terraforma wizard` or `terraforma generate`, then run:

```text
terraforma verify-project --dir ./example-web
terraforma verify-project --dir ./example-web --json-output
```

Exit `0` means the three Terraform files and saved questionnaire match this receipt. A modified, missing, unreadable, linked, nonregular, or oversized file returns a mismatch and exit `1`. An invalid/missing receipt returns a nonzero command error. The receipt is limited to 64 KiB, each compared file to 8 MiB, and filenames to the four declared artifacts. Reports omit file contents.

The command does not compare the ZIP guide or authenticate the checksum list. It does not execute Terraform, use cloud credentials, call AI, or upload files.

## What matching hashes establish

Receipts are unsigned local records. Anyone able to replace both files and receipt can produce a matching set. Keep a trusted original receipt or independently trusted artifact hashes when comparing copies. A match does not authenticate the generator, prove account identity, bind a binary Terraform plan, certify security, or approve deployment. The report always sets `receipt_authenticated` and `approval_granted` to `false`.

Receipts supplement source review and [local plan review](PLAN_REVIEW.md). The protected state, plan-integrity, signing/provenance, and approval workflows remain future roadmap work.
