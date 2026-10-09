# Verification record

## Documentation CI and source verification — v0.4.0 development checkpoint

- The committed local inline-documentation link checker passes across all 43 tracked Markdown files. Three subprocess tests in isolated local Git repositories verify valid/encoded/spaced references, broken screenshot reporting without exposing the target value, and rejection of an existing file outside the repository. No external URL or heading-anchor verification is claimed.
- GitHub's Linux/Windows Python matrix now runs this check and includes the script in Ruff checks/formatting. No package runtime, generated Terraform or UI behavior changes in this checkpoint; previously recorded native/package results remain historical evidence for their exact source checkpoints.
- Architecture-guard commit cc9a520/run 37871056118 now passes all six GitHub jobs, including native validation. Readiness-audit run 37871647916 remained in progress with five successful jobs when inspected. This checkpoint's CI is not yet verified. Live creation, guest access, initialization and cleanup still require dedicated-account evidence; v0.3.0 remains the latest release.

## Machine architecture guards — v0.4.0 development checkpoint

- The full default suite passes 2,917 tests with 535 optional/native/platform cases skipped. Subsequently added CLI cases and expanded NVIDIA Grace/Azure case-variant coverage pass in the final focused set: 176 architecture/CPU-credit/Terragrunt tests, with 29 optional cases skipped. These later cases are not included in the full-suite count.
- Six catalog Linux/Windows configurations pass Terraform 1.14.0 validation and TFLint 0.61.0. Forty additional Terraform test runs use only generated size variables and `command = plan`, with no provider or resource declarations: all recognized Arm overrides fail at variable validation, while x86 examples and unknown identifiers pass this limited guard. Passing does not establish provider compatibility or availability.
- Shared input validation rejects recognized Arm families for catalog/custom image recipes, identifies the invalid field without repeating its value, prevents terminal file writes, and rejects browser compile/import and Terragrunt export. Native Terraform validation uses the same patterns; Azure case variants cannot bypass the naming guard. Primary provider references and snapshot limitations appear in [machine architecture checks](MACHINE_ARCHITECTURE.md).
- Ruff checks/formatting pass across 136 Python files; local links pass across 42 Markdown files. The development wheel is 167,876 bytes, SHA-256 `68249c034f75b1f59d1d526312c2fd5bc5365425d62ffb9ef4fd260857ffb264`. An isolated installation with existing dependencies passes 27 offline imports/UI-route checks and 190 architecture/Terragrunt/combined-input tests, with 51 optional cases skipped.
- Advanced-disclosure commit 75f9a34/run 37869375653 now passes all six GitHub jobs. The preceding Terragrunt/T8i run 37870504698 was still in progress when inspected; this checkpoint's CI has not yet been verified. No new release or live acceptance is claimed. Dedicated-account creation, guest access, initialization and cleanup remain pending.

## Optional Terragrunt export and T8i credits — v0.4.0 development checkpoint

- The default suite passes 2,822 tests with 520 optional/native/platform cases skipped. A subsequent writer failure-recovery test passes, preserving existing user files and removing only owned partial output. Six subsequently added native Terragrunt tests pass separately; they are not included in the default-suite count.
- Terragrunt 1.1.6, downloaded from its official release and checked against its published SHA256SUMS, evaluates all six combined provider/OS exports. Effective inputs match the compiled project exactly, including literal initialization-script interpolation. Local module references resolve; no remote state, dependencies or hooks are configured. All 30 exporter tests pass with native checks enabled. No cloud, plan, apply or destroy command runs in these checks.
- Matching recipes share local modules; environment answers remain separate. New output directories are required. Paths and reserved device names are rejected, external secret references remain external, and generated checksums cover exported text. This is local export support, not completion of the multi-environment automation phase. Backend configuration and live acceptance remain pending.
- The preceding T8i change passes twelve Linux/Windows × tenancy × CPU-credit-mode Terraform 1.14.0/TFLint 0.61.0 checks and six provider-mocked plan runs. Four additional terminal input cases pass. Shared family-prefix validation now includes documented T8i support; synthetic `t8i.small` inputs do not establish actual SKU or regional availability.
- Ruff checks and formatting pass across 134 Python files; local links pass across 41 Markdown files. The final development wheel is 166,739 bytes, SHA-256 `092ec7268d113b0ffdcf3501a8cfe6cd4dbf878417717d7a24cbd27188e59bcf`. An isolated installation using existing runtime dependencies passes 27 offline imports/UI-route checks and 118 exporter/CPU-credit/combined-VM tests, with 56 optional cases skipped.
- Prior tenancy commit 8899f09/run 37868363894 and combined-matrix commit 6915827/run 37868692011 have completed successfully. Advanced-disclosure run 37869375653 remained running when checked. This checkpoint's GitHub CI result is not yet claimed. v0.3.0 remains the latest release; no live creation, login, guest execution or cleanup evidence is claimed.

## Advanced VM disclosure — v0.4.0 development checkpoint

- The full default suite passes 2,791 tests with 506 optional/native/platform cases skipped. Ruff checks and formatting pass across 132 Python files; JavaScript syntax passes. No provider, contract or Terraform output changed, so the prior combined native/plan evidence remains applicable.
- Browser checks across AWS/Azure/GCP confirm default operations/identity sections are closed and non-default imported settings open. Deletion protection and Secure Boot remain visible. AWS monitoring survives generation while collapsed; an incomplete identity input reopens and focuses for correction. Keyboard Enter toggles the disclosure. All fixtures are synthetic; no cloud check was submitted.
- The [screenshot](images/vm-advanced-options.png) shows the visible protection controls, collapsed section and persistent default notice. Initialization controls and their review behavior remain outside the advanced section.
- The final isolated development wheel is 163,722 bytes, SHA-256 e1099aeb30ddad0b4d5a93142f84112aa0b337b4a6d4fc4aa79f485acd1d9795. Its installation passes 27 offline imports/bundled UI checks and 138 combined-input/web/initialization regressions using existing dependencies. Packaged JavaScript and CSS exactly match the browser-verified source.
- Earlier guidance 57e2e5e/run 37867691252 and VM documentation d2bd5df/run 37867782164 now pass all six GitHub jobs. Tenancy 8899f09/run 37868363894 remains running; advanced-disclosure CI has not yet run. No new release or live acceptance is claimed.

## Combined network/tenancy inputs — v0.4.0 development checkpoint

