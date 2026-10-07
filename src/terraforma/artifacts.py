import hashlib
import json
from pathlib import Path
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from terraforma import __version__
from terraforma.plan_review import reject_constant, unique_object

ArtifactName = Literal["main.tf", "variables.tf", "outputs.tf", "terraforma.project.json"]
Digest = Annotated[str, Field(pattern=r"^[a-f0-9]{64}$")]
MAX_ARTIFACT_BYTES = 8 * 1024 * 1024


class GenerationReceipt(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    receipt_version: Literal[1] = 1
    generator_version: str = Field(min_length=1, max_length=64, pattern=r"^[a-zA-Z0-9.+-]+$")
    template_version: str = Field(min_length=1, max_length=64, pattern=r"^[a-zA-Z0-9.+-]+$")
    specification_sha256: Digest
    file_sha256: dict[ArtifactName, Digest] = Field(min_length=4, max_length=4)

    @field_validator("receipt_version", mode="before")
    @classmethod
    def exact_version(cls, value):
        if type(value) is not int or value != 1:
            raise ValueError("Receipt version must be the integer 1.")
        return value


def json_document(data: dict) -> str:
    return json.dumps(data, indent=2, sort_keys=True, ensure_ascii=False) + "\n"


def digest_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def create_receipt(specification: dict, files: dict[str, str]) -> dict:
    artifacts = {**files, "terraforma.project.json": json_document(specification)}
    canonical = json.dumps(specification, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return GenerationReceipt(
        generator_version=__version__,
        template_version=specification["template_version"],
        specification_sha256=digest_text(canonical),
        file_sha256={name: digest_text(content) for name, content in artifacts.items()},
    ).model_dump()


def project_artifacts(project: dict) -> dict[str, str]:
    return {
        **project["files"],
        "terraforma.project.json": json_document(project["specification"]),
        "terraforma.receipt.json": json_document(project["receipt"]),
    }


def checksum_document(files: dict[str, str]) -> str:
    return "".join(f"{digest_text(content)}  {name}\n" for name, content in sorted(files.items()))


def verify_project(directory: Path) -> dict:
    receipt_path = directory / "terraforma.receipt.json"
    if receipt_path.is_symlink() or not receipt_path.is_file():
        raise ValueError("A regular generation receipt is required.")
    with receipt_path.open("rb") as stream:
        raw = stream.read(64 * 1024 + 1)
    if len(raw) > 64 * 1024:
        raise ValueError("Generation receipt exceeds 64 KiB.")
    receipt = GenerationReceipt.model_validate(
        json.loads(
            raw.decode("utf-8-sig"), object_pairs_hook=unique_object, parse_constant=reject_constant
        )
    )
    results = []
    for name, expected in sorted(receipt.file_sha256.items()):
        path = directory / name
        status = "unreadable"
        try:
            if path.is_symlink() or not path.is_file():
                status = "missing_or_unsupported"
            else:
                digest = hashlib.sha256()
                total = 0
                with path.open("rb") as stream:
                    while chunk := stream.read(64 * 1024):
                        total += len(chunk)
                        if total > MAX_ARTIFACT_BYTES:
                            break
                        digest.update(chunk)
                status = (
                    "too_large"
                    if total > MAX_ARTIFACT_BYTES
                    else "match"
                    if digest.hexdigest() == expected
                    else "modified"
                )
        except OSError:
            pass
        results.append({"file": name, "status": status})
    return {
        "status": "matches_receipt"
        if all(item["status"] == "match" for item in results)
        else "mismatch",
        "files": results,
        "receipt_authenticated": False,
        "approval_granted": False,
        "limitations": "Unsigned local receipt. Matching hashes identify bytes against this receipt; they do not authenticate the receipt, verify a binary plan or cloud identity, certify security, or authorize deployment.",
    }
