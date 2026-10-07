# Changelog

## Unreleased

- Corrected catalog image choices for Windows recipes, removed the stale GCP exact-pin exclusion and synchronized gp3 capability text with current input limits. Catalog metadata now has regressions against questionnaire choices and performance bounds.

- Expanded AWS standalone gp3 tuning to the documented regional 80,000 IOPS/2,000 MiB/s ceilings while preserving included-performance defaults and size/IOPS/throughput ratios. Outposts remains unsupported; instance bandwidth, availability and achieved performance require separate verification.

- Terminal generation now flushes and synchronizes generated file contents before reporting success. Sync errors and interrupts trigger existing cleanup, with redacted recovery messages; atomic multi-file publication and directory durability remain outside this change.

- Plan review policy 0.10.0 flags EC2 metadata token responses that can cross additional network hops, with explicit unknown/malformed-control handling. Existing IMDSv1 blocks remain in place; reports remain redacted and never grant provisioning approval.

- Added an AWS standalone metadata token-response hop setting with readable host/container options and an unmanaged default. IMDSv2 stays required; the form explains expanded reachability and that returning to default does not reset an existing setting.

- Azure Windows standalone VMs now offer Server 2022 Core Gen2 alongside the desktop default under Microsoft's refreshed windowsserver2022 offer. External credentials, patching and Trusted Launch controls are preserved; installation changes require replacement and compatibility review.

- GCP Windows standalone VMs now offer the published Server 2022 Core family or a matching supported exact image name. Desktop remains the default; input and Terraform guards reject mismatched desktop/Core pins. Existing IAP, activation and boot controls are preserved.

- Azure Windows generation now references the refreshed windowsserver2022 offer after Microsoft's legacy-offer deprecation. The form and generated guidance warn that regeneration can replace existing VMs, old pins need revalidation and application dependencies must be reviewed. Existing guests are not migrated.

- Added an AWS Windows Server 2022 Core Base image choice alongside the existing Full Base default. Amazon publisher, selected image-name, x86_64 and HVM filters remain in place for latest or pinned AMIs; Core desktop/compatibility and replacement risks are explained.

- Added readable connection-path, CPU-credit and GCP maintenance option labels to the browser and terminal questionnaire. Terraform/specification values and defaults remain unchanged.

- Added explicit AWS/GCP standalone boot-disk deletion or retention choices, preserving deletion by default. The form and generated guidance explain separate data-disk/key lifecycle, AWS KMS recovery requirements and GCP replacement naming conflicts. No live retention or recovery was run.

- GCP Windows standalone VMs accept latest or a supported exact Windows Server 2022 Datacenter image name from the fixed windows-cloud publisher. Input and Terraform guards reject other image variants; availability and cloud boot remain unverified.

- GCP standalone Linux/Windows questionnaires now offer an IAP tunnel connection path, with one targeted administrator port and the unused direct network question hidden. Direct access remains the default; IAM grants and guest authentication remain outside generation. Added connection guidance without opening live tunnels.

- Local plan policy 0.9.0 recognizes narrowly targeted Google IAP IPv4 administrator firewall rules as mandatory manual review. Broader or unresolved rules retain the block; tunnel IAM, guest authentication and effective access remain unverified. Guided IAP generation remains planned.

- Added AWS standalone VM CPU credit choices: provider default, standard or unlimited for x86 T2/T3/T3a families. The shared questionnaire/specification and Terraform guards enforce the supported scope; defaults leave the setting unmanaged, and removing an explicit mode does not reset an existing VM.

- AWS standalone VM preflight now checks EBS-backed HVM boot support in the existing size response. Missing, incompatible and malformed capabilities remain distinct and prevent a subsequent zone offering read, including when root encryption is disabled.

- Added a cloud authentication guide linked from the target-check card and documentation. It covers existing AWS SSO profiles, Azure CLI login and separate Google CLI/ADC credentials without collecting secrets or running login commands in TerraForma.

