import tempfile

from terraforma.image_metadata import (
    aws_catalog,
    aws_image_metadata,
    azure_catalog,
    azure_image_metadata,
    gcp_catalog,
    gcp_image_metadata,
    image_values,
)
from terraforma.json_input import strict_json
from terraforma.process import run_bounded


def image_commands(specification, executable):
    provider = specification.recipe.provider
    values = image_values(specification)
    custom = values.get("use_custom_image", False)
    if provider == "aws":
        owner, pattern = aws_catalog(values["os_image"])
        filters = [
            "Name=architecture,Values=x86_64",
            "Name=root-device-type,Values=ebs",
            "Name=virtualization-type,Values=hvm",
        ]
        if custom:
            owner = values["custom_image_owner_account_id"]
            filters.extend(
                [
                    f"Name=image-id,Values={values['custom_image']}",
                    "Name=is-public,Values=false",
                ]
            )
        else:
            filters.append(f"Name=name,Values={pattern}")
            if values["image_version"] != "latest":
                filters.append(f"Name=image-id,Values={values['image_version']}")
        return [
            [
                executable,
                "ec2",
                "describe-images",
                "--owners",
                owner,
                "--filters",
                *filters,
                "--region",
                values["region"],
                "--output",
                "json",
                "--no-cli-pager",
                "--no-paginate",
                "--max-results",
                "1000",
                "--query",
                "{Images: reverse(sort_by(Images, &CreationDate))[:1], NextToken: NextToken}",
            ]
        ]
    if provider == "azure":
        if custom:
            reference = values["custom_image"]
            return [
                [
                    executable,
                    "sig",
                    "image-version",
                    "show",
                    "--ids",
                    reference,
                    "--expand",
                    "ReplicationStatus",
                    "--output",
                    "json",
                    "--only-show-errors",
                ],
                [
                    executable,
                    "sig",
                    "image-definition",
                    "show",
                    "--ids",
                    reference.rsplit("/versions/", 1)[0],
                    "--output",
                    "json",
                    "--only-show-errors",
                ],
            ]
        publisher, offer, sku = azure_catalog(values["os_image"])
        return [
            [
                executable,
                "vm",
                "image",
                "show",
                "--urn",
                f"{publisher}:{offer}:{sku}:{values['image_version']}",
                "--location",
                values["location"],
                "--subscription",
                values["subscription_id"],
                "--output",
                "json",
                "--only-show-errors",
            ]
        ]
    if custom:
        parts = values["custom_image"].split("/")
        project, image, action = parts[1], parts[-1], "describe"
    else:
        project, family, _ = gcp_catalog(values["os_image"])
        action = "describe-from-family" if values["image_version"] == "latest" else "describe"
        image = family if action == "describe-from-family" else values["image_version"]
    return [
        [
            executable,
            "compute",
            "images",
            action,
            image,
            "--project",
            project,
            "--format=json",
            "--quiet",
        ]
    ]


def inspect_image(specification, executable, environment, timeout):
    records = []
    try:
        for arguments in image_commands(specification, executable):
            with tempfile.TemporaryDirectory(prefix="terraforma_image_preflight_") as directory:
                result = run_bounded(
                    arguments,
                    cwd=directory,
                    env=environment,
                    timeout=timeout,
                    stream_limit=128 * 1024,
                )
            if result.failure or result.returncode != 0:
                return {"status": "failed"}
            record = strict_json(result.stdout)
            if not isinstance(record, dict):
                return {"status": "invalid_response"}
            records.append(record)
        values = image_values(specification)
        windows = specification.recipe.architecture_type == "windows_virtual_machine"
        provider = specification.recipe.provider
        if provider == "aws":
            return aws_image_metadata(records[0], values, windows)
        if provider == "azure":
            return azure_image_metadata(records, values, windows)
        return gcp_image_metadata(
            records[0],
            values,
            windows,
            require_shielded=specification.recipe.architecture_type
            in {
                "virtual_machine",
                "windows_virtual_machine",
            },
        )
    except OSError:
        return {"status": "failed"}
    except (ValueError, TypeError, KeyError, IndexError, RecursionError):
        return {"status": "invalid_response"}


def image_machine_boot_check(image, machine):
    modes = ("legacy_bios_boot_supported", "uefi_boot_supported")
    outcomes = []
    for mode in modes:
        values = (image.get(mode), machine.get(mode))
        if any(value is not None and type(value) is not bool for value in values):
            return {"status": "invalid_response"}
        outcomes.append(False if False in values else None if None in values else True)
    compatible = True if True in outcomes else None if None in outcomes else False
    return {
        "status": "metadata_confirmed"
        if compatible
        else "metadata_unknown"
        if compatible is None
        else "incompatible",
        "boot_mode_compatible": compatible,
        "legacy_bios_fallback": (
            image.get("legacy_bios_boot_supported") is True
            and image.get("uefi_boot_supported") is True
            and machine.get("uefi_boot_supported") is False
            and machine.get("legacy_bios_boot_supported") is True
        ),
    }