- Thirty-six combined provider/OS/public-private/network configurations pass Terraform 1.14.0 validation and TFLint 0.61.0. Custom images, identity, data disks, labels and reviewed initialization are enabled together; new networks exercise both outbound profiles and AWS cases request Dedicated Instance tenancy.
- All 36 offline saved-project/export/import cases pass, checking every supplied value's generated default, required-variable completeness, external secrets, exact file content and the existing 48-input bound. Eighteen terminal cases also pass, verifying the same combined answers and exact reviewed local script content without invoking cloud/guest commands.
- All 54 offline cases pass against the isolated tenancy wheel installation using existing runtime dependencies. No package/runtime code changed; the previously recorded 163,414-byte wheel and its digest remain applicable. Ruff checks/formatting and local documentation links pass. No additional full-suite result is claimed for this test-only checkpoint.
- Outbound checkpoint 1d1a76d/run 37867379798 now passes all six GitHub jobs, including native validation. Later guidance, documentation and tenancy runs remain unverified as complete at this checkpoint.
- Live policy, tenancy, guest execution, creation, login and cleanup remain pending dedicated-account evidence. v0.3.0 remains the latest release.

## AWS hardware tenancy — v0.4.0 development checkpoint

- The full default suite passes 2,757 tests with 494 optional/native/platform cases skipped. Four subsequent terminal/offline-preflight cases pass. Both OS families and new/existing networks preserve tenancy answers through generation/import; invalid host and other unsupported values are rejected.
- All eight Linux/Windows × new/existing-network × unmanaged/dedicated configurations pass Terraform 1.14.0 validation and TFLint 0.61.0. Two provider-mocked plan runs verify requested dedicated tenancy. Structural assertions establish that no host ID, host resource group or Dedicated Host resource is requested; provider-computed host values are not treated as known during plan.
- Ruff checks and formatting pass across 132 Python files; JavaScript syntax passes. The isolated development wheel is 163,414 bytes, SHA-256 32737bcab6b70ddf73b1e88ceeff4282d54ac97bff5d1cd40739bacb1c061fd5. Its installation passes 27 offline fixture/bundled-UI checks and 116 tenancy/credit/existing-network/preflight regressions using existing runtime dependencies.
- The browser [resource guide](images/aws-tenancy-guide.png) shows dedicated costs and unverified compatibility using synthetic inputs. No cloud preflight, provisioning, credential/state read, guest command or AI request was performed.
- Outbound 1d1a76d/run 37867379798 and guidance 57e2e5e/run 37867691252 have five completed successful jobs and native validation still running at this checkpoint. Tenancy CI has not yet run. No new CI completion or release is claimed.
- Effective tenancy, supported size/region, capacity, licensing, creation, access, changes and cleanup remain pending dedicated-account evidence. v0.3.0 remains the latest release.

## Outbound guidance — v0.4.0 development checkpoint

- The full default suite passes 2,731 tests with 484 optional/native/platform cases skipped. Six subsequent capability-metadata cases also pass. The resource guide and CLI explain the selected profile and its limits; existing-network guidance makes no claim of unrestricted effective access.
- Ruff checks and formatting pass across 130 Python files. Terraform output is unchanged from the outbound checkpoint, whose 24 native profile combinations, 24 combined-input configurations and provider-mocked plans remain applicable.
- The updated development wheel is 162,120 bytes, SHA-256 a7fa8ea36c21dfe78b27008042a520d4b09748f50570e902e28328100dd7f407. Its isolated installation passes 27 offline imports/bundled UI checks and 120 profile/IAP/catalog regressions using existing runtime dependencies.
- Browser verification confirms the selected profile's [generated guide](images/vm-outbound-guide.png). All inputs are synthetic; no cloud check or deployment was requested. Outbound checkpoint 1d1a76d/run 37867379798 was still running when this record was written; no new CI success or release is claimed.
- Live effective policy, creation, access and cleanup remain pending. v0.3.0 remains the latest release.

## Outbound VM profiles — v0.4.0 development checkpoint

- The full default suite passes 2,706 tests with 484 optional/native/platform cases skipped. Twelve subsequent terminal-questionnaire cases also pass, checking Linux/Windows and new/existing networks across all three providers. Ruff checks and formatting pass across 130 Python files; JavaScript syntax passes.
- Both profiles pass Terraform 1.14.0 validation and TFLint 0.61.0 in 24 provider/OS/public-private configurations. Twenty-four combined custom-image/identity/disk/initialization/new-existing-network regressions also pass native validation and lint.
- Twelve provider-mocked plan runs verify restricted ports, ordered denies, Windows licensing exceptions and unchanged unrestricted defaults. The six existing-GCP-network mocked plan runs also pass, including zero management of both new outbound firewall resources. All mock runs use plan only, without cloud operations.
- Browser verification confirms restricted-profile generation and hiding the control for existing networks. The [questionnaire screenshot](images/vm-outbound-profile.png) uses synthetic inputs. The development wheel is 161,644 bytes, SHA-256 56945215bbe9dde1a278a27c46023e02320360139acc7778779bb212dcfbe70a. Its isolated installation passes 27 saved-project imports and bundled UI checks plus 93 offline regressions using existing runtime dependencies.
- Earlier image preflight fcde04b/run 37865305438, AWS boot-mode 1e350db/run 37865801762 and GCP firmware 93917cb/run 37866074935 each pass all six GitHub jobs. Outbound checkpoint CI has not yet been run at the time of this record.
- Effective egress policy, guest updates/activation, creation, login and cleanup remain pending dedicated-account testing. No live operations, credential/state reads or guest execution were performed. v0.3.0 remains the latest release.

## GCP image firmware — v0.4.0 development checkpoint

- The full default suite passes 2,652 tests with 454 optional/native/platform cases skipped. Twenty-nine additional mocked cases cover Linux/Windows, catalog/custom images, Secure Boot on/off, declared/missing UEFI support, malformed/duplicate features and web-recipe scope. All metadata responses are synthetic; no cloud CLI was invoked.
- Ruff checks/formatting pass across 127 Python files; JavaScript syntax and 38 tracked Markdown local-link checks pass. This feature adds no provider command and changes no Terraform configuration. Existing vTPM/integrity-monitoring requirements cannot be bypassed by disabling Secure Boot.
- The development wheel is 159,593 bytes, SHA-256 0b592d684c58c3544425139342bed125f37d5ad968a4f336c389e44e9c90aec7. Its isolated installation passes all 160 image/firmware mocked regressions plus 27 offline imports/bundled-UI checks using existing runtime dependencies.
- Image checkpoint fcde04b/run 37865305438 and boot-mode checkpoint 1e350db/run 37865801762 were still running when this record was written. The prior 1f2d2a9 checkpoint passes all six jobs. No new CI success or release is claimed.
- Live cloud image reads, signing/guest-agent behavior, boot/execution, creation/access/cleanup and v0.4.0 acceptance remain pending. v0.3.0 remains the latest release.

## AWS image/VM boot mode — v0.4.0 development checkpoint

