# Connect your cloud tools

Generate and review example files without signing in to a cloud. When checking a real target, connect only the cloud you selected. Terraform and the cloud CLI manage credentials outside TerraForma; enter account references and infrastructure inputs in the questionnaire.

| Task | What you need |
| --- | --- |
| Generate files or run local provider validation | Python, plus Terraform/TFLint for validation; provider downloads need network access |
| Check target and VM metadata | The selected cloud CLI, an authenticated session and permission for the requested reads |
| Plan or deploy outside TerraForma | Terraform provider authentication, appropriate resource permissions, protected state and a reviewed plan |

TerraForma does not run plan, apply or destroy. Signing in does not grant permissions or confirm readiness. These examples are commands for your terminal; TerraForma does not execute them for you.

## AWS

Install the [AWS CLI](https://docs.aws.amazon.com/cli/latest/userguide/getting-started-install.html). If your organization provides IAM Identity Center access, configure its assigned account and role using [AWS's SSO setup](https://docs.aws.amazon.com/cli/latest/userguide/cli-configure-sso.html). Use a profile name reserved for this project; the examples use `terraforma`.

```text
aws configure sso --profile terraforma
aws sso login --profile terraforma
```

Select that profile in the terminal used to start TerraForma and later run Terraform:

```powershell
$env:AWS_PROFILE = "terraforma"
```

On macOS/Linux, use `export AWS_PROFILE=terraforma`. Restart TerraForma after changing its environment. The questionnaire supplies the deployment region separately from the SSO directory's region.

The [AWS provider credential chain](https://registry.terraform.io/providers/hashicorp/aws/latest/docs) can select other credentials when environment variables or provider settings take precedence. Review existing configuration if the observed account differs; a matching CLI account does not establish Terraform's principal or permissions. If SSO is unavailable, follow your organization's approved credential method outside TerraForma.

Opt-in checks use caller-account metadata and EC2 instance-type metadata. Selecting an AWS VM zone also requires `ec2:DescribeInstanceTypeOfferings`; this reads reported offerings, not capacity. No role or permission set is created.

## Azure

Install the [Azure CLI](https://learn.microsoft.com/en-us/cli/azure/install-azure-cli) and sign in using [Microsoft's interactive authentication guidance](https://learn.microsoft.com/en-us/azure/developer/terraform/authenticate/authenticate-to-azure-with-microsoft-account):

```powershell
az login
$terraformaSubscription = Read-Host "Subscription ID from your questionnaire"
az account set --subscription $terraformaSubscription
az account show --query '{id:id, state:state}' --output json
```

Confirm that the subscription matches your questionnaire. For local Terraform use, review the [AzureRM provider's CLI authentication requirements](https://registry.terraform.io/providers/hashicorp/azurerm/latest/docs/guides/azure_cli). Existing `ARM_*` authentication settings can select a different credential method; TerraForma does not inspect or reconcile identities.

Target preflight reads subscription metadata. Optional VM preflight reads SKU restrictions and requested capabilities, including selected zone support. It does not verify feature registration, capacity or resource permissions. Keep Windows administrator passwords in the documented [external secret workflow](AZURE_WINDOWS_DESIGN.md), and protect Terraform state and saved plans.

## Google Cloud

Install the [Google Cloud CLI](https://docs.cloud.google.com/sdk/docs/install), then use an approved identity and your questionnaire's project ID:

```powershell
gcloud auth login
$terraformaProject = Read-Host "Project ID from your questionnaire"
gcloud config set project $terraformaProject
gcloud auth application-default login
```

The CLI login and Application Default Credentials (ADC) are separate configurations. [Terraform uses ADC](https://docs.cloud.google.com/docs/terraform/authentication); TerraForma's optional reads use the CLI. A successful CLI project check does not prove the ADC identity matches.

The [ADC login command](https://docs.cloud.google.com/sdk/gcloud/reference/auth/application-default/login) writes a local credential file, replaces earlier user ADC and may select a quota/billing project from CLI configuration. Review your organization's existing authentication before replacing it. If `GOOGLE_APPLICATION_CREDENTIALS` is set, its configuration can take precedence over user ADC. Credentials stay outside generated projects.

Target preflight reads project metadata; VM preflight reads the selected zone's machine-type metadata. Billing, enabled APIs, quotas, permissions and deployment remain unverified.

## Check the saved target

After exporting a project and authenticating the selected CLI, explicitly request the reads:

```text
terraforma preflight --spec terraforma.project.json --verify-target --verify-machine
```

Or use **Check your cloud target** in the web UI and enable the relevant consent controls. Results omit raw responses and never grant deployment approval. Authentication sessions can expire; reauthenticate through the cloud tool when needed.

Before any external deployment, review [artifact and state handling](ARTIFACTS.md), the recipe's limits and your organization's approval process. Never paste tokens, private keys or passwords into the questionnaire, screenshots or repository.
