# Dependency trust and updates

## Generated provider constraints

| Recipe | Constraint | Compatibility boundary |
| --- | --- | --- |
| AWS | `~> 6.0` | Existing AWS template family |
| Azure Windows VM | `~> 4.81` | Validated Windows argument names, including `automatic_updates_enabled` |
| Other Azure recipes | `~> 4.0` | Existing non-Windows template family |
| Google Cloud | `~> 7.0` | Existing Google template family |

The Azure Windows floor excludes AzureRM 4.0's older `enable_automatic_updates` argument name. Compare the provider's [4.0 documentation](https://github.com/hashicorp/terraform-provider-azurerm/blob/v4.0.0/website/docs/r/windows_virtual_machine.html.markdown) with [4.81 documentation](https://github.com/hashicorp/terraform-provider-azurerm/blob/v4.81.0/website/docs/r/windows_virtual_machine.html.markdown). Review a lockfile upgrade before using that recipe with an older provider selection. Constraints do not establish package trust or replace the dependency lockfile.

CI and the reusable Action reference setup actions by full commit SHA. The following commits were resolved through GitHub's API from tags in the official repositories on October 6, 2026. Annotated tags were dereferenced to their underlying commit.

| Action | Selected tag | Pinned commit |
| --- | --- | --- |
| actions/checkout | v7.0.1 | [3d3c42e](https://github.com/actions/checkout/commit/3d3c42e5aac5ba805825da76410c181273ba90b1) |
| actions/setup-python | v7.0.0 | [5fda3b9](https://github.com/actions/setup-python/commit/5fda3b95a4ea91299a34e894583c3862153e4b97) |
| hashicorp/setup-terraform | v3 | [b9cd54a](https://github.com/hashicorp/setup-terraform/commit/b9cd54a3c349d3f38e8881555d616ced269862dd) |
| terraform-linters/setup-tflint | v4 | [90f302c](https://github.com/terraform-linters/setup-tflint/commit/90f302c255ef959cbfb4bd10581afecdb7ece3e6) |

Update the workflow and composite Action together after reviewing the upstream change. Verify the selected commit in the official repository and run all CI jobs, including the installed-wheel and composite-Action smoke checks. A tag name alone does not identify immutable source.

Checkout and Python setup now use Node 24; self-hosted runners need Actions Runner v2.327.1 or later. Authenticated Git commands inside Docker container actions require v2.329.0 or later with the selected checkout version. Project CI uses GitHub-hosted runners and disables checkout credential persistence. See the official [checkout release](https://github.com/actions/checkout/releases/tag/v7.0.1) and [Python setup release](https://github.com/actions/setup-python/releases/tag/v7.0.0).

Terraform 1.14.0 and TFLint 0.61.0 are selected explicitly for native checks. Provider constraints remain in the generated Terraform; initialization downloads provider packages. Preserve and review Terraform's dependency lock file in deployment projects. Setup-action commit pins do not independently certify the binaries, downloaded provider packages, or linter plugins.

Python package minimum versions are declared in `pyproject.toml`. Installations currently resolve compatible package versions from the configured package index; they are not a hash-locked dependency set. Platform CI checks that the resolved set works, but dependency resolution can change between runs. A future reproducible release workflow must record and verify the resolved packages and hashes before treating dependency artifacts as reproducible.

Native tools and their plugins execute on the host. File-copy isolation is not containment for untrusted dependencies or Terraform configurations. Follow the [security boundaries](ARCHITECTURE.md) and validate only trusted source.
