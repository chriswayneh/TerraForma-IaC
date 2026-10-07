# Changelog

## Unreleased

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
