# Azure Windows credential design

Status: initial native Azure Windows generation is implemented on `main`. Live deployment and protected backend configuration remain unverified or planned. Operational inputs for all three clouds are described in [Windows VMs](WINDOWS_VM.md).

The adapter uses a native Windows VM resource and the shared questionnaire contract. Both interfaces expose the credential and state boundary plainly before users export or deploy a configuration.

## Verified provider boundary

Native schema inspection with AzureRM 4.81.0 found `admin_password` marked sensitive, with no write-only password argument. The [provider documentation](https://github.com/hashicorp/terraform-provider-azurerm/blob/v4.81.0/website/docs/r/windows_virtual_machine.html.markdown) explains that VM arguments, including the password, are stored in Terraform state. A sensitive variable hides ordinary display; it does not remove the value from state. Supplying `TF_VAR_admin_password` externally prevents a literal password in generated files, but cannot establish protected state storage.

Do not invent `admin_password_wo` or mark the normal field as an ephemeral value. Provider support and the minimum Terraform version must be verified before adopting either mechanism. Generated projects permit Terraform 1.6. The Windows recipe requires AzureRM 4.81 or later within 4.x (`~> 4.81`), matching the validated argument names. AzureRM 4.0 used `enable_automatic_updates`; the generated `automatic_updates_enabled` argument is verified with 4.81. Existing non-Windows Azure recipes retain their prior `~> 4.0` constraint. Review and update an older dependency lock before initializing the Windows recipe.

## Delivery boundary

| Requirement | Adapter behavior |
| --- | --- |
| Password entry | Show the external `TF_VAR_admin_password` reference; never render a password input |
| Saved project | Record only the declared environment-variable reference |
| Generated HCL | Declare a sensitive variable without a password default or credential output |
| Validation | Structural validation must not read a password or make authenticated cloud calls |
| Protected state | Record state ownership and the chosen protected storage workflow before enabling managed plan/apply |
| Plan artifacts | Treat saved plans and JSON exports as sensitive; protect their storage and access |
| AI | Keep password/state/plan contents outside automatic AI transmission |
| User guidance | Explain state retention and password replacement behavior alongside the secret reference |

Generation alone cannot prove backend encryption, authorization, backup retention, or who can read a downloaded project on the host. Checks must report what was actually inspected and leave the remaining controls unverified. No acknowledgment should be presented as an authenticated security guarantee.

## Key Vault alternative

Azure Resource Manager supports [a Key Vault reference for a secure deployment parameter](https://learn.microsoft.com/en-us/azure/azure-resource-manager/templates/key-vault-parameter). This can keep the password value out of Terraform's parameter payload when Azure resolves the reference. Reading a Key Vault secret into an ordinary Terraform data source would still expose the value to Terraform and is not the same design.

An ARM deployment adapter would require additional permission checks, resource ownership and teardown rules, and policy inspection of resources inside its template. A deployment wrapper must not conceal VM changes from the plan reviewer or silently switch lifecycle semantics. It is a separate candidate adapter, rather than an implicit substitute for the native VM resource.

## Supported inputs and remaining verification

| Area | Required operational choices |
| --- | --- |
| Identity | Subscription, environment, resource naming and existing provider credentials |
| Image | Reviewed Windows publisher/offer/SKU, architecture, exact version or latest, regional availability and licensing |
| Guest naming | Administrator username within Windows limits and a separately visible computer name within the 15-character limit |
| Capacity | VM size, boot disk type/size, optional data disk and supported performance limits |
| Connectivity | New network/subnet, optional private/public address and restricted RDP administrator CIDR |
| Protection | Secure Boot/vTPM compatibility, host encryption support, diagnostics, optional managed identity and backup boundaries |
| Credentials/state | External password reference, state storage ownership, plan handling and recovery expectations |

Windows naming limits differ from the existing Linux adapter; [Microsoft's OS profile documentation](https://learn.microsoft.com/en-us/python/api/azure-mgmt-compute-bulkaction/azure.mgmt.compute.bulkaction.types.osprofile?view=azure-python-preview) specifies a 20-character administrator username and 15-character computer name. Do not silently truncate the project name into a hostname. Show the chosen hostname in the questionnaire and exported summary.

Input validation, export/import, native provider/lint cases and Windows boot policy coverage are implemented. Account-specific image availability, size compatibility, guest boot and password acceptance still need live verification. Release acceptance requires a dedicated test-account creation, credential/access verification and controlled teardown. These deployment checks remain outstanding.
