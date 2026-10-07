# Security

TerraForma-IaC is a local development tool. It must not be exposed as a shared network service without additional authentication and execution isolation.

## Reporting a vulnerability

Do not post credentials or working exploits containing private data in a public issue. Use the repository's private vulnerability reporting feature when available. Otherwise, open a minimal issue requesting a private reporting channel without including sensitive details.

## Execution model

The supported UI launcher binds to loopback. Mutation endpoints require a local session token and reject cross-origin requests. The UI accepts questionnaire selections rather than arbitrary HCL or host paths.

The validation sandbox isolates temporary files. Native tools and provider/linter plugins still execute on the host with its environment and network access. It is not a containment boundary for untrusted code. CLI validation should only be used with trusted configurations and plugins.

Generation never applies or destroys infrastructure. Generated templates still require cloud-specific review, secure state storage, appropriate network rules, and a reviewed Terraform plan before deployment.

## AI diagnostics

The web UI sends failed command logs to OpenAI only when the user enables AI explanations. The CLI uses its documented `--ai/--no-ai` option. Known-secret redaction is best effort; tool logs can contain source snippets or sensitive data that is not recognized. Use local-only diagnosis when that is inappropriate. An AI suggestion is unverified advice and does not change files automatically.

## Supported versions

The project is pre-release. Security fixes are developed on `main`; stable support windows will be defined before v1.0.
