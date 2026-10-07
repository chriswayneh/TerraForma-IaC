# Dependency trust and updates

CI and the reusable Action reference setup actions by full commit SHA. The following commits were resolved through GitHub's API from tags in the official repositories on October 6, 2026. Annotated tags were dereferenced to their underlying commit.

| Action | Selected tag | Pinned commit |
| --- | --- | --- |
| actions/checkout | v4 | [11d5960](https://github.com/actions/checkout/commit/11d5960a326750d5838078e36cf38b85af677262) |
| actions/setup-python | v5 | [a26af69](https://github.com/actions/setup-python/commit/a26af69be951a213d495a4c3e4e4022e16d87065) |
| hashicorp/setup-terraform | v3 | [b9cd54a](https://github.com/hashicorp/setup-terraform/commit/b9cd54a3c349d3f38e8881555d616ced269862dd) |
| terraform-linters/setup-tflint | v4 | [90f302c](https://github.com/terraform-linters/setup-tflint/commit/90f302c255ef959cbfb4bd10581afecdb7ece3e6) |

Update the workflow and composite Action together after reviewing the upstream change. Verify the selected commit in the official repository and run all CI jobs, including the installed-wheel and composite-Action smoke checks. A tag name alone does not identify immutable source.

Terraform 1.14.0 and TFLint 0.61.0 are selected explicitly for native checks. Provider constraints remain in the generated Terraform; initialization downloads provider packages. Preserve and review Terraform's dependency lock file in deployment projects. Setup-action commit pins do not independently certify the binaries, downloaded provider packages, or linter plugins.

Python package minimum versions are declared in `pyproject.toml`. Installations currently resolve compatible package versions from the configured package index; they are not a hash-locked dependency set. Platform CI checks that the resolved set works, but dependency resolution can change between runs. A future reproducible release workflow must record and verify the resolved packages and hashes before treating dependency artifacts as reproducible.

Native tools and their plugins execute on the host. File-copy isolation is not containment for untrusted dependencies or Terraform configurations. Follow the [security boundaries](ARCHITECTURE.md) and validate only trusted source.
