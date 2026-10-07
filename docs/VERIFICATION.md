# Verification record

## Provider lock validation checkpoint

- The default suite passes 1,463 tests with 228 optional/native/platform cases skipped. Ruff checks and formatting pass across 83 Python files; JavaScript syntax passes.
- Four additional runner cases verify read-only initialization only when a provider lock exists, no upgrade/writable retry, validation skipped on init failure and source lock preservation.
- Real AzureRM 4.81 initialization/validation and TFLint pass with matching reviewed dependency requirements while both source and copied lock bytes remain unchanged. An incompatible 4.0 selection fails initialization and skips Terraform validation without modifying the source lock. A previously recorded constraint change also correctly fails read-only init even when the selected version fits the new constraint.
- No apply or cloud read was run. Missing locks remain unpinned, remote module contents are not locked by this control and provider/plugin execution still requires trust.

## Validation copy input checkpoint

- The default suite passes 1,459 tests with 228 optional/native/platform cases skipped. Ruff checks and formatting pass across 83 Python files; JavaScript syntax passes.
- New copy tests cover root/nested private filename exclusions, case-insensitive matching, exact binary asset/lock preservation, UTF-8 HCL byte limits, growth after the initial size check, exact limits and temporary cleanup. A POSIX pipe-substitution case is skipped on this Windows host and included in platform CI.
- A copied cloud-free `terraform_data` configuration with a referenced asset passes real Terraform init/validate and TFLint init/lint. Saved plan, backend configuration and local CLI configuration markers are absent from the copy; no apply was run.
- Filename rules do not discover arbitrary secrets. Included assets, native tools, provider/linter plugins and inherited cloud credential chains remain trusted inputs; the copy is not an untrusted-code execution boundary.

## Azure managed disk policy checkpoint

- The default suite passes 1,428 tests with 227 optional/native/platform cases skipped. Ruff checks and formatting pass across 82 Python files; JavaScript syntax passes.
- Forty-eight disk policy cases cover unrestricted/private exports, public-network flags, reopening an existing deny-all boundary, absent/null/unknown settings, malformed values and unknown markers, destructive actions and data sources. CLI and API return the same redacted report without exposing disk values or resource addresses.
- A temporary browser tab imported a synthetic disk plan and displayed the blocked export finding, policy 0.8.0, JSON digest and no-approval guidance. The user's tab was preserved. No cloud read, plan execution or deployment was performed.
- These rules inspect declared plan values only. Effective permissions/connectivity, disk encryption, backup/recovery, private endpoint correctness and complete resource policy coverage remain unverified.

## Azure data disk access checkpoint

- The default suite passes 1,380 tests with 227 optional/native/platform cases skipped. Ruff checks and formatting pass across 81 Python files; JavaScript syntax passes.
- Linux and Windows generation tests verify empty managed data disks deny remote import/export and disable public network access while retaining their VM attachment and existing external-secret requirements.
- Four separately enabled Linux/Windows regional/zone-2 configurations pass Terraform validation and TFLint against AzureRM 4.81. Versioned AzureRM 4.0 documentation confirms both access attributes are supported by the existing Linux provider floor.
- No cloud resources were created. OS disk access, guest encryption, backup/recovery, private endpoints and export workflows remain outside this change; local plan policy does not yet check these disk access attributes.

## Azure zone metadata checkpoint

- The default suite passes 1,378 tests with 227 optional/native/platform cases skipped. Ruff checks/formatting pass across 81 Python files; JavaScript syntax passes.
- Twenty-nine mocked zone-read cases cover Linux/Windows supported, absent, unknown, malformed and duplicate SKU location/zone metadata, regional defaults, preserved restrictions, CLI failure exits and private-value omission. Zone checking uses the same two explicitly opted-in target/size reads; no extra cloud call is added.
- A listed zone establishes only the CLI-reported VM SKU metadata result. Capacity, quotas, disk/NAT/public-IP zone support, provider credential equivalence and successful allocation remain unverified. No real cloud read, deployment or approval was performed.

## Azure standalone placement checkpoint