- Clarified the storage encryption choice in the web UI and before the terminal question: disabling it requests unencrypted AWS boot/database storage, while standalone data disks retain encryption. Provider-specific defaults and account policy still apply.

- AWS standalone VM size preflight now checks reported EBS encryption support when the generated root or data disk requires encryption. Missing or unsupported capabilities remain unresolved and prevent a subsequent zone offering read; no extra cloud request is added.

- The optional AWS VM metadata preflight now reads the selected availability zone's instance-type offering after target and CPU checks pass. Incomplete, malformed and failed responses remain unresolved; an offering does not verify capacity, quotas, deployment permissions or grant approval.

- Added optional AWS standard availability zone placement for standalone Linux/Windows VMs, preserving automatic placement when blank. Subnet guards require two standard zones and reported membership; Local Zones/Wavelength Zones/zone IDs are unsupported. Regeneration or placement changes can replace resources and lose data; zone capacity remains unverified.

- Existing provider locks are now read-only during validation initialization. Dependency/lock conflicts are reported without an upgrade or writable retry; projects without a lock retain explicit unpinned-validation guidance.

- Validation copies now omit saved plans/plan JSON, backend configuration, local Terraform CLI configuration and crash logs using case-insensitive filename rules. Bounded regular-file reads enforce limits against actual copied bytes; raw HCL receives the same per-file limit. Other assets still require review.

- Local plan policy 0.8.0 now reviews Azure managed disk remote import/export and public network controls. Unrestricted exports/public access and reopening a deny-all boundary are blocked; private export and unknown settings require review. No provisioning approval is granted.

- Newly generated optional Azure managed data disks deny remote import/export and disable public network access. The recipe retains empty-disk attachment; exports, private endpoints and backup/recovery workflows remain unsupported.

- The existing opt-in Azure VM size read now checks a selected availability zone against reported SKU location metadata. Unsupported, unknown and malformed zone results remain distinct; no extra cloud read or deployment approval is added.

- Added Azure standalone Linux/Windows placement choices: regional or availability zone 1–3. The VM, optional data disk, Standard NAT gateway and generated public IPs share the selected placement. Changes can replace resources and lose data; zone support/capacity remain unverified.

- Removed repeated non-secret field descriptions from the terminal questionnaire. Input guidance appears once per applicable question; external-secret guidance remains visible.

- Local project-specification and plan-JSON readers now check for regular files before opening and recheck the opened descriptor. Pipes, devices and directories are rejected; existing byte limits and generic CLI error handling remain in place.

- Added GCP standalone Linux/Windows host-maintenance and automatic-restart questions, defaulting to live migration and enabled restart on standard VMs. Inputs persist through generation/import; guest patching, application recovery and live host behavior remain unverified.

- Administrator-network questions now explain the distinction between accepted generation inputs and the stricter local plan policy: a public `/32` can generate files but remains a blocking administrator-access finding during plan review.

- Updated terminal provider/workload prompts to direct selection wording. Standalone VM guidance now explains administrator access and routing; HTTP/TLS guidance appears only for web-server recipes.

- Improved recovery from failed or interrupted terminal generation. Cleanup attempts all newly created artifacts even when one removal fails, and the CLI identifies leftovers requiring review without exposing underlying error details.

- Added an Azure Windows automatic patch-assessment question. It preserves automatic OS installation and the enabled VM Agent; platform assessment, agent health and patch completion remain unverified.

- Raised the Azure Windows provider floor to AzureRM 4.81 within 4.x, matching validated automatic-update argument names. Older 4.0 locks require a reviewed upgrade; non-Windows Azure constraints remain unchanged.

- Grouped browser inputs into cloud target, image/capacity, network/access, storage, operations/identity and workload sections. All declared questions remain visible when applicable; section headings do not hide required inputs or change the saved specification.