- The full default suite passes 2,623 tests with 454 optional/native/platform cases skipped. Thirty-six additional mocked regressions verify Linux/Windows UEFI, Legacy BIOS, preferred-mode fallback, documented x86 defaults, missing/malformed capabilities, independent consent and CLI/API mismatch reporting. No additional cloud command is introduced.
- Ruff checks/formatting pass across 126 Python files; JavaScript syntax passes. Terraform output remains unchanged. An isolated local mock server verifies the browser warning, with an explicit synthetic-test notice in the screenshot. The temporary server/tab were closed; the normal preview was restarted with current code and an empty questionnaire.
- The development wheel is 159,466 bytes, SHA-256 817a13fc848e1e7098b3b034357461ef3d65bd7f94163a50132ef3f251b02739. Its isolated installation passes 131 image/boot-mode mocked regressions and 27 offline imports/bundled-UI checks using existing runtime dependencies. No release was published.
- Cloud reads, guest boot/execution, live creation/access/cleanup and v0.4.0 acceptance remain unverified. The image checkpoint fcde04b is pushed; its CI was still running when this entry was written. v0.3.0 remains the latest release.

## Image metadata preflight — v0.4.0 development checkpoint

- The full default suite passes 2,587 tests with 454 optional/native/platform cases skipped. Ninety-five image regressions cover provider/OS/catalog/custom sources, explicit consent, pins, incompatible/missing/malformed fields, ambiguous records, private diagnostics and combined bounded read budgets. All provider responses are synthetic mocks; no cloud CLI was invoked.
- Ruff checks and formatting pass across 125 Python files. JavaScript syntax and local documentation links pass. Generated Terraform is unchanged by this read-only feature; this checkpoint does not add live or native provisioning evidence.
- Browser verification confirms all cloud consent controls start off, image consent alone cannot enable a target check, and changing the questionnaire clears image consent and the stale preview. The screenshot uses a synthetic project; no cloud check was submitted.
- The development wheel is 158,400 bytes, SHA-256 da83e6dd6bf1228ad2d59b956a665b92c83cb451bdf5124e77b8aec07fabf9d2. An isolated installation passes all 95 mocked image regressions and 27 offline project imports/bundled-UI checks using existing runtime dependencies. Initial local building without build isolation failed because setuptools was absent; the normal isolated build succeeded. This is not a release asset or fresh runtime dependency-resolution test.
- Previous checkpoint 1f2d2a9 passes all six GitHub CI jobs in run 37863555733. The image checkpoint's CI remains unverified until its own run completes.
- v0.3.0 remains the latest release. v0.4.0 dedicated-account creation, login, guest execution and cleanup gates remain pending; the user has requested offline development without provider accounts.

## Restored script review — v0.4.0 development checkpoint

- The full default suite passes 2,492 tests with 454 optional/native/platform cases skipped. Twelve provider/OS LF/CRLF API cases preserve exact script text and safe summaries; six are additional regressions. Ruff checks/formatting pass across 122 Python files; JavaScript syntax passes.
- Browser restoration of a synthetic CRLF script normalizes displayed text, clears its prior review and invalidates preview/export. Confirming the displayed content and generating again restores export. Ordinary LF restoration preserves its unchanged review. The screenshot uses synthetic content.
- The development wheel is 151,884 bytes, SHA-256 debe68fdd38ecca86d01fce96544338d6be84763fe28248ed732afb140d946c1. Its isolated installation passes 27 offline fixture imports and bundled UI checks using existing dependencies.
- Both initialization 3bcdab2 (run 37862222834) and guest plan review 4989a06 (run 37862503651) pass all six GitHub CI jobs. Later checkpoints were still running when this record was written.
- No live cloud operations, state/credential reads, script execution or AI calls were performed. The v0.4.0 live acceptance gates remain pending.

## Combined VM inputs — v0.4.0 development checkpoint

- The full default suite passes 2,486 tests with 454 optional/native/platform cases skipped. Ruff checks/formatting pass across 122 Python files. Twenty-four new round-trip cases verify each supplied variable's exact exported default, required input completeness, external-secret requirements and preserved project/file content.
- All 24 combined provider/OS/public-private/new-existing-network configurations pass Terraform 1.14.0 validation and TFLint 0.61.0 with initialized provider locks. Custom images, workload identity, a data disk, labels and reviewed initialization are enabled together. Image provenance, effective permissions, guest behavior and live compatibility remain unverified.
- The initialization checkpoint 3bcdab2 passes all six GitHub CI jobs, including native validation (run 37862222834). Subsequent plan-review and mocked-payload checkpoints were still running in Actions when this record was written.
- [VM acceptance evidence](VM_ACCEPTANCE.md) records pending dedicated-account gates and the evidence needed for future separately authorized testing. No live operations, credential/state reads, guest execution or AI requests were performed. v0.3.0 remains the latest release.

## Mocked initialization payloads — v0.4.0 development checkpoint

- Six provider/OS fixtures pass native validation/TFLint and twelve Terraform mocked plan runs. Enabled checks decode AWS and Azure Linux payloads, inspect Azure Windows protected command encoding and verify GCP Linux/Windows startup fields. Disabled checks verify the requested payload or extension is absent from its modeled configuration; GCP serial-console disable remains intact.
- All runs use command=plan with mocked providers and no real credentials, guest execution or cloud resources. AWS's optional/computed user_data_base64 uses an explicit empty mock default when unset; this check does not establish live metadata removal. The native AWS schema confirms that optional/computed property, now explained in the questionnaire and initialization guide.
- The targeted default initialization suite passes 55 tests with 49 native cases skipped; Ruff checks/formatting pass across 121 Python files. The preceding full default policy suite passes 2,462 tests with 424 skipped. The six new provider-mocked cases are wired into native CI.
- v0.4.0 creation, login, guest execution and cleanup remain unverified. v0.3.0 remains the latest release.

## Guest initialization plan review — v0.4.0 development checkpoint

- The full default suite passes 2,462 tests with 424 optional/native/platform cases skipped. Ruff checks and formatting pass across 120 Python files. Eighty-one new regressions cover payloads, references, absence, unknown/malformed values, removals, extension coverage gaps, destructive actions and CLI/API report privacy.
- A browser report from a synthetic EC2 plan shows guest initialization review and limited policy coverage under policy 0.12.0, without echoing payload content. Reports never approve deployment; the screenshot contains no cloud identity or script content.
- The development wheel is 151,693 bytes, SHA-256 a01ba339c2cc6b12858c1d9197300cdd1f386f01c033eb32d360048b7c6486f6. Its isolated installation passes all 81 guest initialization policy regressions and confirms bundled policy/report privacy with existing dependencies.
- Native validation is unchanged by this local review feature. The preceding initialization checkpoint 3bcdab2 passes package smoke and all four Python/platform test jobs; its native GitHub job was still running when this record was written. Check Actions for the final result.
- No script execution, live provider operations, credentials/state reads, cloud provisioning or live AI calls were performed. v0.4.0 live acceptance remains outstanding; v0.3.0 remains the latest release.

## Reviewed VM initialization — v0.4.0 development checkpoint

- The full default suite passes 2,381 tests with 424 optional/native/platform cases skipped. Ruff checks/formatting pass across 118 Python files; JavaScript syntax and whitespace checks pass.

