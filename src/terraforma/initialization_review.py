VM_FIELDS = {
    "aws_instance": ("user_data", "user_data_base64"),
    "aws_launch_template": ("user_data",),
    "aws_launch_configuration": ("user_data",),
    "azurerm_linux_virtual_machine": ("custom_data",),
    "azurerm_windows_virtual_machine": ("custom_data",),
    "google_compute_instance": ("metadata_startup_script",),
    "google_compute_instance_template": ("metadata_startup_script",),
}
GCP_TYPES = {"google_compute_instance", "google_compute_instance_template"}
STARTUP_KEYS = {
    "startup-script",
    "startup-script-url",
    *{f"windows-startup-script-{kind}" for kind in ("ps1", "cmd", "bat", "url")},
    *{f"sysprep-specialize-script-{kind}" for kind in ("ps1", "cmd", "bat", "url")},
}


def script_present(resource_type, values):
    if values is None:
        return False
    if not isinstance(values, dict):
        raise TypeError("Resource values must be an object.")
    present = False
    for field in VM_FIELDS[resource_type]:
        value = values.get(field)
        if value is not None and not isinstance(value, str):
            raise TypeError("Initialization fields must contain text.")
        present = present or bool(value)
    if resource_type in GCP_TYPES:
        metadata = values.get("metadata")
        if metadata is not None and not isinstance(metadata, dict):
            raise TypeError("Metadata must be an object.")
        for key in STARTUP_KEYS:
            value = (metadata or {}).get(key)
            if value is not None and not isinstance(value, str):
                raise TypeError("Startup metadata must contain text.")
            present = present or bool(value)
    return present


def script_unknown(resource_type, markers):
    if not isinstance(markers, dict):
        raise TypeError("Unknown markers must be an object.")
    unknown = False
    for field in VM_FIELDS[resource_type]:
        marker = markers.get(field, False)
        if type(marker) is not bool:
            raise TypeError("Unknown script markers must be boolean.")
        unknown = unknown or marker
    if resource_type in GCP_TYPES:
        metadata = markers.get("metadata", False)
        if type(metadata) is bool:
            return unknown or metadata
        if not isinstance(metadata, dict):
            raise TypeError("Unknown metadata markers must be boolean or an object.")
        for key in STARTUP_KEYS:
            marker = metadata.get(key, False)
            if type(marker) is not bool:
                raise TypeError("Unknown startup markers must be boolean.")
            unknown = unknown or marker
    return unknown


def initialization_findings(resource_type, change):
    if resource_type == "azurerm_virtual_machine_extension":
        return [
            (
                "guest_extension_review",
                "review",
                "A guest extension can execute privileged operations. Review its publisher, handler, public/protected settings, dependencies, identity and repeat behavior independently. Extension contents are not inspected or approved.",
            )
        ]
    if resource_type not in VM_FIELDS:
        return []
    present = script_present(resource_type, change["after"])
    previous = script_present(resource_type, change.get("before"))
    unknown = script_unknown(resource_type, change.get("after_unknown", {}))
    findings = []
    if unknown:
        findings.append(
            (
                "guest_initialization_unknown",
                "review",
                "Guest initialization inputs are unresolved. Review the exact payload, privileges, dependencies, repeat/replacement behavior and secret exposure when values become available.",
            )
        )
    if present:
        findings.append(
            (
                "guest_initialization_review",
                "review",
                "Guest initialization content or a reference is present. Review privileged execution, dependency sources, repeat/replacement behavior and state/metadata exposure independently. Script contents are not inspected, executed or approved.",
            )
        )
    elif previous and not unknown:
        findings.append(
            (
                "guest_initialization_removed",
                "review",
                "Previously declared guest initialization is being removed. Removing a payload does not undo guest changes; review replacement, retained applications and recovery separately.",
            )
        )
    return findings