- Azure Secure Boot guidance now explicitly identifies AzureRM's VM replacement and potential OS-disk deletion behavior when that setting changes.

- External-secret questions now display their complete contract guidance before generation, including Azure Windows password retention in Terraform state and plans.

- Added Azure Linux/Windows VM host cache inputs for boot and optional data disks. OS caching defaults to ReadWrite and data caching to None. Unsupported modes and non-default data caching without an enabled disk fail closed; workload durability, capabilities and safe cache changes remain unverified.

- The terminal questionnaire now shows each field's input guidance before the question, including defaults, compatibility limits and external-secret/state handling. Hidden conditional questions remain hidden.

- Added initial Azure Windows Server 2022 generation with restricted RDP, separate guest naming, licensing choices and an external administrator-password reference. Passwords remain outside saved questionnaire files but AzureRM retains them in Terraform state/plans; protected backend setup and live deployment checks remain outstanding. Plan policy `0.7.0` extends Azure Secure Boot/vTPM review to Windows VM resources.

- Updated the workspace introduction and questionnaire labels to direct input wording, and refreshed GitHub screenshots that still showed older copy.

- Added a GCP Windows Server 2022 recipe with restricted RDP, external user/password setup, activation routing, configurable Shielded VM settings and no password or private-key collection. Exact Windows image pins and Azure Windows remain planned.

- Added an initial AWS Windows Server 2022 VM recipe with restricted RDP, RSA public-key validation, configurable machine/disks/network and external EC2 password recovery. No password or private key is collected or retrieved. Azure/GCP Windows generation and live deployment/access checks remain planned.

- Applied Azure environment/management tags explicitly to supported generated compute, network, storage and private DNS resources, alongside the resource group. Untaggable associations and supporting resources remain excluded.

- Separated AWS/Azure/GCP builders from shared recipe configuration and HCL rendering. Existing generator imports remain available; generated bytes and input contracts are unchanged across all 60 configuration combinations.

- Added gp3 boot/data disk IOPS and throughput inputs for standalone AWS VMs, defaulting to the included baseline. Conditional questions, export/import, ratio checks and Terraform preconditions preserve requested settings and reject incompatible combinations; template limits remain explicit.

- Added optional fixed private IPv4 addresses for standalone VMs across AWS/Azure/GCP. Shared input/export handling and generated Terraform preconditions reject addresses outside the chosen subnet or in provider-reserved ranges; blank retains cloud allocation, with availability and independent reservation left unverified.

- Added Azure encryption-at-host support checks to the existing opt-in compute-size read when encryption is requested. Incompatible and unknown capabilities require review; malformed metadata fails closed, with subscription feature registration left for separate verification.

- Added optional accelerated networking for standalone Azure Linux VMs, off by default, with shared questionnaire/export handling and support metadata in the existing opt-in size check. Incompatible, unknown and malformed capability responses remain distinct from deployment approval.

- Added managed command cleanup with Windows jobs and POSIX process groups, including helper cleanup after normal completion, timeout and output overflow. Trusted-tool limitations and the Windows launch/attachment gap remain explicit.

- Added standalone VM reference outputs across AWS/Azure/GCP: resource ID, name and placement, plus Azure resource group. AWS Name tags are explicitly described as non-unique.

- Extended plan policy to `0.6.0` with GCP interactive serial-console checks on instances/templates. Enabled access and removal of an explicit disable are blocked; missing/inherited settings require review, and malformed metadata fails closed.

- Explicitly disabled interactive GCP serial console access on compute instances/templates, overriding project metadata inheritance. Read-only serial logs and cloud IAM remain separate considerations.

- Added exact AWS AMI IDs for compute recipes while retaining trusted owner/OS/HVM constraints and adding an explicit x86_64 filter. A pin adds an image-ID filter; unsupported or unavailable pins do not fall back to latest.

- Added exact GCP image names for compute recipes with fixed publisher projects, selected-OS matching and Terraform preconditions. Default family resolution remains available; ARM/custom references and mismatched OS pins are rejected.