- Fifty-five initialization regressions cover all six provider/OS input and API round trips, safe summaries, missing review, inactive content, format/byte limits, BOM/invalid text, regular-file loading and terminal collection without script execution. An additional regression confirms blank labels remain optional in the browser contract.
- Twenty-four enabled/disabled, Linux/Windows and public/private configurations pass Terraform 1.14.0 validation and TFLint 0.61.0 using existing initialized provider locks. Nineteen isolated native checks verify literal AWS payload decoding, Azure Windows protected command encoding/size and review/format/content guards. These isolated plans use only Terraform's built-in terraform_data resource; no cloud provider is configured or called.
- All six synthetic provider/OS browser imports restore initialization and generated previews. Local script loading clears the previous review, missing review blocks generation and focuses its declaration, and an oversized file preserves current content. Blank labels generate successfully. The screenshot contains only a synthetic script; cloud consent remains off.
- The final development wheel is 150,265 bytes, SHA-256 2c7e35f36c1e98e9c7518d63dc0e3ea61381e3af99abb41efd949755812106a5. Installation into an isolated directory passes 26 offline fixture imports and bundled UI checks with existing dependencies; this is not a release or a fresh dependency-resolution claim.
- The preceding labels checkpoint d700f39 passes all six GitHub CI jobs (run 37860445759). Initialization native tests are included in CI; check GitHub Actions for the new checkpoint result.
- No live credentials/state reads, cloud operations, backend setup, role grants, provisioning, script execution or live AI calls were performed. Guest execution and v0.4.0 Linux/Windows creation, login and cleanup gates remain open. v0.3.0 remains the latest release.

## Optional VM labels — v0.4.0 development checkpoint

- The full default suite passes 2,325 tests with 381 optional/native/platform cases skipped. Forty-two new regressions cover provider/OS import, field-level privacy and format validation, recipe scope and terminal collection. Existing Azure environment-label coverage now includes Windows VMs and checks retained environment/management keys.
- Twelve provider/OS/public-private configurations with labels and data disks pass Terraform 1.14.0 validation and TFLint 0.61.0 with existing initialized provider locks. Three additional native console checks confirm blank and partial maps omit unused labels and preserve environment/management values; no cloud provider is configured in those checks.
- Browser imports and generation succeed for all six provider/OS forms with cloud consent off. Invalid label input focuses its field; correction succeeds. The 390×844 check has no page horizontal overflow. Temporary viewport settings and synthetic entries were cleared; the screenshot uses synthetic values.
- Existing infrastructure is not retagged. Actual labels, policy compliance, billing allocation and live deployment remain unverified. v0.4.0 acceptance gates remain open.
- Ruff checks/formatting pass across 116 Python files, JavaScript syntax and local documentation links pass, and the rebuilt development wheel passes twenty offline fixture imports and bundled UI checks from an isolated package directory using existing dependencies. GitHub CI run 37859792726 passes for the preceding AWS checkpoint (`fdb5566`), including the corrected native private-address fixture.

## Existing AWS subnet — v0.4.0 development checkpoint

- The default suite passes 2,279 tests with 366 optional/native/platform cases skipped. Twenty-four new regressions cover ownership, required subnet/security-group/range inputs, inactive-field conflicts, reserved IPs, safe errors, offline API round trips, terminal collection and browser address calculations.
- Eight Linux/Windows, public/private and catalog/custom existing-subnet combinations and all 24 baseline AWS recipe combinations pass Terraform 1.14.0 validation and TFLint 0.61.0 with existing initialized provider locks. Two additional mocked tests (sixteen plan runs) confirm zero managed network resources in existing mode and reject mismatched CIDRs, shared-account subnets, incompatible security-group accounts/VPCs, IPv6, Outposts and nonstandard zones. All AWS provider operations in these plans are mocked; no live provider or cloud credentials are used.
- Browser imports restore both OS variants, show the declared existing subnet's usable addresses and generate with cloud consent off. Missing review focuses its field; correction succeeds. The 390×844 check shows no horizontal page overflow; temporary viewport settings and synthetic entries were cleared. The screenshot uses synthetic references.
- This checkpoint does not establish effective rule/ACL safety, live attachment, available IP capacity, guest login, state upgrade, recovery or teardown. v0.4.0 remains development; live acceptance gates remain open.
- Azure checkpoint CI (`f7f87ac`, run 37859004930) passed all default/platform and package jobs, but its isolated native private-address fixture omitted newly referenced network-mode variables. The fixture now declares those variables and all 24 native private-address cases pass. Native provider validation of generated configurations was unaffected.
- Ruff checks and formatting pass across 114 Python files, JavaScript syntax and local documentation links pass, and the rebuilt development wheel passes fourteen offline fixture imports plus bundled UI checks from an isolated package directory using existing local dependencies. This is not a released artifact or a fresh dependency-resolution claim.

## Existing Azure subnet — v0.4.0 development checkpoint

- The full default suite passes 2,255 tests with 356 optional/native/platform cases skipped. Twenty-one new regressions cover ownership, subscription/CIDR guards, provider-reserved addresses, explicit range input, terminal questions, safe errors, offline API round trips and browser address calculations.
- Eight Linux/Windows, public/private and catalog/custom existing-subnet combinations pass Terraform 1.14.0 validation and TFLint 0.61.0 with existing initialized provider locks. All 24 baseline Azure recipe combinations pass validation/lint too. Two additional Terraform mocked tests (eight plan runs) confirm zero managed VNet/subnet/NSG/NAT infrastructure in existing mode and reject mismatched CIDR, region and missing subnet NSG metadata. All Azure provider operations in these plan tests are mocked; no live provider or cloud credentials are used.
- Browser imports restore both OS variants, show the declared existing range's usable addresses, and generate with cloud consent off. Missing review focuses the declaration field; correction succeeds. The 390×844 check has no horizontal page overflow; temporary viewport settings and synthetic entries were cleared. The screenshot uses synthetic references.
- Ruff checks/formatting pass across 112 Python files, JavaScript syntax and local documentation links pass, and the rebuilt development wheel passes twelve offline fixture imports plus bundled UI checks from an isolated package directory using existing local dependencies. This is not a released artifact or a fresh dependency-resolution claim.
- The preceding GCP checkpoint (`c579617`) passes GitHub CI run 37857826630. Azure attachment tests are included in native CI. This checkpoint does not establish live upgrades, delegated-subnet detection, effective NSG safety, attachment permissions, IP availability, login or cleanup. v0.4.0 release gates remain open; the user selected continued offline development without cloud test accounts.

## Existing GCP subnet — v0.4.0 development checkpoint

