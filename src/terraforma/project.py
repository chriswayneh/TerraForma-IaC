import base64
import binascii
import ipaddress
import re
from pathlib import Path
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator

from terraforma.artifacts import create_receipt
from terraforma.catalog import recipe_capabilities
from terraforma.generator import TerraformGenerator, WizardConfig
from terraforma.json_input import strict_json
from terraforma.network_inputs import usable_vm_address


class ProjectSpecification(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    schema_version: Literal[1] = 1
    template_version: Literal["0.3.0.dev0"] = "0.3.0.dev0"
    recipe: WizardConfig
    inputs: dict[str, str | int | bool] = Field(default_factory=dict, max_length=32)
    secret_references: dict[str, str] = Field(default_factory=dict, max_length=16)

    @field_validator("schema_version", mode="before")
    @classmethod
    def exact_schema_version(cls, value):
        if type(value) is not int or value != 1:
            raise ValueError("Schema version must be the integer 1.")
        return value


class ProjectInputError(ValueError):
    def __init__(self, field: str, message: str):
        self.field = field
        super().__init__(f"{field}: {message}")


def input_contract(config: WizardConfig) -> list[dict]:
    generator = TerraformGenerator(config)
    generator.generate()
    contract = []
    for variable in generator.variables:
        attributes = variable.attributes
        name = variable.labels[0]
        sensitive = attributes.get("sensitive", False)
        kind = {
            "ssh_public_key": "ssh_public_key",
            "allowed_cidr": "ipv4_cidr",
            "network_cidr": "ipv4_cidr",
            "database_client_ip": "ipv4_address",
            "private_ip_address": "optional_ipv4_address",
            "subscription_id": "uuid",
            "index_html": "multiline",
        }.get(name, "text")
        contract.append(
            {
                "name": name,
                "label": {
                    "allowed_cidr": "Allowed client network (CIDR)",
                    "network_cidr": "New network address range (CIDR)",
                    "private_ip_address": "Private IPv4 address (optional)",
                    "instance_type": "VM size",
                    "vm_size": "VM size",
                    "machine_type": "VM size",
                    "instance_count": "Number of web VMs",
                    "os_image": "Linux operating system",
                    "image_version": "Azure image version (latest or exact version)"
                    if config.provider == "azure"
                    else "AWS image version (latest or AMI ID)"
                    if config.provider == "aws"
                    else "GCP image version (latest or exact image name)",
                    "admin_username": "Administrator username",
                    "detailed_monitoring": "Enable detailed EC2 monitoring",
                    "protect_vm": "Protect this VM from accidental deletion",
                    "enable_secure_boot": "Verify signed boot components (Secure Boot)",
                    "enable_boot_diagnostics": "Capture Azure boot diagnostics",
                    "enable_accelerated_networking": "Enable Azure accelerated networking",
                    "enable_data_disk": "Attach a data disk",
                    "data_disk_size_gb": "Data disk size (GiB)",
                    "data_disk_type": "Data disk type",
                    "enable_workload_identity": "Enable workload identity",
                    "workload_identity": "Existing IAM instance profile name"
                    if config.provider == "aws"
                    else "Existing service account email",
                    "boot_disk_size_gb": "Boot disk size (GiB)",
                    "boot_disk_type": "Boot disk type",
                    "gcp_project_id": "Google Cloud project ID",
                    "subscription_id": "Azure subscription ID",
                    "aws_account_id": "Target AWS account ID",
                    "environment": "Environment label",
                    "ssh_public_key": "Administrator SSH public key (Ed25519 or RSA)",
                    "database_client_ip": "Database client IPv4 address",
                    "index_html": "Website HTML",
                }.get(name, name.replace("_", " ").capitalize()),
                "description": attributes["description"],
                "type": attributes["type"].value,
                "kind": "external_secret"
                if sensitive
                else "boolean"
                if attributes["type"].value == "bool"
                else "integer"
                if attributes["type"].value == "number"
                else kind,
                "required": "default" not in attributes,
                "default": None if sensitive else attributes.get("default"),
                "sensitive": sensitive,
                "editable": name != "project_name",
                "environment_variable": f"TF_VAR_{name}" if sensitive else None,
                **generator.input_constraints[name],
            }
        )
    return contract


def validate_ssh_public_key(value: str) -> None:
    parts = value.split(" ", 2)
    if len(parts) < 2 or parts[0] not in {"ssh-ed25519", "ssh-rsa"}:
        raise ValueError("Use an OpenSSH Ed25519 or RSA public key for this recipe.")
    try:
        encoded = parts[1]
        raw = base64.b64decode(encoded + "=" * (-len(encoded) % 4), validate=True)
        if base64.b64encode(raw).decode().rstrip("=") != encoded.rstrip("="):
            raise ValueError("Noncanonical public-key encoding.")
        offset = 0
        fields = []
        for _ in range(2 if parts[0] == "ssh-ed25519" else 3):
            if len(raw) - offset < 4:
                raise ValueError("Incomplete public key.")
            size = int.from_bytes(raw[offset : offset + 4], "big")
            offset += 4
            if not size or size > len(raw) - offset:
                raise ValueError("Incomplete public-key field.")
            fields.append(raw[offset : offset + size])
            offset += size
        if offset != len(raw) or fields[0] != parts[0].encode("ascii"):
            raise ValueError("Mismatched public-key structure.")
        if parts[0] == "ssh-ed25519":
            if len(fields[1]) != 32:
                raise ValueError("Ed25519 public keys require 32 bytes.")
        else:
            for integer in fields[1:]:
                if integer[0] & 128 or (
                    len(integer) > 1 and integer[0] == 0 and not integer[1] & 128
                ):
                    raise ValueError("Invalid RSA integer encoding.")
            exponent, modulus = (int.from_bytes(item, "big") for item in fields[1:])
            if exponent < 3 or exponent % 2 == 0 or modulus.bit_length() < 2048 or modulus % 2 == 0:
                raise ValueError(
                    "RSA keys require an odd exponent and at least a 2048-bit modulus."
                )
    except (ValueError, binascii.Error):
        raise ValueError(
            "Public-key structure is invalid or unsupported; supply a valid OpenSSH public key."
        ) from None


def validate_input(name: str, value: str, kind: str):
    if kind == "optional_ipv4_address" and value == "":
        return
    if not value or len(value.encode("utf-8")) > 16384:
        raise ValueError("Input must be nonempty and at most 16 KiB.")
    if re.search(r"-----BEGIN [A-Z ]*PRIVATE KEY-----", value):
        raise ValueError("Private keys cannot be stored as project inputs.")
    if kind != "multiline" and any(ord(char) < 32 for char in value):
        raise ValueError("Single-line inputs cannot contain control characters.")
    if kind == "ipv4_cidr":
        ipaddress.IPv4Network(value, strict=True)
    elif kind in {"ipv4_address", "optional_ipv4_address"}:
        ipaddress.IPv4Address(value)
    elif kind == "uuid":
        UUID(value)
    elif kind == "ssh_public_key":
        validate_ssh_public_key(value)
    elif name == "vm_size":
        if not re.fullmatch(r"[A-Za-z][A-Za-z0-9_-]{1,63}", value):
            raise ValueError("Azure VM-size identifier has an invalid format.")
    elif name in {"region", "location", "zone", "instance_type", "machine_type"}:
        if not re.fullmatch(r"[a-z][a-z0-9.-]{1,63}", value):
            raise ValueError("Region, zone, or machine-size identifier has an invalid format.")
    elif name == "gcp_project_id" and not re.fullmatch(r"[a-z][a-z0-9-]{4,28}[a-z0-9]", value):
        raise ValueError(
            "Google Cloud project ID must use 6–30 lowercase letters, digits, or hyphens."
        )


def validate_answer(definition: dict, value: str | int | bool) -> None:
    try:
        _validate_answer(definition, value)
    except (ValueError, TypeError):
        if definition["kind"] == "boolean":
            message = "Choose enabled or disabled; this input requires a JSON true or false value."
        elif definition["kind"] == "integer":
            message = (
                f"Enter a whole number from {definition['minimum']} to {definition['maximum']}."
            )
        elif definition.get("network_policy") == "vm_network":
            message = f"Enter an RFC1918 private IPv4 network with a /{definition['prefix_minimum']} through /{definition['prefix_maximum']} prefix and no host bits."
        elif definition.get("network_policy") == "database_cidr":
            message = "Enter an RFC1918 private subnet or an IPv4 /24 through /32 client network; prefer /32 for one client."
        elif definition.get("network_policy") == "administrator_cidr":
            message = "Enter an RFC1918 private subnet or a single IPv4 /32 administrator address."
        elif definition.get("network_policy") == "database_address":
            message = "Enter one client IPv4 address outside 0/8, loopback, and 224/3; Azure-wide service access is unsupported."
        elif definition.get("required_when"):
            message = "Enter the existing identity reference in the documented provider format; credentials and keys are unsupported."
        elif definition["choices"]:
            message = "Choose one of: " + ", ".join(definition["choices"]) + "."
        elif definition["name"] == "aws_account_id":
            message = "Enter the 12-digit target AWS account ID."
        elif definition["name"] == "admin_username":
            message = "Enter a non-reserved username using 3–32 lowercase letters, digits, underscores or hyphens; start with a letter and end with a letter or digit."
        else:
            message = {
                "ipv4_cidr": "Enter an IPv4 network in CIDR notation, with no host bits (for example, 10.0.0.0/16).",
                "ipv4_address": "Enter a valid IPv4 client address.",
                "optional_ipv4_address": "Enter a valid IPv4 address, or leave it blank for cloud allocation.",
                "uuid": "Enter a valid subscription UUID.",
                "ssh_public_key": "Enter a structurally valid OpenSSH Ed25519 or RSA public key; private keys are unsupported.",
            }.get(
                definition["kind"],
                "Enter a nonempty value in the field's documented format; private keys and control characters are unsupported.",
            )
        raise ProjectInputError(definition["name"], message) from None


def _validate_answer(definition: dict, value: str | int | bool) -> None:
    if definition["kind"] == "boolean":
        if type(value) is not bool:
            raise ValueError("This input requires a boolean.")
    elif definition["kind"] == "integer":
        if type(value) is not int or not definition["minimum"] <= value <= definition["maximum"]:
            raise ValueError("Numeric input is outside the supported whole-number range.")
    else:
        if not isinstance(value, str):
            raise TypeError("This input requires a string.")
        validate_input(definition["name"], value, definition["kind"])
        if definition["pattern"] and not re.fullmatch(definition["pattern"], value):
            raise ValueError("Input does not match the required identifier format.")
        if definition["choices"] and value not in definition["choices"]:
            raise ValueError("Input is not one of the supported choices.")
        if value in (definition.get("forbidden_values") or []):
            raise ValueError("This value is reserved by the provider.")
        if definition.get("network_policy") == "vm_network":
            network = ipaddress.IPv4Network(value, strict=True)
            if (
                str(network) != value
                or not definition["prefix_minimum"]
                <= network.prefixlen
                <= definition["prefix_maximum"]
                or not any(
                    network.subnet_of(ipaddress.IPv4Network(cidr))
                    for cidr in ("10.0.0.0/8", "172.16.0.0/12", "192.168.0.0/16")
                )
            ):
                raise ValueError("Use a supported canonical private network range.")
        elif definition.get("network_policy") in {"database_cidr", "administrator_cidr"}:
            network = ipaddress.IPv4Network(value, strict=True)
            private = any(
                network.subnet_of(ipaddress.IPv4Network(cidr))
                for cidr in ("10.0.0.0/8", "172.16.0.0/12", "192.168.0.0/16")
            )
            minimum_prefix = 32 if definition["network_policy"] == "administrator_cidr" else 24
            if network.prefixlen < minimum_prefix and not private:
                raise ValueError("Use an RFC1918 private network or an IPv4 /24 through /32.")
        elif definition.get("network_policy") == "database_address":
            first = int(value.split(".")[0])
            if first == 0 or first == 127 or first >= 224:
                raise ValueError(
                    "Use a supported client IPv4 address; broad Azure-service access is unsupported."
                )


def compile_project(specification: ProjectSpecification) -> dict:
    contract = input_contract(specification.recipe)
    definitions = {item["name"]: item for item in contract}
    for name, value in specification.inputs.items():
        definition = definitions.get(name)
        if definition is None or definition["sensitive"] or not definition["editable"]:
            raise ValueError("Project input is unsupported, secret, or controlled by the recipe.")
        validate_answer(definition, value)
    for name, reference in specification.secret_references.items():
        definition = definitions.get(name)
        if definition is None or not definition["sensitive"] or reference != f"TF_VAR_{name}":
            raise ValueError(
                "Secret references must identify the declared Terraform environment variable."
            )
    missing = [
        item["name"]
        for item in contract
        if item["required"] and not item["sensitive"] and item["name"] not in specification.inputs
    ]
    if missing:
        raise ProjectInputError(missing[0], "This required project input is missing.")
    required_secrets = [item["environment_variable"] for item in contract if item["sensitive"]]
    effective = {item["name"]: item["default"] for item in contract if item["default"] is not None}
    effective.update(specification.inputs)
    if (
        specification.recipe.provider == "gcp"
        and effective.get("image_version", "latest") != "latest"
    ):
        prefix = (
            "debian-12-bookworm-v" if effective["os_image"] == "debian-12" else "ubuntu-2404-noble"
        )
        if not effective["image_version"].startswith(prefix):
            raise ProjectInputError(
                "image_version",
                "Choose an exact image name matching the selected Linux operating system.",
            )
    if effective.get("private_ip_address") and not usable_vm_address(
        specification.recipe.provider,
        effective["network_cidr"],
        specification.recipe.is_public,
        effective["private_ip_address"],
    ):
        raise ProjectInputError(
            "private_ip_address",
            "Choose a usable private IPv4 address in the generated VM subnet, excluding provider-reserved addresses.",
        )
    for definition in contract:
        if (
            definition.get("required_when")
            and all(
                effective.get(name) == expected
                for name, expected in definition["required_when"].items()
            )
            and not effective.get(definition["name"])
        ):
            raise ProjectInputError(
                definition["name"], "This input is required when workload identity is enabled."
            )
    if (
        specification.recipe.provider == "gcp"
        and "zone" in effective
        and not effective["zone"].startswith(effective["region"] + "-")
    ):
        raise ProjectInputError(
            "zone", "Choose a zone that belongs to the selected Google Cloud region."
        )
    generator = TerraformGenerator(specification.recipe)
    files = generator.generate()
    for variable in generator.variables:
        if variable.labels[0] in specification.inputs:
            variable.attributes["default"] = specification.inputs[variable.labels[0]]
    files["variables.tf"] = (
        "\n\n".join(variable.render() for variable in generator.variables) + "\n"
    )
    return {
        "files": files,
        "receipt": create_receipt(specification.model_dump(), files),
        "specification": specification.model_dump(),
        "input_contract": contract,
        "choice_summary": choice_summary(contract, effective, specification.inputs),
        "capabilities": recipe_capabilities(specification.recipe),
        "target": {
            "provider": specification.recipe.provider,
            "account_reference": effective.get(
                {"aws": "aws_account_id", "azure": "subscription_id", "gcp": "gcp_project_id"}[
                    specification.recipe.provider
                ]
            ),
            "identity_verified": False,
            "environment": effective["environment"],
        },
        "required_secret_environment_variables": required_secrets,
        "verification": "Generated offline. Account permissions, region/image/SKU availability, quotas, and deployment remain unverified.",
    }


def choice_summary(contract: list[dict], effective: dict, supplied: dict) -> list[dict]:
    choices = []
    for definition in contract:
        name = definition["name"]
        if definition.get("visible_when") and any(
            effective.get(field) != expected
            for field, expected in definition["visible_when"].items()
        ):
            continue
        value = effective.get(name)
        source = "answer" if name in supplied else "default"
        if definition["sensitive"]:
            display = "Supplied externally through " + definition["environment_variable"]
            source = "external"
        elif name == "ssh_public_key":
            display = "SSH public key provided"
        elif name == "index_html":
            display = "Website page content provided"
        elif name == "private_ip_address" and value == "":
            display = "Allocated by the cloud provider"
        elif type(value) is bool:
            display = "Enabled" if value else "Disabled"
        else:
            display = " ".join(str(value).splitlines())
            display = "".join(char for char in display if char.isprintable())
            if len(display) > 120:
                display = display[:117] + "..."
        if not definition["editable"] and not definition["sensitive"]:
            source = "recipe"
        choices.append(
            {"name": name, "label": definition["label"], "value": display, "source": source}
        )
    return choices


def load_specification(path: Path) -> ProjectSpecification:
    with path.open("rb") as stream:
        raw = stream.read(64 * 1024 + 1)
    return parse_specification(raw)


def parse_specification(raw: bytes) -> ProjectSpecification:
    if len(raw) > 64 * 1024:
        raise ValueError("Project specification exceeds the 64 KiB limit.")
    return ProjectSpecification.model_validate(strict_json(raw))
