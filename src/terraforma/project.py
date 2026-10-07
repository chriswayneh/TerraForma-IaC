import ipaddress
import json
import re
from pathlib import Path
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from terraforma.generator import TerraformGenerator, WizardConfig
from terraforma.plan_review import reject_constant, unique_object


class ProjectSpecification(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    schema_version: Literal[1] = 1
    template_version: Literal["0.2.0"] = "0.2.0"
    recipe: WizardConfig
    inputs: dict[str, str] = Field(default_factory=dict, max_length=32)
    secret_references: dict[str, str] = Field(default_factory=dict, max_length=16)


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
                    "gcp_project_id": "Google Cloud project ID",
                    "subscription_id": "Azure subscription ID",
                    "ssh_public_key": "Administrator SSH public key",
                    "database_client_ip": "Database client IPv4 address",
                    "index_html": "Website HTML",
                }.get(name, name.replace("_", " ").capitalize()),
                "description": attributes["description"],
                "type": "string",
                "kind": "external_secret" if sensitive else kind,
                "required": "default" not in attributes,
                "default": None if sensitive else attributes.get("default"),
                "sensitive": sensitive,
                "editable": name != "project_name",
                "environment_variable": f"TF_VAR_{name}" if sensitive else None,
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
    elif name in {"region", "location", "zone", "instance_type"}:
        if not re.fullmatch(r"[a-z][a-z0-9.-]{1,63}", value):
            raise ValueError("Region, zone, or machine-size identifier has an invalid format.")
    elif name == "gcp_project_id" and not re.fullmatch(r"[a-z][a-z0-9-]{4,28}[a-z0-9]", value):
        raise ValueError(
            "Google Cloud project ID must use 6–30 lowercase letters, digits, or hyphens."
        )


def compile_project(specification: ProjectSpecification) -> dict:
    contract = input_contract(specification.recipe)
    definitions = {item["name"]: item for item in contract}
    for name, value in specification.inputs.items():
        definition = definitions.get(name)
        if definition is None or definition["sensitive"] or not definition["editable"]:
            raise ValueError("Project input is unsupported, secret, or controlled by the recipe.")
        validate_input(name, value, definition["kind"])
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