- The full default suite passes 2,234 tests with 346 optional/native/platform cases skipped. Ruff checks and formatting pass across 110 Python files; JavaScript syntax and whitespace checks pass. Sixteen new regressions cover ownership guards, project/region/CIDR validation, safe errors, API round trips and the Linux/Windows terminal questionnaires.
- All 24 existing/new-network, Linux/Windows, public/private, catalog/custom and direct/IAP combinations selected for this change pass Terraform 1.14.0 validation and TFLint 0.61.0 with existing initialized provider locks. Two additional Terraform mocked tests (six plan runs) confirm zero managed network, subnet, administrator firewall, router, NAT and API enablement resources and no adopted VM network tags in existing mode, and reject mismatched actual CIDRs and non-IPv4-only subnet metadata. All Google provider operations in these plan tests are mocked; no cloud credentials or live providers are used.
- Browser imports restore both OS variants, declared CIDR and existing-mode choices with cloud consent off. Missing review focuses the declaration field; correction generates successfully. A 390×844 check shows no page horizontal overflow and the fieldset fits its form. The viewport was reset and test entries cleared. The screenshot uses synthetic references.
- The latest development wheel installs into an isolated package directory and passes ten custom-image, Azure identity and GCP attachment fixture imports plus bundled UI checks using existing local dependencies. This is not a released package or a fresh dependency-resolution claim.
- GitHub CI for the preceding exact Azure gallery correction (`9d714d6`) passes all six jobs, including native validation. New existing-subnet native and mocked tests are included in CI. Current results remain visible in GitHub Actions.
- No live cloud metadata, credential/state access, backend setup, role grant, provisioning or live AI request was performed. Address moves are generated for prior counted-resource transitions, but live upgrades, existing network access and cleanup remain unverified. v0.4.0 release gates remain open.

## Azure image boot compatibility correction

- Azure custom references now require exact Compute Gallery image versions. Microsoft's Trusted Launch guidance identifies managed images as unsupported; the original development managed-image format was corrected without disabling vTPM or Secure Boot defaults. Image security type and guest compatibility still require independent verification.
- Eighteen additional regressions cover Linux/Windows rejection of managed images, unversioned/latest aliases, leading zeros and version overflow, plus accepted numeric boundaries with retained boot settings. All eight Azure catalog/gallery and public/private combinations pass Terraform 1.14.0 validation and TFLint 0.61.0 with existing initialized provider locks.
- The full default suite passes 2,218 tests with 328 optional/native/platform cases skipped. Browser imports generate both Linux and Windows gallery configurations with cloud consent off. The screenshot uses a synthetic exact version; no image query or cloud operation was performed.

## Existing Azure VM identity — v0.4.0 development checkpoint

- The default suite passes 2,200 tests with 328 optional/native/platform cases skipped. Ruff checks and formatting pass across 108 Python files. Sixteen new regressions cover identity modes, references, safe errors, cross-subscription rejection, offline API import and the Linux/Windows terminal questionnaires.
- All 12 Linux/Windows, public/private and disabled/system-assigned/existing-user-assigned combinations pass Terraform 1.14.0 validation and TFLint 0.61.0 with existing initialized provider locks. Native CI includes the new matrix.
- Browser imports restore both Linux and Windows existing identity choices with cloud consent off. Switching to system-assigned hides the inactive reference; corrected existing identity generation succeeds. A fieldset width fix prevents long select options from expanding past the form. Desktop bounds and a 390×844 viewport show the form stays within its container with no page horizontal overflow; the viewport was reset and test entries cleared.
- No cloud query, credential/state access, role grant, identity creation, provisioning or live AI request was performed. Identity attachment, token access, effective permissions and cleanup remain unverified. This checkpoint does not complete v0.4.0 release gates.

## Existing VM images — v0.4.0 development checkpoint

- The default suite passes 2,184 tests with 316 optional/native/platform cases skipped. Ruff checks and formatting pass across 106 Python files; JavaScript syntax, whitespace and changed documentation local links pass.
- All 24 provider/OS/catalog-or-custom/public-or-private combinations pass Terraform 1.14.0 validation and TFLint 0.61.0 using existing initialized provider locks. A separate fresh initialization attempt timed out while downloading the Google provider; it did not complete. Native CI includes the new image matrix.
- Thirty-four new regressions cover contracts, exact reference formats, owner and administrator inputs, absent declarations, stale catalog values, secret-free API import/export and the terminal questionnaire. Azure catalog-image regressions retain publisher, credentials, patch and boot assertions with the conditional image block.
- Browser checks import all six provider/OS custom-image fixtures, show custom inputs and hide inactive catalog inputs. AWS mode switching restores catalog questions; an absent review declaration focuses its field. Generation succeeds after correction. Cloud target consent remains off. The new screenshot uses a synthetic GCP image reference.
- A built `0.4.0.dev0` wheel installed into an isolated package directory passes all six image imports and bundled UI checks using the existing local dependencies. This is a development package check, not a public release or fresh dependency-resolution claim.
- No live cloud query, credential/state access, backend operation, provisioning, IAM grant or live AI request was performed. Image trust, guest compatibility, Linux/Windows creation, login and teardown remain unverified. v0.3.0 remains the latest release; v0.4.0 acceptance gates remain open.

## v0.3.0 release verification

- The default suite passes 2,150 tests with 292 optional/native/platform cases skipped. Ruff checks and formatting pass across 104 Python files; backend JavaScript syntax, whitespace and local documentation links pass.
- All 495 selected generator, network, image, administrator-name and AWS-placement tests pass with native checks enabled on Windows, using Terraform 1.14.0 and TFLint 0.61.0. Provider initialization, validation and linting ran without cloud deployment. This suite includes the native template combinations skipped by the default suite.
- Twenty additional backend API cases verify known-field format guidance and generic unknown/schema errors without submitted values. Three project cases cover the release template default and accepted saved development specifications, preserving template labels and recording the current generator version in receipts.
- A clean Python 3.14 virtual environment installed the built v0.3.0 wheel with freshly resolved dependencies, including Pydantic 2.14.0 and FastAPI 0.143.0. The installed package passed version, bundled UI assets, generation, ZIP/checksum presence, project import, backend contracts, safe field errors and absent plan/apply/destroy route checks.
- The installed CLI generated the synthetic example project and `verify-project` reported matching files and specification. Receipt authentication and deployment approval remained false.
- Browser checks verified invalid account-field focus/help, correction and successful input recheck, cleared entries after closing, and project import with no cloud consent or AI opt-in. A 390×844 viewport showed no horizontal overflow in the storage form; the override was reset. Workspace, configuration and storage screenshots use synthetic examples.
- No live cloud metadata, credential/state access, backend initialization/migration, IAM grant, provisioning or live AI request was performed. Remaining boundaries are listed in the release notes, artifact guide and state protection design.

## Saved backend input import checkpoint

- The default suite passes 2,127 tests with 292 optional/native/platform cases skipped. The targeted backend/browser suite passes 155 tests. Ruff checks and formatting pass across 104 Python files; JavaScript syntax and whitespace checks pass.
- Thirteen additional API cases cover import authentication/origin guards, unsupported/credential fields, duplicate keys, exact and streamed size boundaries, rejected state/project/credential-file schemas and canonical UUID restoration. Existing provider round trips now import downloaded files and confirm the returned contract and unverified status.
- Browser checks imported a synthetic GCP intent into the S3 form, restored its references and required a new check before download. Invalid state-shaped and oversized files preserved an existing owner entry. A new check succeeded; the screenshot uses synthetic references. No cloud request, credential/state access, backend initialization or migration was run.

