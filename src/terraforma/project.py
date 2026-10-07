import base64
import binascii
import ipaddress
import json
import re
from pathlib import Path
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator

from terraforma.artifacts import create_receipt
from terraforma.catalog import recipe_capabilities
from terraforma.generator import TerraformGenerator, WizardConfig
from terraforma.plan_review import reject_constant, unique_object


class ProjectSpecification(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    schema_version: Literal[1] = 1
    template_version: Literal["0.3.0.dev0"] = "0.3.0.dev0"
    recipe: WizardConfig
    inputs: dict[str, str | int] = Field(default_factory=dict, max_length=32)
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
            "database_client_ip": "ipv4_address",
            "subscription_id": "uuid",
            "index_html": "multiline",
        }.get(name, "text")
        contract.append(
            {
                "name": name,
                "label": {
                    "allowed_cidr": "Allowed client network (CIDR)",
                    "instance_type": "VM size",
                    "vm_size": "VM size",
                    "machine_type": "VM size",
                    "instance_count": "Number of web VMs",
                    "os_image": "Linux operating system",
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
    if not value or len(value.encode("utf-8")) > 16384:
        raise ValueError("Input must be nonempty and at most 16 KiB.")
    if re.search(r"-----BEGIN [A-Z ]*PRIVATE KEY-----", value):
        raise ValueError("Private keys cannot be stored as project inputs.")
    if kind != "multiline" and any(ord(char) < 32 for char in value):
        raise ValueError("Single-line inputs cannot contain control characters.")
    if kind == "ipv4_cidr":
        ipaddress.IPv4Network(value, strict=True)
    elif kind == "ipv4_address":
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


def validate_answer(definition: dict, value: str | int) -> None:
    try:
        _validate_answer(definition, value)
    except (ValueError, TypeError):
        if definition["kind"] == "integer":
            message = (
                f"Enter a whole number from {definition['minimum']} to {definition['maximum']}."
            )
        elif definition.get("network_policy") == "database_cidr":
            message = "Enter an RFC1918 private subnet or an IPv4 /24 through /32 client network; prefer /32 for one client."
        elif definition.get("network_policy") == "administrator_cidr":
            message = "Enter an RFC1918 private subnet or a single IPv4 /32 administrator address."
        elif definition.get("network_policy") == "database_address":
            message = "Enter one client IPv4 address outside 0/8, loopback, and 224/3; Azure-wide service access is unsupported."
        elif definition["choices"]:
            message = "Choose one of: " + ", ".join(definition["choices"]) + "."
        elif definition["name"] == "aws_account_id":
            message = "Enter the 12-digit target AWS account ID."
        else:
            message = {
                "ipv4_cidr": "Enter an IPv4 network in CIDR notation, with no host bits (for example, 10.0.0.0/16).",
                "ipv4_address": "Enter a valid IPv4 client address.",
                "uuid": "Enter a valid subscription UUID.",
                "ssh_public_key": "Enter a structurally valid OpenSSH Ed25519 or RSA public key; private keys are unsupported.",
            }.get(
                definition["kind"],
                "Enter a nonempty value in the field's documented format; private keys and control characters are unsupported.",
            )
        raise ProjectInputError(definition["name"], message) from None


def _validate_answer(definition: dict, value: str | int) -> None:
    if definition["kind"] == "integer":
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
        if definition.get("network_policy") in {"database_cidr", "administrator_cidr"}:
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


def load_specification(path: Path) -> ProjectSpecification:
    with path.open("rb") as stream:
        raw = stream.read(64 * 1024 + 1)
    return parse_specification(raw)


def parse_specification(raw: bytes) -> ProjectSpecification:
    if len(raw) > 64 * 1024:
        raise ValueError("Project specification exceeds the 64 KiB limit.")
    return ProjectSpecification.model_validate(
        json.loads(
            raw.decode("utf-8-sig"), object_pairs_hook=unique_object, parse_constant=reject_constant
        )
    )