- The default suite passes 1,349 tests with 227 optional/native/platform cases skipped. Ruff checks/formatting and JavaScript syntax checks pass.
- Eighteen new regression cases cover Linux/Windows regional and zone 1–3 answers, matching VM/data-disk/NAT/public-IP placement, API generation/import preservation, invalid choices, defaults and exclusion from other Azure recipes.
- Four separately enabled Linux/Windows regional/zone-2 cases pass Terraform validation and TFLint against AzureRM 4.81, including data disks and inbound public IPs. Versioned AzureRM 4.0 documentation confirms the existing Linux provider floor supports these zone arguments.
- A temporary browser tab imported an Azure Windows project, displayed the regional default in Cloud target, selected zone 2 and generated files successfully. The resulting summary retained zone 2; the user's tab was preserved.
- These checks do not establish regional/SKU/network zone support, account capacity, successful deployment, failover or replacement/data recovery. The current size preflight does not confirm zone availability.

## Terminal question guidance checkpoint

- The CLI/project/Azure Windows regression run passes 89 cases. Removing a duplicate description print preserves the existing per-question guidance and external-secret handling. Ruff checks and formatting pass across 79 Python files after normalizing edited source files.

## Regular file input checkpoint

- The default suite passes 1,331 tests with 223 optional/native/platform cases skipped. Ruff checks and formatting pass across 79 Python files.
- Reader tests verify exact bytes, bounded overflow reads, invalid limits, directory rejection, a nonregular descriptor after opening and private-value-free CLI failures. Three POSIX named-pipe tests are skipped on this Windows host; they cover rejection before open and a regular-file-to-pipe substitution using nonblocking open.
- Existing specification/plan byte limits remain enforced by their parsers. These checks do not authenticate files, create immutable snapshots, protect against every concurrent filesystem change or read cloud credentials.

## GCP host lifecycle checkpoint

- The default suite passes 1,321 tests with 220 optional native cases skipped. Seventeen new cases verify standard Linux/Windows scheduling bindings, imported API answers, backwards-compatible defaults, strict enum/boolean rejection and exclusion from web-server/tier input contracts.
- Four separately enabled Linux/Windows migration/termination combinations pass native Terraform validation and TFLint against the initialized Google 7.46.1 provider. Both automatic-restart choices are covered; these checks create no cloud resources.
- A temporary browser tab imported a GCP Windows project, displayed MIGRATE and enabled restart defaults in Operations and identity, selected TERMINATE/disabled restart, and generated files successfully. The resulting choice summary retained both answers. The user's tab was preserved.
- Host event execution, recovery timing, guest/application health and selected machine compatibility remain unverified. These choices do not add guest patch schedules, automatic stopping for Terraform updates, Spot instances or deployment approval.

## Administrator access guidance checkpoint

- Network-input, plan-review and AWS/Azure/GCP Windows regression tests pass 234 cases with one optional native case skipped. Existing input acceptance and policy decisions are unchanged; question descriptions explain that a public `/32` accepted for generation remains blocked by local administrator-access policy.
- Generation still does not approve deployment or establish a private routed access path.

## Terminal workload guidance checkpoint

- The CLI/artifact regression run passes 38 cases with two Unix permission cases skipped on Windows. Linux and Windows VM questionnaire tests generate real project files and verify routed-access guidance without a claim that the VM serves HTTP. The existing web-server test retains HTTP/TLS guidance.
- This adjusts questionnaire language only; it does not install guest applications, provide a private access path or verify cloud connectivity.

## Artifact recovery checkpoint

- The default suite passes 1,302 tests with 216 optional native cases skipped. Ruff checks and formatting pass across 76 Python files.
- Failure-injection tests cover write errors and keyboard interruption, continued cleanup after a denied removal, preservation of unrelated files, refusal to regenerate over leftover Terraform, and a nonzero CLI error identifying only leftover filenames. The original exception remains the internal cause; its details are absent from console output.
- These checks establish handled-failure behavior, not crash atomicity, power-loss durability, Windows ACL privacy or protection from concurrent filesystem changes. No Terraform, cloud or AI execution behavior changes.

## Azure Windows assessment checkpoint

