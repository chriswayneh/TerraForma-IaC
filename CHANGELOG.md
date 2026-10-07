# Changelog

## Unreleased

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
