# Getting started

[Project home](../README.md) · [Security overview](SECURITY_OVERVIEW.md) · [All guides](README.md)

**Goal:** launch the local app and export your first Terraform project. You do not need a cloud account, Terraform installation or AI key for this walkthrough.

## 1. Install the released version

Use the [Windows or macOS/Linux commands in the README](../README.md#quick-start). They clone release `v0.3.0`, create a private Python environment named `.venv`, install the web dependencies and start the app. The environment keeps these packages separate from your other projects; it is not a security sandbox.

Check prerequisites before installing:

| Requirement | Check | Used for |
| --- | --- | --- |
| Python 3.11+ | `python --version` on Windows; `python3 --version` on macOS/Linux | Running TerraForma |
| Git | `git --version` | Downloading the repository |
| Internet access | Package downloads must be reachable | Installing Python dependencies |
| Terraform and TFLint | Optional; install later | Native configuration checks |
| Cloud account / OpenAI key | Not needed for the first run | Separately enabled cloud checks / AI explanations |

The released checkout is pinned to a tag, so Git's **detached HEAD** notice is expected. It does not prevent installation or use. For development, clone `main` into a separate directory without `--branch v0.3.0`; it currently installs `0.4.0.dev0`. Do not mix development examples with a released installation.

If Git is unavailable, download the wheel and `SHA256SUMS.txt` from the [v0.3.0 release](https://github.com/chriswayneh/TerraForma-IaC/releases/tag/v0.3.0), compare the wheel's SHA-256 to the published checksum, and install into a virtual environment. From the folder containing the wheel, on Windows:

```powershell
python -m venv .venv
.venv/Scripts/python.exe -m pip install "./terraforma_iac-0.3.0-py3-none-any.whl[web]"
.venv/Scripts/python.exe -m terraforma.cli serve --open-browser
```

On macOS/Linux use `python3` to create the environment and `.venv/bin/python` for the other two commands. A checksum compares downloaded bytes; it is not independent proof of publisher identity.

## 2. Open the workspace

Open [http://127.0.0.1:8765](http://127.0.0.1:8765). This address points to your computer. Keep the server terminal open while using the app.

To launch again later, return to the project folder and run:

```powershell
.venv/Scripts/python.exe -m terraforma.cli serve --open-browser
```

Use `.venv/bin/python` on macOS/Linux. Stop the server with **Ctrl+C**. If port 8765 is already occupied, add `--port 8766` and open `http://127.0.0.1:8766`.

## 3. Generate a first project

1. Choose **Amazon Web Services** and continue.
2. Choose **A static website** and continue.
3. Enter `first-site` as the project name. Keep public access off. Enter `123456789012` in **AWS account ID** for this offline demonstration; keep the other defaults, including region `us-east-1`.
4. Select **Generate Terraform**. Read the resource explanation and inspect all three file tabs.
5. Select **Download .zip**, then extract it into a new folder.

This example describes private S3 object storage containing an HTML object. It does not create a public website. The demonstration account ID is a synthetic placeholder, not an authenticated target. Replace it with your intended account ID and review the project before live use. Generation does not authenticate to AWS, create resources or incur cloud usage charges. Optional cloud checks and AI explanations are unnecessary for this exercise.

### Understand the output

| File | Plain-language purpose |
| --- | --- |
| `main.tf` | The cloud provider and resources Terraform would manage. |
| `variables.tf` | The configuration inputs and any required values without defaults. |
| `outputs.tf` | Values Terraform would display after deployment. |
| `terraforma.project.json` | Non-secret answers you can load into TerraForma again. |
| `terraforma.receipt.json` and `SHA256SUMS.txt` | Hashes for comparing exported files; they do not approve deployment or authenticate the publisher. |
| `README.md` | Instructions and required inputs for this generated project. |
| `.gitignore` | Common state, plan, variable and credential filenames to exclude from Git. |

You have completed the first run when the ZIP is downloaded and you can read the three Terraform files. Load `terraforma.project.json` using **Load project** to reuse the saved answers. Generate again after editing inputs.

Browser **Remember choices** saves non-secret questionnaire choices locally. It does not save credentials, AI consent, generated code or validation logs. Unchecking it removes those saved choices; [data-handling details](SECURITY_OVERVIEW.md#data-and-network-access) explain the other storage boundaries.

## 4. Add local validation when ready

Install Terraform and TFLint separately using the [validation guide](VALIDATION.md). Choose **Validate locally** after generation. These checks initialize provider dependencies and inspect configuration structure and lint rules; they can download executable plugins and should use trusted configurations only.

A passing result does not verify cloud permissions, prices, capacity, guest login or deployment success. You can export without installing either tool.

## 5. Use the terminal instead

From the installed project folder on Windows:

```powershell
.venv/Scripts/python.exe -m terraforma.cli --version
.venv/Scripts/python.exe -m terraforma.cli doctor --require web
.venv/Scripts/python.exe -m terraforma.cli wizard --dir ./output/first-project
```

On macOS/Linux replace the interpreter path with `.venv/bin/python`. The wizard asks the configuration questions in the terminal and writes into a fresh directory. It refuses to overwrite an existing Terraform project; cancellation writes nothing.

`doctor` checks installed Python packages and executable availability without contacting cloud accounts. It does not establish tool trust, authentication or deployment readiness. After optional native-tool installation, validate trusted files with:

```powershell
.venv/Scripts/python.exe -m terraforma.cli run --dir ./output/first-project --no-ai
```

## Before using a project in a cloud account

Review the generated README and inputs, configure the selected provider's [authentication](CLOUD_AUTHENTICATION.md), and protect Terraform state and plan artifacts. Obtain your organization's normal change approval and review a Terraform plan outside TerraForma before provisioning.

TerraForma currently does not run plan, apply or destroy. Resources created through external tools can incur charges; private resources also need an appropriate access path. Secret variables marked sensitive can still appear in state or plan files. The [security overview](SECURITY_OVERVIEW.md) and [state protection guide](STATE_PROTECTION.md) describe these responsibilities.

For the development VM workflow, use [six synthetic examples](../examples/vm/README.md) with a development installation. Their account references and demonstration keys must be replaced and reviewed before any live use. Dedicated-account creation, login, initialization and cleanup evidence remain pending for v0.4.0.

## Troubleshooting

| Symptom | Next step |
| --- | --- |
| Python or Git is not recognized | Install the prerequisite or correct PATH, then open a new terminal. Confirm the version before retrying. |
| `python3 -m venv` is unavailable | Install your operating system's Python virtual-environment support, then retry environment creation. |
| `terraforma` is not recognized | Use the full `.venv` interpreter command shown above; activation is not required. |
| Installation cannot reach the package index | Check the approved proxy/index settings and network access; use your organization's normal package source. |
| The browser cannot connect | Keep the server running, check its displayed port and open the exact local address. |
| Port 8765 is busy | Use `serve --port 8766` and open the matching address. |
| A tool is shown as not installed | Verify its executable is on PATH in a new terminal, then restart the server. |
| Provider initialization fails | Check network/proxy settings, registry availability and disk space. Follow [validation troubleshooting](VALIDATION.md). |
| Another validation is running | Wait for it to finish; one native check pipeline runs at a time. |
| A local request is rejected after restart | Refresh the page to obtain the new process's session token. |
| An output directory is rejected | Choose a fresh directory and preserve the previous project. |
| Planning needs a missing variable | Read `variables.tf` and the exported README; supply the required input through Terraform's variable mechanisms. |

Need help? Include your operating system, installed version and sanitized reproduction steps in an issue. Use [private security reporting](../SECURITY.md) for suspected vulnerabilities.
