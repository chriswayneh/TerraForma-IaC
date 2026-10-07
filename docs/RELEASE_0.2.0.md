# TerraForma-IaC v0.2.0

The first public release provides a lightweight local interface for generating and understanding Terraform without writing its syntax.

## Included

- A local web UI and terminal questionnaire for guided configuration.
- AWS, Azure, and Google Cloud recipes for web servers, load-balanced tiers, PostgreSQL, and static-site storage.
- HCL previews, resource explanations, required-input guidance, and ZIP export.
- Optional saved non-secret questionnaire selections.
- Filesystem-isolated Terraform/TFLint validation with timeouts and readable failures.
- Explicit opt-in AI diagnostics; no automatic edits or deployment.
- Initial CLI plan review for destructive changes, selected administrative-access and AWS storage/database protections, and policy coverage gaps.
- Local session-token/origin protections and a 64 KiB API request-body limit.
- A reusable GitHub Action with explicit AI opt-in.

## Install

Use the source quickstart in the README, or download the wheel from this GitHub release and install it into a virtual environment:

```text
python -m pip install "./terraforma_iac-0.2.0-py3-none-any.whl[web]"
terraforma serve
```

This release is published on GitHub; it is not published to PyPI. Native Terraform and TFLint installation is separate and is only needed for validation. The browser opens at `http://127.0.0.1:8765`.

## Verification

133 local tests pass; the 48 optional native template combinations have separate Terraform/TFLint validation evidence. GitHub CI checks Windows/Linux and Python 3.11/3.14, native templates, and installed-wheel UI assets. A real local Terraform plan was exported and inspected without apply. See the verification record and release workflow run for exact evidence.

## Limits

This release generates configurations and reviews local checks. It does not collect every VM setting, plan/apply/destroy infrastructure, manage remote state, or orchestrate Terragrunt. The plan reviewer implements limited rules and never authorizes apply. Filesystem isolation does not contain untrusted native plugins. Live OpenAI calls, cloud deployments, and macOS execution remain unverified.

Full provider-aware VM inputs and approved provisioning are future milestones in the revised roadmap. Free reusable templates/modules will be considered with license, provenance, compatibility, and security review.
