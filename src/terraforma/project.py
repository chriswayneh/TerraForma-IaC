import ipaddress
import json
import re
from pathlib import Path
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator

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
                    "boot_disk_size_gb": "Boot disk size (GiB)",
                    "boot_disk_type": "Boot disk type",
                    "gcp_project_id": "Google Cloud project ID",
                    "subscription_id": "Azure subscription ID",
                    "ssh_public_key": "Administrator SSH public key",
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
        if not re.fullmatch(
            r"(?:ssh-ed25519|ssh-rsa|ecdsa-sha2-nistp(?:256|384|521)) [A-Za-z0-9+/]+={0,3}(?: [^\r\n]+)?",
            value,
        ):
            raise ValueError("Supply an OpenSSH public key, not a private key.")
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
    if definition["kind"] == "integer":
        if type(value) is not int or not definition["minimum"] <= value <= definition["maximum"]:
            raise ValueError("Numeric input is outside the supported whole-number range.")
    else:
        if not isinstance(value, str):
            raise TypeError("This input requires a string.")
        validate_input(definition["name"], value, definition["kind"])
        if definition["choices"] and value not in definition["choices"]:
            raise ValueError("Input is not one of the supported choices.")


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
        raise ValueError("Required project inputs are missing: " + ", ".join(missing))
    required_secrets = [item["environment_variable"] for item in contract if item["sensitive"]]
    effective = {item["name"]: item["default"] for item in contract if item["default"] is not None}
    effective.update(specification.inputs)
    if (
        specification.recipe.provider == "gcp"
        and "zone" in effective
        and not effective["zone"].startswith(effective["region"] + "-")
    ):
        raise ValueError("The selected Google Cloud zone must belong to the selected region.")
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
        "specification": specification.model_dump(),
        "input_contract": contract,
        "capabilities": recipe_capabilities(specification.recipe),
        "required_secret_environment_variables": required_secrets,
        "verification": "Generated offline. Account permissions, region/image/SKU availability, quotas, and deployment remain unverified.",
    }


def load_specification(path: Path) -> ProjectSpecification:
    with path.open("rb") as stream:
        raw = stream.read(64 * 1024 + 1)
    if len(raw) > 64 * 1024:
        raise ValueError("Project specification exceeds the 64 KiB limit.")
    return ProjectSpecification.model_validate(
        json.loads(raw, object_pairs_hook=unique_object, parse_constant=reject_constant)
    )
