import re
from pathlib import Path

from terraforma.file_input import read_regular_bytes
from terraforma.hcl import block, ref, value_hcl

MAXIMUM_SCRIPT_BYTES = 4096
SCRIPT_CONTROLS = r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]"


def validate_initialization_script(script):
    if not isinstance(script, str) or len(script.encode("utf-8")) > MAXIMUM_SCRIPT_BYTES:
        raise ValueError("Use a UTF-8 initialization script no larger than 4 KiB.")
    if re.search(SCRIPT_CONTROLS, script) or "\ufffd" in script:
        raise ValueError(
            "Initialization scripts cannot contain unsupported control characters or invalid text."
        )


def read_initialization_file(path):
    data = read_regular_bytes(Path(path), MAXIMUM_SCRIPT_BYTES)
    if len(data) > MAXIMUM_SCRIPT_BYTES:
        raise ValueError("Use a UTF-8 initialization file no larger than 4 KiB.")
    script = data.decode("utf-8-sig")
    validate_initialization_script(script)
    return script


def declare_initialization(builder):
    windows = builder.config.architecture_type == "windows_virtual_machine"
    mechanism = {
        "aws": "EC2 user data requests first-boot execution by the image's launch agent. Changing a configured payload requests VM replacement and can delete boot data. Disabling this option does not establish removal of existing EC2 user data; inspect the plan and cloud metadata independently.",
        "azure": "A Windows Custom Script Extension runs as LocalSystem after guest-agent readiness. Script changes can rerun the extension; no storage credentials or script download URLs are configured."
        if windows
        else "Cloud-init processes custom data during provisioning. Guest-agent/image support is required; changing custom data replaces the VM and can delete boot data.",
        "gcp": "The Google guest environment processes startup metadata on boots. Scripts must be safe to repeat; startup timing and successful completion remain unverified.",
    }[builder.config.provider]
    builder.variable(
        "enable_initialization",
        "Include one reviewed local initialization script. It will run with root/administrator privileges on a future deployment, never on this computer during generation. "
        + mechanism
        + " Script text is stored in project exports, Terraform configuration/state and guest metadata or extension settings. Keep secrets external; base64 is not encryption. Generation does not inspect dependencies, prove script safety or verify guest execution.",
        False,
        type_name="bool",
    )
    builder.variable(
        "initialization_script",
        "Reviewed UTF-8 PowerShell script content, at most 4 KiB. Supply raw PowerShell, without EC2 XML wrappers or persistence tags."
        if windows
        else "Reviewed UTF-8 shell script content, at most 4 KiB. Start with #!/bin/bash or #!/bin/sh on its own line. Cloud-config, multipart payloads and remote script references are unsupported.",
        "",
        visible_when={"enable_initialization": True},
        required_when={"enable_initialization": True},
    )
    builder.variables[-1].children.append(
        block(
            "validation",
            condition=ref(
                'length(base64encode(var.initialization_script)) * 3 / 4 - length(regexall("=", base64encode(var.initialization_script))) <= 4096 && '
                f"length(regexall({value_hcl(SCRIPT_CONTROLS)}, var.initialization_script)) == 0 && "
                '!strcontains(var.initialization_script, "�") && '
                'length(regexall("-----BEGIN [A-Z ]*PRIVATE KEY-----", var.initialization_script)) == 0'
            ),
            error_message="Use at most 4 KiB of UTF-8 script content without private keys, replacement characters or unsupported control characters.",
        )
    )
    builder.variable(
        "confirm_initialization_review",
        "I reviewed this exact script, its sources, dependencies, elevated privileges, repeat behavior and replacement effects. It contains no embedded credentials or personal information and does not require interactive input. This declaration does not verify safety, grant cloud access or approve deployment.",
        False,
        type_name="bool",
        visible_when={"enable_initialization": True},
    )


def initialization_precondition(windows):
    shell_pattern = value_hcl(r"^#!/bin/(bash|sh)\r?\n")
    format_condition = (
        '!startswith(var.initialization_script, "#!") && length(regexall("(?i)<[ /]*(powershell|persist|script)[ >]", var.initialization_script)) == 0'
        if windows
        else f"can(regex({shell_pattern}, var.initialization_script))"
    )
    return block(
        "precondition",
        condition=ref(
            'var.enable_initialization ? (var.confirm_initialization_review && trimspace(var.initialization_script) != "" && '
            + format_condition
            + ') : (var.initialization_script == "" && !var.confirm_initialization_review)'
        ),
        error_message="Enabled initialization requires a reviewed script in the supported shell/PowerShell format. Clear inactive script content and review declarations when disabled.",
    )


def aws_initialization_payload(windows):
    return ref(
        'var.enable_initialization ? base64encode("<powershell>\\n${var.initialization_script}\\n</powershell>") : null'
        if windows
        else "var.enable_initialization ? base64encode(var.initialization_script) : null"
    )


def add_azure_windows_initialization(builder):
    command = (
        'powershell.exe -NoProfile -NonInteractive -Command "& { '
        "$ErrorActionPreference = 'Stop'; $s = [System.Text.Encoding]::UTF8.GetString([System.Convert]::FromBase64String('"
        + "${base64encode(var.initialization_script)}"
        + "')); & ([scriptblock]::Create($s)); if (-not $?) { exit 1 } }\""
    )
    encoded_command = value_hcl(command).replace("$${base64encode", "${base64encode")
    builder.resource(
        "azurerm_virtual_machine_extension",
        "initialization",
        count=ref("var.enable_initialization ? 1 : 0"),
        name="terraforma-initialization",
        virtual_machine_id=ref("azurerm_windows_virtual_machine.this.id"),
        publisher="Microsoft.Compute",
        type="CustomScriptExtension",
        type_handler_version="1.10",
        auto_upgrade_minor_version=True,
        protected_settings=ref(f"jsonencode({{ commandToExecute = {encoded_command} }})"),
        children=[block("lifecycle", children=[initialization_precondition(True)])],
    )