## Browser backend inputs checkpoint

- The default suite passes 2,114 tests with 292 optional/native/platform cases skipped. The targeted backend/CLI/browser API suite passes 142 tests. Ruff checks and formatting pass across 104 Python files; JavaScript syntax and whitespace checks pass.
- Twenty-three new API regressions cover shared provider contracts/checks/downloads, session/origin guards, credential/invalid-field rejection, strict JSON, exact/streamed byte limits, value-free reports and private attachment/cache headers.
- A temporary browser tab checked synthetic references for all three storage providers, rejected invalid S3 input, downloaded and inspected the valid S3 file, disabled downloading after an edit and cleared entries after closing. A phone-sized viewport showed no horizontal overflow; its override was reset. No cloud request, credential/state access, backend initialization, migration or provisioning was run.
- The browser download contains non-secret references and follows browser folder permissions. Local API checks run in memory and never write an input file. Actual authentication, locking, storage protection and recovery remain unverified.

## Guided backend inputs checkpoint

- The default suite passes 2,091 tests with 292 optional/native/platform cases skipped. Ruff checks and formatting pass across 103 Python files; whitespace and changed documentation link checks pass.
- Twenty-three new regressions cover guided S3/Azure Blob/GCS file creation and checker round trips, cancellation at different stages, occupied destinations, declined S3 lockfile intent, invalid inputs, concurrent file creation, sync-error cleanup and shared prompt validation. The targeted backend/CLI/artifact suite passes 134 tests with two platform cases skipped.
- The wizard saves only a standalone non-secret intent using the existing terminal writer. No backend HCL, credential read, cloud request, state access, migration, IAM grant or provisioning operation was performed. Backend integration and authentication/locking/recovery verification remain planned.

## Offline backend contract checkpoint

- The full default suite passes 2,066 tests with 292 optional/native/platform cases skipped. All 73 backend regressions pass in a targeted run after the final reserved-name refinements, including two cases added after full-suite collection. Ruff checks and formatting pass across 102 Python files; whitespace and changed documentation link checks pass.
- Coverage includes strict non-secret fields for all three backends, mandatory declared S3 locking, provider-specific names/identifiers, traversal and size rejection, malformed JSON, missing inputs, credential-field rejection, redacted CLI failures and matching CLI/library reports. Successful checks never grant approval or claim a configured backend.
- Backend intents remain separate from generated project specifications. No backend HCL, state migration, cloud query, credentials read, state access, IAM grant or provisioning operation was performed. Authentication, actual locking, permissions and recovery remain unverified.

## Prior disk key material checkpoint

- All 162 targeted disk-key and existing plan-review tests pass after extending the rule to prior values; Ruff checks and formatting pass across 100 Python files. Six additional regressions cover removed or migrated boot/persistent disk material without disclosing it. The preceding full-suite checkpoint remains recorded below.
- No cloud request, credentials access, key creation, IAM grant or apply was run. Removing a key from planned configuration does not remove its prior value from the private plan export.

## GCP disk key review checkpoint

- The default suite passes 1,989 tests with 292 optional/native/platform cases skipped. Ruff checks and formatting pass across 100 Python files; whitespace checks pass.
- Fifty-eight new regressions cover boot/persistent disk references, added/changed/removed keys, unchanged keys, raw key material, relevant versus unrelated unknown values, malformed controls, preserved destructive blocking and identical redacted CLI/API reports.
- Policy 0.11.0 checks declared plan controls only and always reports that approval is not granted. Effective encryption, key location/state/IAM, source-image decryption and recovery remain unverified. No cloud request, credentials access, key creation, IAM grant or apply was run.

## Existing GCP disk key checkpoint

- The default suite passes 1,931 tests with 292 optional/native/platform cases skipped. Ruff checks and formatting pass across 99 Python files; JavaScript syntax and whitespace checks pass.
- Twenty-six new regressions cover Linux/Windows, enabled/default key modes, optional disks, malformed/raw/unused references, missing required keys, supported location shapes, unrelated recipes and API import. The Terraform lifecycle also requires a key when enabled. Google-managed encryption remains the default.
- Eight separately enabled Linux/Windows mode/data-disk cases pass real Terraform validation and TFLint against the cached Google provider. Key availability, location compatibility, IAM access, disk creation and encrypted boot remain unverified.
- A temporary browser tab imported an older GCP Linux project, enabled the existing-key option and generated its reference and recovery warning. The tab was closed; original sidebar spacing and the user's tab were preserved. No cloud request, key creation, IAM grant or apply was run.

## Catalog consistency checkpoint

- Eighty-three catalog, GCP image-pin and gp3 regressions pass. Seven new checks compare Linux/Windows image choices across providers and the reported AWS performance ceilings against the input contract. Ruff checks and formatting pass across 98 Python files; whitespace checks pass.
- This corrects capability descriptions without changing Terraform generation or cloud behavior. No cloud request or apply was run.

## Expanded regional gp3 checkpoint

- The default suite passes 1,898 tests with 284 optional/native/platform cases skipped. Ruff checks and formatting pass across 98 Python files; whitespace checks pass.
- Existing boundary tests now cover regional 80,000 IOPS/2,000 MiB/s ceilings, minimum size/IOPS ratios and overflow rejection for boot/data disks. Two additional API regressions preserve maximum-performance Linux/Windows projects through import. Included-performance defaults are unchanged.
- Four separately enabled Linux/Windows private/public cases pass real Terraform validation and TFLint against the cached AWS provider. No volume creation or achieved throughput was verified; Outposts is unsupported.
- A temporary browser tab imported maximum boot-performance answers and verified the numeric ceiling and generated summary. The tab was closed; original sidebar spacing and the user's tab were preserved. No cloud request or apply was run.

## Generated file synchronization checkpoint

- The default suite passes 1,884 tests with 280 optional/native/platform cases skipped. Ruff checks and formatting pass across 98 Python files; whitespace checks pass.
- Eight new regressions inject sync errors/interrupts on early, middle and final files, preserve existing notes, verify incomplete-cleanup reporting and confirm the CLI omits private errors and success messages after failure. Existing receipt, permission and CLI tests pass.
- File synchronization uses the operating system's supported primitive. Directory entries, parent directories, atomic publication, hardware durability and browser-download permissions remain separate boundaries. No state or cloud resources were touched.

## Metadata hop policy checkpoint

- The default suite passes 1,876 tests with 280 optional/native/platform cases skipped. Ruff checks and formatting pass across 97 Python files; whitespace checks pass.
- Thirty-four new regressions cover one/additional hops, disabled endpoints, relevant versus unrelated unknown controls, malformed values/markers, preserved IMDSv1 blocking and identical redacted CLI/API reports. A targeted rerun after the exception-type lint correction passes.
- Policy 0.10.0 remains partial and never grants approval. No cloud request, guest/container access, IAM evaluation or apply was run.

