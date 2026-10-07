# Verification record

First release: `0.2.0`, October 6, 2026. This record distinguishes structural/local checks from unverified cloud behavior.

## Local checks

- 133 unit/API/generator/guidance/plan-review tests pass on Windows with Python 3.14.
- The 48 optional native template cases are skipped in the normal unit command. They were separately verified against Terraform 1.14.0 and TFLint 0.61.0 with installed AWS/Azure/Google provider schemas.
- Python lint and formatting checks pass. Browser JavaScript passes `node --check`.
- A built wheel contains the HTML, JavaScript, and both CSS files.
- A real Terraform 1.14.0 plan using the built-in `terraform_data` resource was exported and reviewed locally; no apply or cloud API call was made.
- The CLI returns exit 0 for a valid configuration and exit 1 for an invalid configuration.
- The browser completed guided generation, native validation, and ZIP download. The later onboarding flow displays required inputs and a resource guide.
- Desktop, 390-pixel, and 320-pixel layouts were inspected. Dark/light theme switching was exercised; the narrow layout had no horizontal document overflow.
- Optional saved choices were checked through selection, reload, restoration, and removal in the browser.

## Development toward v0.3.0

- 181 local unit/API/generator/guidance/plan-review tests pass, including shared specifications, input contracts, numeric bounds, export/import preservation, terminal input collection, and recipe capability metadata.
- All 48 native generator cases pass with Terraform 1.14.0 and TFLint 0.61.0 after adding VM-size and boot-disk inputs. These checks validate provider schemas; they do not deploy resources.
- Browser checks confirm required-field validation, numeric disk bounds, and configured values in the generated Terraform preview. The 390-pixel layout has no horizontal document overflow.
- A saved AWS project was imported through the browser file chooser; region, VM size, disk size/type, project name, and preview were restored from the specification.
- Python lint and formatting checks pass. The [shared specification checkpoint](https://github.com/chriswayneh/TerraForma-IaC/actions/runs/37559663074) passed all CI jobs; subsequent changes have their own workflow results.

## Release CI

The [onboarding GitHub Actions run](https://github.com/chriswayneh/TerraForma-IaC/actions/runs/37556530184) passed all four unit-test jobs (Windows/Linux, Python 3.11/3.14), the native provider-validation job, and a clean installed-wheel smoke test. Check the [latest workflow runs](https://github.com/chriswayneh/TerraForma-IaC/actions) for current commit results.

## Reproduce

```text
python -m pip install -e ".[dev]"
python -m ruff check src tests
python -m ruff format --check src tests
python -m pytest -q
```

For native cases, put Terraform and TFLint on PATH and set `TERRAFORMA_NATIVE_TESTS=1` before running tests. Provider downloads need network access. Native tests use temporary configurations and do not apply infrastructure.

## Unverified behavior

- Live OpenAI requests; diagnostics use mocked HTTP responses in tests.
- Cloud provisioning, quotas, organization policies, application reachability, and teardown.
- macOS runtime behavior; automated platform coverage currently includes Windows and Linux.
- Containment of untrusted Terraform/provider/linter execution; temporary workspace isolation is not a process security boundary.

The test environment currently emits a third-party Starlette warning about future TestClient HTTP transport changes. It does not indicate a test failure; future dependency upgrades should include transport compatibility checks.