- The default suite passes 1,298 tests with 216 optional native cases skipped. Ruff checks/formatting and JavaScript syntax checks pass.
- Four native Azure Windows public/private and Secure Boot combinations pass provider validation and lint with platform assessment enabled in public cases and image defaults in private cases. OS update installation and the enabled VM Agent are retained.
- A temporary browser tab verified the assessment checkbox defaults off in Operations and identity. Enabling it and generating files produced the success notice and a true Terraform variable default; zero password fields were rendered.
- These checks do not verify guest-agent health, image support in an account, assessment execution, installation or maintenance schedules. Custom Windows patch schedules and hotpatching remain outside the recipe.
- The preceding provider floor checkpoint passed [all CI jobs](https://github.com/chriswayneh/TerraForma-IaC/actions/runs/37593906691).

## Azure Windows provider floor checkpoint

The Windows/provider generator regression run passes 93 cases with 208 optional native cases skipped. A separately initialized AzureRM 4.81 workspace passes Terraform validation and TFLint with the new Windows provider constraint. Official versioned provider documentation confirms the older 4.0 automatic-update argument name differs; non-Windows Azure constraints remain unchanged. Native test configuration files explicitly use UTF-8.

## Grouped questionnaire checkpoint

- Web/project regression checks pass 76 cases; JavaScript syntax and patch whitespace checks pass.
- A temporary browser tab imported Windows examples for AWS, Azure and GCP. The form retained all 23, 24 and 20 respective questions in five labeled sections, displayed previews, rendered zero password fields and showed no horizontal document overflow at the tested desktop viewport. An example GCP Windows form also retained its generated Windows image preview after generation.
- Sections remain expanded; required controls are not concealed behind collapsed panels. Conditional fields and saved specification semantics are unchanged. Mobile layout and additional catalog workflows retain their prior coverage and were not rechecked for this layout change.

## Azure disk caching development checkpoint

A temporary browser tab verified cache defaults, hidden data cache questions before disk selection, and complete Azure Windows external-secret/state guidance before generation. It rendered zero password fields. The reference-only credential screenshot is published in the Windows guide; the user's existing tab was preserved.

- The default suite passes 1,295 tests with 216 optional native cases skipped; Ruff checks and formatting pass across 76 Python files.
- Sixteen cache-input cases cover Azure Linux/Windows generated bindings, preserved specification values, accepted modes, malformed answers, defaults and inactive-disk rejection. Seven enabled native cases pass: three cache modes plus four Windows public/private and Secure Boot combinations.
- The existing cache defaults are retained. Tests do not verify cached I/O performance, VM/disk support in an account, guest flush behavior, safe cache changes or recovery.
- The Azure Windows and terminal guidance checkpoints passed all GitHub Actions jobs: [Azure Windows](https://github.com/chriswayneh/TerraForma-IaC/actions/runs/37590641781), [terminal guidance](https://github.com/chriswayneh/TerraForma-IaC/actions/runs/37590963794).

## Azure Windows VM development checkpoint

The subsequent terminal guidance change passes 142 CLI/project/Windows regression cases and targeted Ruff checks. Field descriptions come from the existing shared input contract; hidden conditional inputs and external secret references retain their existing behavior.

- The default suite passes 1,279 tests with 213 optional native cases skipped. Ruff checks and formatting pass across 75 Python files; browser JavaScript syntax checks pass.
- Four separately enabled Terraform/provider and TFLint cases pass for Azure Windows public/private networking and both Secure Boot settings, with an optional data disk. These are structural checks without cloud authentication or deployment.
- Generation, terminal, API and ZIP round-trip cases verify that only `TF_VAR_admin_password` is recorded. An environment marker never appears in generated files or responses; no password input is rendered. Windows username/computer-name limits, boot disk minimum and unsupported answers fail closed.
- Policy `0.7.0` covers Azure Windows Secure Boot/vTPM disabling, removal, missing controls and malformed values. Reports retain partial coverage and never grant deployment approval. Mocked SKU metadata checks cover Gen2 compatibility and unknown/incompatible responses.
- A rebuilt installed wheel verifies the 18-entry catalog, Azure Windows generation and bundled updated introduction/questionnaire labels. A temporary browser tab imports an example Azure Windows specification and verifies 128 GiB boot and Standard_D2s_v5 defaults, separate computer naming and external password/state guidance.
- Current GitHub screenshots containing the former introduction were recaptured from the workspace. The wording checkpoint passed [all CI jobs](https://github.com/chriswayneh/TerraForma-IaC/actions/runs/37590039941).
- Cloud creation, marketplace availability, password acceptance, RDP access, licensing activation, update completion, BitLocker recovery and teardown remain unverified. Protected backend configuration and managed plan/apply remain planned.

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

- Explicit Azure environment tags pass 20 workload/access/encryption coverage cases, 20 native Azure configurations and installed-wheel checks across all five workloads. Native provider schema checks confirm tag support on private DNS, compute, storage and gateway resources. Cloud inventory and billing attribution were not queried.

- The provider-module refactor retains exact generated file bytes and input constraints for all 60 provider/workload/access/encryption combinations, checked before and after extraction and again from the installed wheel. Existing generator imports remain available. The local suite passes 1,154 tests with 201 optional native cases skipped; earlier native checks remain recorded separately.

- AWS gp3 tuning passes 37 contract/ratio/type/scope/export/import cases, four native disk-class/enable combinations and 14 cloud-free Terraform plan cases for IOPS and throughput relationships. Terminal validation is also exercised while collecting answers. Included baselines and template limits are explicit; cloud performance, instance EBS limits and billing were not measured.

- Optional fixed private VM addresses pass 56 subnet/format/export/import/scope/browser-hint/terminal cases, six native provider/access configurations and 24 cloud-free Terraform plan cases for usable, reserved, missing and out-of-subnet values. Browser and CLI show usable ranges; browser-hint checks use optional Node.js. No address availability, independent reservation or cloud provisioning was checked.

- Azure encryption-at-host size metadata checks pass 18 supported/unsupported/missing/malformed/opt-out/API/CLI cases across standalone VMs and both web-tier recipes. These use mocked SKU responses and add no cloud request. Subscription feature registration and actual deployment remain unverified.

- Optional Azure accelerated networking passes 16 contract/export/import/capability/API/CLI cases and four native OS/setting combinations. The shared size preflight reports support only when requested; missing, incompatible and malformed metadata remain visible. Guest drivers, capacity, cloud deployment and stop/deallocation operations were not exercised.

- Managed command cleanup passes controlled child/grandchild tests for normal exit, timeout and output overflow on Windows, plus short commands, launch failure and attachment failure. The full local suite passes 1,027 tests with 149 native cases skipped. Windows uses the launched process's retained handle rather than reopening its PID. The Windows launch/attachment gap and detached POSIX children remain outside cleanup guarantees; this is not an untrusted-code sandbox.

- Standalone VM reference outputs pass 15 provider/workload-scope checks and 12 native provider/access/encryption combinations. The installed wheel exports the correct definitions across all providers. No live resource IDs were retrieved and no cloud operation was authorized.

- Policy `0.6.0` adds 42 GCP serial-console cases for instances/templates, documented boolean spellings, inheritance gaps, removed disable settings and malformed before/after values. The installed CLI blocks enabled access and retains `approval_granted: false`. Cloud access and project/organization metadata are not queried.

- Explicit GCP serial-console defaults pass eight workload/access/provider-boundary cases and all 20 native GCP recipe/access/encryption combinations. The installed wheel retains OS Login and web startup behavior. Effective project/organization metadata and cloud access remain unverified.

- Native image-resolution regression checks now include the default version variable and three exact GCP publisher/name resolution cases. This corrects a native CI fixture failure after pinning was added; the generated expressions resolve locally without cloud reads.

- AWS pins pass 13 owner/filter/format/export/import cases and six native OS/workload combinations. The terminal questionnaire and installed wheel preserve an exact ID; generated lookups retain publisher/OS/HVM constraints and an explicit x86_64 filter. Example AMI IDs are illustrative and were not queried against AWS.

- GCP pins pass 13 input/export/import cases, six native OS/workload combinations and three Terraform-only plan cases exercising the generated OS-match precondition without cloud providers or apply. The installed wheel preserves a named pin and rejects a mismatched OS. Native example names do not establish current image availability or integrity.

- Azure marketplace version inputs pass 19 format/contract/export/import cases and six native image/workload combinations. Native pin examples use a syntactically valid illustrative version, without asserting that version exists. The rebuilt installed CLI preserves the exact version and Canonical publisher. Cloud availability and image integrity remain unverified.

- Twenty mocked Azure boot metadata cases cover reported Gen2 support, Trusted Launch exclusion, missing/malformed/duplicate capabilities, retained vTPM when Secure Boot is off, and API/CLI reporting. The installed wheel confirms supported and unsupported SKU responses with exactly two mocked reads. Live cloud support and image compatibility remain unverified.

- Optional Azure-managed boot diagnostics pass 12 input/export/import/default/privacy-guidance cases and 16 native image/access/boot-control/diagnostics combinations. A rebuilt installed wheel generates both choices through the local API. Actual cloud capture, permissions, retention and retrieval remain unverified.

- Policy `0.5.0` adds 26 Azure Linux VM boot-control cases covering disabled, removed, missing and malformed before/after values, partial coverage and CLI failure status. Reports continue to grant no provisioning approval.

- Azure Trusted Launch controls pass 12 added contract/export/import tests and eight native Terraform/TFLint combinations covering both supported Ubuntu images, public/private access and Secure Boot choices. Browser generation confirms the default, explicit choice and generated settings. These are structural checks; no Azure deployment or guest attestation was performed.

- The latest local suite passes 1,018 tests with 149 optional/native/platform cases skipped. Shared JSON tests cover duplicate keys, non-finite constants/overflow, UTF-8 boundaries, 64-level nesting and rejection before tool calls; malformed AI diagnostics use mocked HTTP only. A Python 3.14 Linux CI difference prompted an explicit nesting bound, verified by the [corrected checkpoint](https://github.com/chriswayneh/TerraForma-IaC/actions/runs/37576328490).
- Thirty-eight mocked VM metadata tests cover separate consent, matching-target prerequisites, provider-scoped reads, reported architecture, Azure restrictions, GCP deprecation, malformed responses, command failures, CLI statuses and API boundaries. Browser checks cover both compatible and incompatible results, consent reset and removal of stale results after edits. No live cloud reads were performed; capacity, quotas, images and provisioning remain unverified.
- Eight additional native GCP cases cover both supported images, public/private access and Secure Boot on/off. Terraform validation and TFLint pass; no cloud resource creation was performed. Browser checks show the default enabled control, generated Shielded VM block and choice summary; API and installed-wheel checks verify export/import preservation. [Boot-control CI](https://github.com/chriswayneh/TerraForma-IaC/actions/runs/37576365068) and [policy CI](https://github.com/chriswayneh/TerraForma-IaC/actions/runs/37576473071) passed all jobs.
- Generated ignore rules were checked using Git itself: common private state/plan/variable/credential files are excluded, while Terraform source, manifests, receipts and provider lock files remain visible. Existing ignore files are preserved. Installed-wheel generation, ZIP checksums and receipt verification pass.

- Thirteen API tests cover provider target results, strict consent, token/origin/body limits, and a shared native-tool slot for validation and preflight while session reads and offline compilation remain available. Browser checks with mocked cloud responses confirm default-disabled controls, matching/mismatched results, consent reset, and removal of stale results after edits. A rebuilt isolated installed wheel passes packaged consent controls and offline/mocked opt-in API flows. The current local preview also shows default-disabled consent controls without a cloud call. No live cloud CLI calls were made during browser verification.

- Thirty-four mocked cloud-target preflight tests cover all providers, offline/explicit opt-in, target mismatch, non-ready states, malformed/ambiguous responses, bounded command failures, missing tools, timeout limits, CLI exit statuses and value privacy. The rebuilt isolated installed wheel passes all three offline and mocked opt-in CLI flows. No live authentication or cloud account read was performed; target/resource permissions and credential equivalence remain unverified in a real account.

- Eight added receipt checks cover inconsistent canonical digests/template versions, malformed or ambiguous questionnaire metadata despite matching file hashes, key-order/whitespace equivalence, CLI failure status and value privacy. The rebuilt isolated installed wheel confirms an intact comparison and CLI exit `1` for a conflicting canonical digest. Comparison remains unsigned and does not authorize deployment.

- Terminal output uses exclusive file creation with mode `0600` and new leaf directories with mode `0700`. Existing overwrite and rollback tests pass on Windows. The rebuilt isolated installed wheel generates an intact receipt and refuses overwrites. Two added Unix CI tests verify private modes under a permissive umask and preservation of existing directory permissions; they are skipped on Windows. Download/extraction permissions and cross-version Windows ACL privacy are not established by these checks.

- Ten local readiness tests cover missing native/web/base dependencies, unsupported Python, selected-capability exit status, JSON/text reports and omission of private environment values and discovered paths. The rebuilt isolated installed wheel confirms web availability, validation exit `1` with missing tools, and generation remaining available. The command discovers package metadata and PATH only; it does not run tools or establish executable trust, cloud identity or provider readiness.

- Optional workload identity checks cover enabled/disabled AWS profiles, Azure managed identities and GCP user-managed service accounts, conditional required references, malformed/credential-shaped values, terminal collection, resource guides and ZIP import/export. Six added provider cases pass native validation/TFLint; two native console cases enforce the required-reference condition. The full generator run passes 166 tests, and a focused identity/username rerun passes after correcting literal-hyphen patterns.
- Browser checks confirm reference visibility, required-field focus, disabled exports omitting inactive values, enabled ZIP/import preservation, AWS/GCP format checks and Azure principal output. Corrected HTML patterns reject invalid project/environment/username/identity values and accept supported hyphenated identifiers. A rebuilt isolated installed wheel passes all three identity export/import flows and conditional missing-reference errors. Identity existence, pass-role/act-as authorization, IAM/RBAC permissions and live provisioning remain unverified.
- VM network-range tests cover all three private address families, provider-specific prefix bounds, canonical network notation, rejection of public/reserved/IPv6 inputs, and export/import preservation. All 60 recipe combinations, 16 data-disk cases and nine selected network cases pass native validation/TFLint. Three additional native console checks confirm Terraform conditions match shared validation for accepted/rejected ranges. Browser checks confirm field focus on invalid input, correction, ZIP export and import; the isolated installed wheel retains the selected range and summary. Overlap with existing networks and live connectivity remain unverified.
- Policy version `0.3.0` adds 23 cases covering metadata endpoint/token combinations, missing/malformed settings, attached identity review gaps and value privacy. The browser and rebuilt isolated installed CLI show the metadata block, permission gap, policy version and digest without private values; CLI exits `1`. The browser and packaged UI also show the updated infrastructure-requirements introduction.
- Policy version `0.2.0` tests cover enabled, disabled, unresolved and malformed AWS/GCP VM protection controls, protection removal, and forced AWS disk detach. Browser and rebuilt installed-CLI checks show both lifecycle blocks, exit `1`, the policy version and digest, while omitting private resource keys and raw values. No plan or apply was executed.
- 676 local unit/API/generator/guidance/plan-review tests pass, including shared specifications, input contracts, numeric bounds, export/import preservation, terminal input collection, recipe capability metadata, SSH key structure/type checks, browser plan-review route limits/privacy/concurrency, explicit AWS account constraints, environment-label mapping, artifact receipts/comparisons, clean-destination/rollback safeguards, diagnostic control-character handling, database client-network restrictions, configured tier capacity, supported Linux image inputs, safe field-level feedback, standalone VM access/export contracts, Azure administrator usernames, strict EC2 monitoring boolean answers, bounded native command output, AWS/GCP VM deletion protection, read-only configuration summaries, and conditional data disk questions.
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

## AWS Windows VM development checkpoint

- The Windows Server 2022 recipe covers public/private access and encryption combinations, restricted RDP, trusted Amazon image filters and optional exact AMI pins, RSA-only public-key validation, disk defaults, gp3 ratios and private-address guards.
- Generation/export tests verify that no administrator password, private key, password retrieval argument or credential output is introduced. API guidance and catalog metadata describe external EC2 password recovery and retain unverified deployment status.
- Native Terraform 1.14.0 provider validation and TFLint 0.61.0 pass all four public/private and encryption combinations with an optional data disk. CI includes the same native cases.
- A temporary browser tab completed AWS Windows generation, showed the RSA recovery question and 50 GiB boot default, and confirmed that switching to Azure hides Windows and selects Linux. The user's existing tab was preserved.
- These checks do not establish cloud availability, creation, password recovery, RDP access or teardown. Azure/GCP Windows recipes remain planned.

The AWS Windows checkpoint passes 1,198 local tests (205 optional native cases skipped in the default run), Ruff checks across 73 Python files, JavaScript syntax checks and four separately enabled native provider/lint cases. An installed-wheel smoke verifies Windows generation, bundled UI assets and the 16-entry catalog. Target metadata tests use mocked responses, and the terminal questionnaire resolves required public-key/account inputs without collecting a password.

## Google Cloud Windows VM development checkpoint

- The default suite passes 1,231 tests (209 optional native cases skipped). Two additional terminal and ZIP export/import tests pass separately, preserving the requested non-secret username and required project inputs. Ruff covers 74 Python files; JavaScript syntax checks pass.
- Four enabled native provider/lint cases cover public/private networking and both Secure Boot settings with an optional data disk. Trusted windows-cloud family selection, restricted RDP, Private Google Access, activation routing/TCP 1688, vTPM/integrity monitoring and serial-console disablement are generated explicitly.
- An installed wheel verifies GCP Windows generation, bundled assets and the 17-entry catalog. A temporary browser tab completed GCP Windows generation, showed 64 GiB and e2-standard-2 defaults, and explained external account/password setup without collecting credentials.
- Cloud creation, licensing activation, guest readiness, password setup, RDP access, BitLocker recovery and teardown remain unverified. Exact GCP Windows image pins and Azure Windows generation remain planned. The username output does not create a guest account.
- The preceding AWS Windows checkpoint passed all GitHub Actions jobs: [workflow run](https://github.com/chriswayneh/TerraForma-IaC/actions/runs/37585313510).
