# Contributing

TerraForma-IaC is in active development. Check the [roadmap](docs/ROADMAP.md) before proposing a large feature, and open an issue to describe the problem and expected behavior.

## Local setup

```powershell
python -m venv .venv
.venv/Scripts/python.exe -m pip install -e ".[dev]"
.venv/Scripts/python.exe -m pytest -q
.venv/Scripts/python.exe -m ruff check src tests
.venv/Scripts/python.exe .github/scripts/check_doc_links.py
.venv/Scripts/terraforma.exe serve
```

On macOS/Linux, replace `.venv/Scripts/` with `.venv/bin/`. Python 3.11+ is required. Terraform and TFLint must be on PATH for native validation. Set `TERRAFORMA_NATIVE_TESTS=1` to include the provider-schema and native lint matrix; these checks download provider binaries and need network access.

The documentation check needs Git and inspects tracked Markdown files. It checks local inline guide/image targets within the repository, including percent-encoded paths and angle-wrapped paths with spaces. External URLs and heading anchors are not verified. GitHub CI runs this check on Linux and Windows alongside the Python checks.

## Pull requests

- Explain the user-visible problem, the resulting behavior, and how it was verified.
- Keep generation, validation, diagnostics, and UI responsibilities separate.
- Add meaningful tests for changed behavior. Avoid claims of cloud deployment verification unless there is evidence.
- Keep UI text accessible to people learning Terraform. Explain costs, inputs, and cloud-specific behavior where they affect a decision.
- Do not commit credentials, variable-value files, state files, provider binaries, or virtual environments.
- Do not introduce an automatic apply/destroy path into the guided workflow.

## Template changes

Validate all affected provider/workload/access/encryption combinations. Terraform validation checks structure, not successful provisioning. If a change affects deployment behavior, document the verification limits and any cloud-specific prerequisites.

## Reporting issues

Include the operating system, Python version, tool versions, the selected provider/workload, and steps to reproduce. Remove credentials and sensitive values from logs before sharing them. For suspected vulnerabilities, follow [SECURITY.md](SECURITY.md).