## AWS metadata response hops checkpoint

- The default suite passes 1,842 tests with 280 optional/native/platform cases skipped. Ruff checks and formatting pass across 96 Python files; JavaScript syntax and whitespace checks pass.
- Twenty-four new regressions cover Linux/Windows, public/private, all supported modes, invalid answers, unrelated recipe exclusion, API import and readable summaries. Existing CLI and VM regressions pass; the unmanaged default preserves existing generated behavior.
- Six separately enabled Linux/Windows mode cases pass real Terraform validation and TFLint against the cached AWS provider. No guest/container access or effective cloud settings were verified.
- A temporary browser tab imported an AWS Linux project, selected the two-hop label and generated its matching summary. The tab was closed; original sidebar spacing and the user's tab were preserved. No cloud request, credentials access or apply was run.

## Azure Windows Core checkpoint

- The default suite passes 1,818 tests with 274 optional/native/platform cases skipped. Ruff checks and formatting pass across 95 Python files; whitespace checks pass.
- Eleven new regressions cover private/public Core selection, latest/exact versions, Secure Boot choices, preserved password/patch/vTPM controls, unsupported versions and API import. The former Azure exclusion case was removed; desktop remains the default.
- Four separately enabled private/public latest/pin cases pass real Terraform validation and TFLint against the cached AzureRM provider. Synthetic versions are structural examples; regional availability, activation and guest boot remain unverified.
- A temporary browser tab imported an Azure Windows project, selected Core and generated the matching summary and replacement guidance. The tab was closed; original sidebar spacing and the user's tab were preserved. No cloud request, connection or apply was run.

## GCP Windows Core checkpoint

- The default suite passes 1,808 tests with 270 optional/native/platform cases skipped. Ruff checks and formatting pass across 94 Python files; whitespace checks pass.
- Thirteen new regressions cover private/public Core selection, direct/IAP paths, latest/exact image names, desktop/Core pin mismatch rejection, unsupported versions, API import and preserved activation/Shielded/serial-console controls. The earlier AWS-only exclusion case was narrowed to Azure now that GCP offers Core.
- Four separately enabled private/public latest/pin IAP cases pass real Terraform validation and TFLint against the cached Google provider. Synthetic exact image names are structural examples; availability and live guest behavior remain unverified.
- A temporary browser tab imported an older GCP Windows project, selected Core with a matching exact name and IAP, then generated the matching summary and access guide. The tab was closed; original sidebar spacing and the user's tab were preserved. No cloud request, connection or apply was run.

## Azure Windows refreshed offer checkpoint

- The default suite passes 1,796 tests with 266 optional/native/platform cases skipped. Ruff checks and formatting pass across 93 Python files; whitespace checks pass.
- Existing Windows generation regressions assert the refreshed windowsserver2022 offer with the same publisher/SKU and latest/exact version support. API guidance warns about image replacement, application dependencies and old pins requiring review.
- Four separately enabled private/public latest/pin cases pass real Terraform validation and TFLint against the cached AzureRM provider. Synthetic exact versions are structural examples; new-offer regional availability and guest boot remain unverified.
- Microsoft's Azure Compute announcement was read directly in a temporary browser tab to verify the refreshed offer and legacy-offer deprecation. A second tab imported an Azure Windows project, generated the new reference and displayed its migration warning. Both tabs were closed; original sidebar spacing and the user's tab were preserved. No live cloud request, guest migration or apply was run.

## AWS Windows Core checkpoint

- The default suite passes 1,796 tests with 262 optional/native/platform cases skipped. Ruff checks and formatting pass across 93 Python files; whitespace checks pass.
- Fifteen new regressions cover private/public Core selection, latest/pinned AMIs, separate boot lifecycle, Amazon owner/name/x86_64/HVM filters, unsupported variants, other provider exclusion and API import. Full Base remains the default.
- Four separately enabled private/public latest/pin cases pass real Terraform validation and TFLint against the cached AWS provider. Synthetic pinned AMI identifiers are structural examples; no cloud availability or boot was verified.
- A temporary browser tab imported an older AWS Windows project, confirmed Full Base as the default, selected the readable Core option and generated its summary and replacement/compatibility warning. The tab was closed; original sidebar spacing and the user's tab were preserved. No cloud request, credential recovery, connection or apply was run.

## Readable questionnaire choices checkpoint

- Eighty-three existing CLI, GCP access/scheduling and AWS credit regressions pass. Ruff checks/formatting and JavaScript syntax pass. These labels change presentation while preserving input values and defaults.
- A temporary browser tab selected the displayed Google IAP tunnel label, hid the unused network input and generated the existing `iap_tunnel` value in its choice summary. The tab was closed; original sidebar spacing and the user's tab were preserved.

## Standalone boot disk lifecycle checkpoint

- The default suite passes 1,781 tests with 258 optional/native/platform cases skipped. Ruff checks and formatting pass across 92 Python files; JavaScript syntax passes.
- Twenty-six new regressions cover AWS/GCP Linux/Windows deletion/retention values, unchanged defaults, separate data-disk scope, boolean validation, unrelated recipe exclusion and API import. Generated warnings distinguish AWS encrypted-key preservation from GCP replacement naming.
- Eight separately enabled AWS/GCP Linux/Windows deletion/retention cases pass real Terraform validation and TFLint against cached providers. No cloud request, apply, deletion or recovery was run.
- A temporary browser tab imported an older AWS Windows project, confirmed the enabled deletion default, selected retention and generated the matching summary and KMS warning. The tab was closed; original sidebar spacing and the user's tab were preserved. Live disk retention, key preservation and recovery remain unverified.

## GCP Windows image pin checkpoint

- The default suite passes 1,755 tests with 250 optional/native/platform cases skipped. Ruff checks and formatting pass across 91 Python files; whitespace checks pass.
- Twenty new regressions cover latest/exact names, private/public and direct/IAP combinations, the fixed windows-cloud publisher, API import preservation and rejection of other OS variants, publisher paths or expressions. Existing defaults remain latest.
- Two separately enabled private/public cases pass real Terraform validation and TFLint against the cached Google provider. The example image name is synthetic; validation does not establish that it exists or boots.
- A temporary browser tab imported an older Windows project, generated with an exact name, rejected a mismatched OS through field validation and restored the valid example. The tab was closed; original sidebar spacing and the user's tab were preserved. No cloud request, tunnel or apply was run.

## Google IAP generation checkpoint

