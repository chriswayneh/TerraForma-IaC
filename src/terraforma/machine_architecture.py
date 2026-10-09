import re

from terraforma.hcl import block, ref, value_hcl

MACHINE_SIZE_FIELDS = {"aws": "instance_type", "azure": "vm_size", "gcp": "machine_type"}
KNOWN_ARM_PATTERNS = {
    "aws": r"^(t4g|m6g|m6gd|m7g|m7gd|m8g|m8gb|m8gd|m8gn|m9g|m9gd|c6g|c6gd|c6gn|c7g|c7gd|c7gn|c8g|c8gb|c8gd|c8gn|c9g|c9gd|r6g|r6gd|r7g|r7gd|r8g|r8gb|r8gd|r8gn|r9g|r9gd|x2gd|x8g|i4g|i8g|i8ge|im4gn|is4gen|g5g|p6e-gb200)\.",
    "azure": r"(?i)^Standard_[A-Z][A-Za-z]*[0-9]+(-[0-9]+)?[a-z]*p[a-z]*(_[A-Za-z0-9]+)*$",
    "gcp": r"^(t2a|c4a|n4a|a4x)-",
}
ARCHITECTURE_MESSAGE = (
    "This recipe requires an x86-64 machine size; the selected size identifies an unsupported Arm family. "
    "Other sizes still require account-specific architecture, image and availability checks."
)


def validate_machine_architecture(name: str, value: str) -> None:
    for provider, field in MACHINE_SIZE_FIELDS.items():
        if name == field and re.search(KNOWN_ARM_PATTERNS[provider], value):
            raise ValueError(ARCHITECTURE_MESSAGE)


def machine_architecture_validation(provider: str):
    name = MACHINE_SIZE_FIELDS[provider]
    return block(
        "validation",
        condition=ref(f"!can(regex({value_hcl(KNOWN_ARM_PATTERNS[provider])}, var.{name}))"),
        error_message=ARCHITECTURE_MESSAGE,
    )