- Added an exact Azure marketplace image version input for VM and web-tier recipes, retaining `latest` as the default and the existing Canonical offer/SKU constraints. Export/import preserves the answer, with replacement/data-loss and availability guidance.

- Extended the existing Azure standalone VM metadata check to reported Gen2/Trusted Launch support. Unsupported and unknown boot capabilities remain visible, with no additional cloud request or deployment approval.

- Added optional Azure-managed VM boot diagnostics, off by default, with shared input/export/import handling and console-data/retention guidance. No custom storage account or diagnostic URL output is generated.

- Extended local plan policy to version `0.5.0` with Azure Linux VM Secure Boot/vTPM checks. Disabled controls require review, removal of existing controls is blocked, and malformed values fail closed without exposing raw values.

- Added guided Azure standalone VM Secure Boot, enabled by default with vTPM retained. The questionnaire explains unsigned driver and VM-size compatibility limits; guest attestation and Defender monitoring remain outside this recipe.

- Offer a separate VM-size metadata opt-in after target confirmation: reported x86 compatibility across AWS/Azure/GCP, Azure restrictions and GCP deprecation, with bounded reads and no deployment approval.

- Bound AI diagnostic response collection to 64 KiB with closed streams, absolute per-attempt timeouts, finite retry delays and redirect refusal.

- Apply shared bounded UTF-8 JSON parsing to API requests, project imports, receipts, cloud CLI metadata and AI responses; reject duplicate keys, non-finite numeric overflow and nesting beyond 64 levels.
- Require actual boolean consent before API validation can request an AI explanation.
- Include a generated `.gitignore` for common private Terraform artifacts, preserve existing ignore files, and retain provider lock files for version control.
- Offer Secure Boot for standalone GCP VMs, enabled by default with vTPM and integrity monitoring; document compatibility and stopped-VM update requirements.
- Extend plan review to GCP Shielded VM controls and removal of existing protections, using policy version `0.4.0`.

- Add browser cloud-target checks with one-time explicit consent, shared native-tool concurrency limits, readable results and invalidation after questionnaire edits.

- Add explicit CLI opt-in for bounded AWS account, Azure subscription and GCP project target reads, with mismatch/state checks, specification digests and reports omitting raw responses and credentials.

- Compare canonical questionnaire digests and template versions during receipt verification; report invalid or inconsistent metadata without revealing values.

- Create terminal-generated artifacts with Unix owner-only file permissions and private new destination directories; preserve existing directory permissions and document Windows/download boundaries.

- Add `terraforma doctor` for local package/PATH availability checks, capability-specific exit status and JSON output without tool execution or credential access.

- Extend local plan review to block tokenless AWS metadata access and flag unverified attached AWS/GCP identity permissions, using policy version `0.3.0`.

- Clarify the generator introduction: enter infrastructure requirements and review the generated Terraform.

- Add optional workload identity to standalone Linux VMs: existing AWS instance profiles, Azure system-assigned identities, and existing GCP user-managed service accounts, with conditional required references and no role grants or credential keys.

- Restore browser format checks for supported identifiers by escaping literal hyphens in shared input patterns.

- Ask for a new private IPv4 network range on standalone VMs, with provider-specific recipe bounds, derived subnet layouts and matching shared/Terraform validation.

- Extend local plan review with AWS/GCP VM protection changes and unsafe forced AWS disk detach checks, using policy version `0.2.0`.

- Add one optional empty data disk to standalone AWS/Azure/GCP Linux VMs, with conditional size/type questions, provider-specific attachments, and explicit cost/data-lifecycle guidance.

- Explain effective configuration answers/defaults in the browser and exported guide, with a read-only `describe` command for saved projects and external-secret requirements.

- Update pinned GitHub checkout/Python setup actions to official Node 24 releases and disable checkout credential persistence in CI.

