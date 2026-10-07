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

- Eight added receipt checks cover inconsistent canonical digests/template versions, malformed or ambiguous questionnaire metadata despite matching file hashes, key-order/whitespace equivalence, CLI failure status and value privacy. The rebuilt isolated installed wheel confirms an intact comparison and CLI exit `1` for a conflicting canonical digest. Comparison remains unsigned and does not authorize deployment.

- Terminal output uses exclusive file creation with mode `0600` and new leaf directories with mode `0700`. Existing overwrite and rollback tests pass on Windows. The rebuilt isolated installed wheel generates an intact receipt and refuses overwrites. Two added Unix CI tests verify private modes under a permissive umask and preservation of existing directory permissions; they are skipped on Windows. Download/extraction permissions and cross-version Windows ACL privacy are not established by these checks.

- Ten local readiness tests cover missing native/web/base dependencies, unsupported Python, selected-capability exit status, JSON/text reports and omission of private environment values and discovered paths. The rebuilt isolated installed wheel confirms web availability, validation exit `1` with missing tools, and generation remaining available. The command discovers package metadata and PATH only; it does not run tools or establish executable trust, cloud identity or provider readiness.

- Optional workload identity checks cover enabled/disabled AWS profiles, Azure managed identities and GCP user-managed service accounts, conditional required references, malformed/credential-shaped values, terminal collection, resource guides and ZIP import/export. Six added provider cases pass native validation/TFLint; two native console cases enforce the required-reference condition. The full generator run passes 166 tests, and a focused identity/username rerun passes after correcting literal-hyphen patterns.
- Browser checks confirm reference visibility, required-field focus, disabled exports omitting inactive values, enabled ZIP/import preservation, AWS/GCP format checks and Azure principal output. Corrected HTML patterns reject invalid project/environment/username/identity values and accept supported hyphenated identifiers. A rebuilt isolated installed wheel passes all three identity export/import flows and conditional missing-reference errors. Identity existence, pass-role/act-as authorization, IAM/RBAC permissions and live provisioning remain unverified.
- VM network-range tests cover all three private address families, provider-specific prefix bounds, canonical network notation, rejection of public/reserved/IPv6 inputs, and export/import preservation. All 60 recipe combinations, 16 data-disk cases and nine selected network cases pass native validation/TFLint. Three additional native console checks confirm Terraform conditions match shared validation for accepted/rejected ranges. Browser checks confirm field focus on invalid input, correction, ZIP export and import; the isolated installed wheel retains the selected range and summary. Overlap with existing networks and live connectivity remain unverified.
- Policy version `0.3.0` adds 23 cases covering metadata endpoint/token combinations, missing/malformed settings, attached identity review gaps and value privacy. The browser and rebuilt isolated installed CLI show the metadata block, permission gap, policy version and digest without private values; CLI exits `1`. The browser and packaged UI also show the updated infrastructure-requirements introduction.
- Policy version `0.2.0` tests cover enabled, disabled, unresolved and malformed AWS/GCP VM protection controls, protection removal, and forced AWS disk detach. Browser and rebuilt installed-CLI checks show both lifecycle blocks, exit `1`, the policy version and digest, while omitting private resource keys and raw values. No plan or apply was executed.
- 629 local unit/API/generator/guidance/plan-review tests pass, including shared specifications, input contracts, numeric bounds, export/import preservation, terminal input collection, recipe capability metadata, SSH key structure/type checks, browser plan-review route limits/privacy/concurrency, explicit AWS account constraints, environment-label mapping, artifact receipts/comparisons, clean-destination/rollback safeguards, diagnostic control-character handling, database client-network restrictions, configured tier capacity, supported Linux image inputs, safe field-level feedback, standalone VM access/export contracts, Azure administrator usernames, strict EC2 monitoring boolean answers, bounded native command output, AWS/GCP VM deletion protection, read-only configuration summaries, and conditional data disk questions.
- The 60 native recipe combinations and 16 additional enabled/disabled data-disk cases pass Terraform validation and TFLint. The extra cases cover all eight offered disk classes across AWS/Azure/GCP. Unit/API checks reject invalid disk sizes/types, preserve export/import choices, and omit inactive fields from the summary. These checks do not establish VM/disk/SKU compatibility in a live account.
- Browser checks confirm enabling a disk reveals its size/type questions, disabling it hides and disables them, and hidden invalid values do not block generation. Enabled ZIP export/import preserves a selected 256 GiB GCP SSD disk; disabled exports omit inactive size/type inputs. The enabled disk appears in the resource guide, and the 390-pixel form has no horizontal document overflow.
- The rebuilt development wheel passed optional-disk compilation, resource-guide, ZIP export and manifest import checks from an isolated installed environment outside the source checkout.
- Browser generation/import and ZIP checks show effective answers in the summary and project guide. The 390-pixel summary layout has no horizontal document overflow. Terminal `describe` checks confirm no files or native commands are started; external secret requirements never read the secret environment value.
- A rebuilt installed wheel passed `describe --json-output` with the selected EC2 monitoring answer; the command is included in the distribution.
- Browser checks confirm standalone AWS/GCP VM deletion protection defaults on, maps to the intended Terraform attribute, and displays enabled/disabled lifecycle guidance for the selected answer. API tests verify both choices survive export and import; Azure VM locks and web-tier protection controls are not offered.
- The updated development wheel passed AWS/GCP VM boolean export/import, lifecycle-guide, UI-asset, and bounded-command checks from an isolated installed environment outside the source checkout. All 60 native generator combinations passed again after adding protection attributes; no cloud deployment was run.
- Real Python subprocess tests cover simultaneous stdout/stderr, output overflow, exact output limits, partial timeout logs, closed terminal input, and invalid deadlines. A cloud-free `terraform_data` configuration passed real Terraform init/validate and TFLint init/lint through the bounded runner; no apply was run.
- Browser checks confirm enabled and disabled EC2 monitoring answers survive step navigation, ZIP export, and file-chooser project import. Generated Terraform declares a boolean and retains the selected value; values such as strings and numbers are rejected by the shared contract.
- All 60 native generator cases pass with Terraform 1.14.0 and TFLint 0.61.0 after adding VM-size, boot-disk inputs, AWS account allowlists, environment tags/labels, database client-network checks, tier capacity, supported Linux image selectors, and standalone VMs. Separate native console checks confirm network policy acceptance, selected image/publisher/startup expressions, and username format/reserved-name conditions. These checks validate provider schemas; they do not deploy resources or establish authenticated account identity.
- The browser focused an invalid CIDR field without reflecting its value in the error; editing it cleared the error and generation succeeded.
- The browser generated the selected Ubuntu configuration and a four-VM tier; updated desktop and 390-pixel layouts have no horizontal document overflow.
- Browser checks confirm required-field validation, numeric disk bounds, and configured values in the generated Terraform preview. The 390-pixel layout has no horizontal document overflow.
- The browser rejected an invalid AWS account ID, generated with a valid-format example, and displayed the requested account as unverified. The updated desktop form has no horizontal document overflow.
- A saved AWS project was imported through the browser file chooser; region, VM size, disk size/type, project name, and preview were restored from the specification.
- A fresh installed development wheel passed project import/export/checksum checks, local plan review, CLI generation, and receipt comparison from outside the source checkout. Its imported module path was confirmed in the clean environment's `site-packages`.
- The updated installed wheel passed standalone VM ZIP export/import, receipts, catalog, and UI-asset checks for all three providers. Installed CLI generation with a selected Ubuntu VM image completed and all four declared receipt files matched. The GCP browser flow showed OS Login metadata and a VM address output; desktop and 390-pixel layouts had no horizontal document overflow.
- The browser reviewed the real cloud-free `terraform_data` plan export and showed its action count, unresolved-value/policy gaps, manual-review status, and digest. No apply was run.
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
