# TerraForma-IaC v0.3.0

Enter infrastructure requirements, generate a reusable Terraform project, and review its files and selected plan policies locally.

## Included

| Workflow | What you can do |
| --- | --- |
| Guided configuration | Answer the declared inputs for supported AWS, Azure and Google Cloud recipes through the browser or CLI |
| VM recipes | Generate supported Linux and Windows configurations, with provider-specific image, capacity, networking, storage and access choices |
| Reusable projects | Save and reload non-secret specifications; preserve external secret references |
| Local checks | Validate trusted configurations with Terraform/TFLint; compare exported files to generation receipts |
| Change review | Review supplied Terraform plan JSON with policy 0.11.0, showing blocking findings and unresolved coverage |
| State preparation | Enter, import, check and download separate S3, Azure Blob or GCS storage references |
| Target checks | Inspect local tool availability; optionally consent to bounded cloud CLI metadata reads |

Storage fields include format hints and safe correction messages. Unknown fields, credentials and unsupported schemas fail closed without exposing their values. Saved `0.3.0.dev0` project specifications remain accepted; imports regenerate files with the installed generator and require review.

## Install

Download the wheel from this GitHub release and install it into a Python 3.11+ virtual environment:

```text
python -m pip install "./terraforma_iac-0.3.0-py3-none-any.whl[web]"
terraforma serve
```

Open `http://127.0.0.1:8765`. Generation needs no cloud accounts or AI key. Terraform and TFLint are separate installations required only for native validation. This release is distributed through GitHub, not PyPI.

## Acceptance gates

| Phase 1 gate | Evidence |
| --- | --- |
| Invalid specifications fail closed | Strict schemas, shared input validation, bounded/strict JSON, rejected unsupported and secret fields |
| Reports omit raw plan values | Value-free findings, bounded plan processing and redaction regressions |
| Policy decisions have meaningful tests | Destructive changes, network exposure, storage protections, unknown controls and key-handling regressions |
| Behavior and remaining gaps are documented | Architecture, input contracts, artifact handling, dependency trust, state protection and verification guides |
| No apply endpoint | Generation, validation, read-only preflight and review remain separate from provisioning |

Exact local and CI results are recorded in the [verification record](VERIFICATION.md). Platform and native checks establish the tested behaviors only.

## Limits

This release does not run plan, apply or destroy, configure remote state, migrate state, grant IAM access or approve deployment. Backend inputs describe future setup; they do not establish authentication, encryption, locking or recovery. Native validation runs trusted provider code and is not a process sandbox.

VM recipes cover documented patterns, not every cloud option. Account capacity, quotas, image compatibility, effective permissions, creation/login/teardown and live AI requests remain unverified. Atomic project publication and protected execution artifacts remain future work. Complete VM acceptance remains the v0.4.0 milestone; resource composition, protected state and approved provisioning follow later phases.