- Ask for deletion protection on standalone AWS/GCP VMs, enabled by default, and explain the configuration change required before deliberate deletion or replacement.

- Bound validation command output to 512 KiB per stream, fail on overflow, and disable terminal input while retaining partial timeout diagnostics.

- Add an opt-in detailed EC2 monitoring question to AWS VM and web-tier recipes, with cost guidance and typed boolean preservation through CLI, browser, import, and export.

- Collect Azure Linux administrator usernames with matching format/reserved-name checks in the questionnaire and generated Terraform.

- Add standalone Linux VM recipes for AWS, Azure, and GCP with supported image/disk inputs, restricted SSH networks, public-key or OS Login authentication, and VM address outputs.

- Show field-specific input correction hints without reflecting submitted values; focus the invalid browser field and clear errors on edits.

- Offer supported Linux image choices from official publishers across AWS, Azure, and GCP, with image-specific AWS startup scripts and visible compatibility limits.

- Ask for load-balanced VM capacity across AWS, Azure, and GCP, with matching whole-number bounds and generated counts.

- Restrict database client networks through shared questionnaire and Terraform checks; exclude broad Azure-service firewall access.

- Add a versioned project specification and a contract derived from every declared recipe variable.
- Ask for non-secret recipe inputs in the browser and preserve them across preview, validation, and ZIP export.
- Add `project-inputs` and `generate --spec` commands; reject unsupported/secret inputs and omit values from validation errors.
- Expose VM sizes and boot-disk size/type in the existing compute recipes; apply shared typed constraints in the questionnaire and Terraform.
- Use the same input contract in the terminal wizard; keep sensitive values external and write nothing on cancellation.
- Add a recipe catalog and disclose fixed images, networking choices, unsupported features, and outstanding account checks.
- Reopen exported project specifications in the browser with bounded, strict local parsing; retain operational answers and regenerate the preview.
- Require exact recipe booleans and structurally valid Ed25519/RSA public keys for Azure; reject unsupported, malformed, and undersized key structures.
- Review existing plan JSON in the browser with bounded input, one review at a time, sanitized reports, and explicit manual-review status.
- Require an explicit target AWS account and generate a provider account allowlist; carry unverified account/subscription/project references into previews and project guides.
- Pin CI/composite setup actions to verified official commit references and require Python formatting checks in CI.
- Carry an environment label through the shared questionnaire, project target, generated tags/labels, and export guide with explicit coverage and isolation limits.
- Remove Terraform variable values and the OpenAI key from native validation subprocess environments.
- Save project manifests, deterministic generation receipts, and export checksums from both interfaces; add bounded `verify-project` comparisons that detect changed files without disclosing contents or granting deployment approval.
- Reject destinations containing existing Terraform state, variable files, initialization data, or generated artifacts before writing; check explicit wizard destinations before prompts and roll back new files after write failures.
- Strip incoming terminal controls and bidirectional formatting controls from displayed validation diagnostics and AI warning cards.

- Add a current-phase summary and version/phase table to the roadmap.
- Add a documentation index and clearer screenshot, architecture, and verification navigation.

## v0.2.0 — October 6, 2026

First public release. [Download](https://github.com/chriswayneh/TerraForma-IaC/releases/tag/v0.2.0) · [Release notes](docs/RELEASE_0.2.0.md) · [Verification](docs/VERIFICATION.md)

- Guided local web UI and CLI for AWS, Azure, and Google Cloud recipes.
- Terraform file previews, ZIP export, resource explanations, and required-input guidance.
- Optional saved non-secret choices.
- Local Terraform/TFLint validation and explicitly enabled AI explanations.
- Initial local plan review with destructive-change checks and limited resource policies.
- Local request protections, bounded request bodies, and a reusable GitHub Action.

This release does not execute infrastructure provisioning. Future capability targets are listed in the [roadmap](docs/ROADMAP.md).
