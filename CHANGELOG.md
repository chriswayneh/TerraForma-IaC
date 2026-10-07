# Changelog

## Unreleased

- Add a versioned project specification and a contract derived from every declared recipe variable.
- Ask for non-secret recipe inputs in the browser and preserve them across preview, validation, and ZIP export.
- Add `project-inputs` and `generate --spec` commands; reject unsupported/secret inputs and omit values from validation errors.

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
