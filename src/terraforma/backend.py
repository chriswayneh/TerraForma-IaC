import hashlib
import ipaddress
import re
from pathlib import Path
from typing import Annotated, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, TypeAdapter, ValidationError, field_validator

from terraforma.file_input import read_regular_bytes
from terraforma.json_input import strict_json

MAX_BACKEND_BYTES = 16 * 1024


class BackendIntent(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    schema_version: Literal[1] = 1
    owner: str = Field(min_length=1, max_length=80, pattern=r"^[A-Za-z0-9][A-Za-z0-9_.-]*$")
    environment: str = Field(min_length=1, max_length=32, pattern=r"^[a-z][a-z0-9-]*$")

    @field_validator("schema_version", mode="before")
    @classmethod
    def exact_version(cls, value):
        if type(value) is not int or value != 1:
            raise ValueError("Backend schema version must be the integer 1.")
        return value


def object_location(value: str) -> str:
    if (
        len(value) > 512
        or not re.fullmatch(r"[A-Za-z0-9_.-]+(?:/[A-Za-z0-9_.-]+)*", value)
        or any(part in {".", ".."} for part in value.split("/"))
    ):
        raise ValueError("Use a bounded relative object location without traversal.")
    return value


def bucket_name(value: str) -> str:
    if not re.fullmatch(r"[a-z0-9][a-z0-9.-]{1,61}[a-z0-9]", value) or any(
        part in value for part in ("..", ".-", "-.")
    ):
        raise ValueError("Use a supported lowercase bucket name.")
    try:
        ipaddress.ip_address(value)
    except ValueError:
        return value
    raise ValueError("IP addresses are not supported bucket names.")


class S3BackendIntent(BackendIntent):
    backend: Literal["s3"]
    account_id: str = Field(pattern=r"^[0-9]{12}$")
    bucket: str
    region: str = Field(pattern=r"^[a-z]{2}(?:-[a-z]+)+-[1-9][0-9]*$")
    key: str
    use_lockfile: bool

    _bucket = field_validator("bucket")(bucket_name)
    _key = field_validator("key")(object_location)

    @field_validator("bucket")
    @classmethod
    def supported_s3_bucket(cls, value):
        if value.startswith(("xn--", "sthree-", "amzn-s3-demo-")) or value.endswith(
            ("-s3alias", "--ol-s3", ".mrap", "--x-s3", "--table-s3", "-an")
        ):
            raise ValueError("Use a supported general-purpose bucket name.")
        return value

    @field_validator("use_lockfile")
    @classmethod
    def locking_required(cls, value):
        if value is not True:
            raise ValueError("The declared S3 backend must enable lockfile use.")
        return value


class AzureBackendIntent(BackendIntent):
    backend: Literal["azurerm"]
    tenant_id: str
    subscription_id: str
    storage_account_name: str = Field(pattern=r"^[a-z0-9]{3,24}$")
    container_name: str = Field(pattern=r"^[a-z0-9][a-z0-9-]{1,61}[a-z0-9]$")
    key: str

    _key = field_validator("key")(object_location)

    @field_validator("tenant_id", "subscription_id")
    @classmethod
    def canonical_uuid(cls, value):
        if str(UUID(value)) != value.lower():
            raise ValueError("Use a canonical UUID reference.")
        return value.lower()

    @field_validator("container_name")
    @classmethod
    def no_consecutive_hyphens(cls, value):
        if "--" in value:
            raise ValueError("Consecutive container-name hyphens are unsupported.")
        return value


class GCSBackendIntent(BackendIntent):
    backend: Literal["gcs"]
    project_id: str = Field(pattern=r"^[a-z][a-z0-9-]{4,28}[a-z0-9]$")
    bucket: str
    prefix: str

    _bucket = field_validator("bucket")(bucket_name)
    _prefix = field_validator("prefix")(object_location)

    @field_validator("bucket")
    @classmethod
    def supported_gcs_bucket(cls, value):
        if value.startswith("goog") or any(reserved in value for reserved in ("google", "g00gle")):
            raise ValueError("Reserved bucket names are unsupported.")
        return value


BACKEND_ADAPTER = TypeAdapter(
    Annotated[
        S3BackendIntent | AzureBackendIntent | GCSBackendIntent, Field(discriminator="backend")
    ]
)


def backend_input_contract(backend: str) -> list[dict]:
    models = {"s3": S3BackendIntent, "azurerm": AzureBackendIntent, "gcs": GCSBackendIntent}
    if backend not in models:
        raise ValueError("Select a supported backend type.")
    labels = {
        "owner": "State owner identifier (team or operator)",
        "environment": "Environment label (lowercase)",
        "account_id": "AWS account ID for the existing state bucket",
        "bucket": "Existing state bucket name",
        "region": "Region of the existing state bucket",
        "key": "State file path within storage (for example, development/network/terraform.tfstate)",
        "use_lockfile": "Declare S3 lockfile use for future backend configuration",
        "tenant_id": "Azure tenant ID for state storage",
        "subscription_id": "Azure subscription ID for state storage",
        "storage_account_name": "Existing Azure storage account name",
        "container_name": "Existing Azure blob container name",
        "project_id": "Google Cloud project ID for state storage",
        "prefix": "State storage prefix (for example, development/network)",
    }
    return [
        {
            "name": name,
            "label": labels[name],
            "kind": "boolean" if field.annotation is bool else "text",
            "default": True
            if field.annotation is bool
            else "development"
            if name == "environment"
            else "",
            "sensitive": False,
            "required": True,
        }
        for name, field in models[backend].model_fields.items()
        if name not in {"schema_version", "backend"}
    ]


def validate_backend_answer(
    backend: str, answers: dict, field: str, value: str | bool
) -> bool | str:
    if field not in {item["name"] for item in backend_input_contract(backend)}:
        return "Choose a supported backend input."
    try:
        BACKEND_ADAPTER.validate_python({**answers, "backend": backend, field: value})
    except ValidationError as error:
        if any(item["loc"][-1] == field for item in error.errors()):
            return "Enter a supported non-secret reference in the documented format."
    return True


def parse_backend(raw: bytes) -> S3BackendIntent | AzureBackendIntent | GCSBackendIntent:
    if len(raw) > MAX_BACKEND_BYTES:
        raise ValueError("Backend intent exceeds the supported byte limit.")
    return BACKEND_ADAPTER.validate_python(strict_json(raw))


def review_backend(raw: bytes) -> dict:
    intent = parse_backend(raw)
    return {
        "schema_version": 1,
        "backend": intent.backend,
        "artifact_sha256": hashlib.sha256(raw).hexdigest(),
        "status": "inputs_valid_verification_required",
        "backend_configured": False,
        "identity_verified": False,
        "approval_granted": False,
        "required_reviews": [
            "Backend and workload authentication must be verified separately.",
            "Confirm state ownership and a unique state location for this environment.",
            "Verify storage access, encryption and encryption-key recovery.",
            "Verify Terraform compatibility and actual lock contention behavior.",
            "Test version retention, backup restoration and migration recovery.",
        ],
    }


def load_and_review_backend(path: Path) -> dict:
    return review_backend(read_regular_bytes(path, MAX_BACKEND_BYTES))