- The default suite passes 1,735 tests with 248 optional/native/platform cases skipped. Ruff checks and formatting pass across 90 Python files; JavaScript syntax passes.
- Twenty-three new regressions cover Linux/Windows private/public access choices, unchanged direct-access defaults, conditional CIDR visibility, invalid choices, unrelated recipe exclusion and API import/generation. Existing public direct-access requirements remain enforced.
- Four separately enabled Linux/Windows private/public IAP cases pass real Terraform validation and TFLint against the cached Google provider. No cloud read, IAM grant, tunnel connection or apply was run.
- A temporary browser tab imported an older GCP Windows project, selected IAP, hid the unused CIDR field and generated matching configuration, summary and access-path guidance. Original sidebar spacing and the user's tab were preserved. Live IAM, guest access and SSH/RDP connectivity remain unverified.

## Google IAP plan policy checkpoint

- The default suite passes 1,712 tests with 244 optional/native/platform cases skipped. Ruff checks and formatting pass across 89 Python files; whitespace checks pass.
- Seventy new regressions cover exact SSH/RDP proxy rules, broader or missing selectors, unknown/malformed markers, destructive changes and identical redacted CLI/API reports. Approval remains false, and other policy gaps remain visible.
- This is local plan classification only. Guided IAP generation, tunnel IAM, guest authentication and live connectivity have not been verified. No cloud request or apply was run.

## AWS CPU credit choices checkpoint

- The default suite passes 1,642 tests with 244 optional/native/platform cases skipped. Ruff checks and formatting pass across 88 Python files; JavaScript syntax passes.
- Thirty-two new regressions cover shared choices/defaults, Linux/Windows generation, supported family constraints, unrelated recipe exclusion, API import preservation and incompatible size rejection. Four separately enabled Linux/Windows standard/unlimited cases pass real Terraform validation and TFLint against the cached AWS provider.
- A temporary browser tab imported an older AWS Windows project, selected standard credits, generated the matching variable and summary, then rejected an incompatible size before generation. The valid example was restored and the tab closed; original sidebar spacing and the user's tab were preserved.
- No cloud read or apply was run. Credit mode defaults and removal behavior follow the provider contract; performance, account-specific settings and surplus-credit costs remain unverified.

## AWS standalone boot capability checkpoint

- The default suite passes 1,610 tests with 240 optional/native/platform cases skipped. Ruff checks and formatting pass across 87 Python files; JavaScript syntax passes.
- Forty-one new mocked regressions cover Linux/Windows EBS/HVM support, explicitly incompatible capabilities, missing/empty metadata, malformed/duplicate values, CPU failure priority and no zone offering read when boot requirements are unresolved. Root encryption off does not bypass boot checking.
- Existing CLI/API regressions preserve the boot capability field alongside disk encryption and zone offering results. This uses the existing size read and adds no cloud request. No live cloud read or apply was run; AMI boot mode, OS compatibility, capacity and deployment remain unverified.

## Cloud authentication guidance checkpoint

- Three PowerShell examples parse without errors; no login or cloud command was executed. Guidance references the official cloud/provider authentication documentation and preserves the distinction between CLI target confirmation and Terraform credentials.
- The existing local UI/asset smoke case passes. A temporary browser tab imported a synthetic project and displayed the authentication guide link beside the unchecked cloud-read controls; its destination matches the published documentation path. The user's tab and sidebar spacing were preserved.

## Storage encryption guidance checkpoint

- The existing 11 CLI regressions pass after moving the provider-specific explanation before the encryption question. Ruff checks/formatting and JavaScript syntax pass.
- A temporary browser tab checked AWS standalone VM, database, web-server and static-site guidance. Local AWS Windows generation with root encryption off and a data disk enabled produced `encrypted = false` for the boot disk and `encrypted = true` for the data disk, matching the explanation. No cloud resources were created.
- The same tab displayed the new EBS capability consent guidance with cloud reads disabled. Temporary tabs were closed, the user's tab was preserved and original sidebar spacing remains unchanged.

## AWS EBS encryption capability checkpoint

- The default suite passes 1,569 tests with 240 optional/native/platform cases skipped. Ruff checks and formatting pass across 86 Python files; JavaScript syntax passes.
- Twenty-five new mocked regressions pass for Linux/Windows supported, unsupported, missing and malformed EBS metadata; encrypted root/data disk requirements; CPU failure priority; and no subsequent zone read when disk capability is unresolved. Existing CLI/API zone regressions retain the additional capability field.
- The size metadata read is unchanged and no extra cloud request is added. No live cloud read or apply was run; KMS access, account encryption policy, volume limits and deployment remain unverified.

## AWS zone offering preflight checkpoint

- The default suite passes 1,541 tests with 240 optional/native/platform cases skipped. Three additional unresolved-machine gating cases were then added; all 50 new offering regressions pass. Ruff checks/formatting and JavaScript syntax pass.
- Mocked Linux/Windows reads cover exact offerings, absent offerings, incomplete pagination, malformed/duplicate/mismatched records, timeout/output limits and CLI errors. Consent, target mismatch, automatic placement and unresolved CPU metadata prevent the offering read. CLI and API return the same redacted reports without deployment approval.
- A temporary browser tab imported a synthetic AWS Windows project and displayed the updated questionnaire and consent guidance. Both consent controls remained unchecked; no live cloud read ran. Original sidebar spacing and the user's tab were preserved.
- AWS offering metadata does not verify capacity, quotas, deployment permissions, image compatibility, a second usable zone or Terraform credential equivalence. Cloud provisioning remains unverified.

## Native CI coverage checkpoint

- The generator/placement default regression run passes 101 cases with 228 optional native cases skipped. Two separately enabled real AWS provider lock cases pass: matching requirements validate without changing source/copied locks, and conflicting requirements fail initialization without a writable retry.
- Native CI now includes the six offline AWS placement expression cases and both provider lock cases. Its setup step creates a runner-local provider cache to reuse downloaded plugins; registry checks and lock checksums remain enforced. No cloud API or apply is introduced.
- GitHub rejected the initial cache configuration before running jobs because `runner.temp` was unavailable at job environment scope. The follow-up uses `RUNNER_TEMP` and `GITHUB_ENV` inside the setup step; [the corrected workflow passed all jobs](https://github.com/chriswayneh/TerraForma-IaC/actions/runs/37613261700).

## AWS standalone placement checkpoint

- The default suite passes 1,494 tests with 238 optional/native/platform cases skipped. Ruff checks and formatting pass across 84 Python files; JavaScript syntax passes.
- Thirty-one new regression cases cover Linux/Windows public/private placement, generation/import preservation, automatic defaults, reported-standard-zone filtering and subnet guards, region matching, unsupported inputs and exclusion from other workloads.
- Four separately enabled Linux/Windows automatic/selected-zone configurations pass native provider validation and TFLint. Six cloud-free native Terraform console cases evaluate the generated ordering and guard expressions against mocked available-zone lists, including an absent requested zone and too few zones.
- A temporary browser tab imported an AWS Windows project, generated successfully with blank automatic placement, selected `us-east-1b` and generated again. The summary retained the selected answer; the user's tab was preserved.
- These checks establish expression/schema behavior only. Live zone availability, account mappings, capacity, deployment and replacement/recovery remain unverified. No cloud read, apply or provisioning was performed.

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
