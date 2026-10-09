import fnmatch
import hashlib
import re
from urllib.parse import urlsplit

from terraforma.project import input_contract


def metadata_text(data, key):
    value = data.get(key)
    if value is not None and (not isinstance(value, str) or not value):
        raise ValueError("Image metadata contains an unsupported text field.")
    return value


def metadata_object(data, key):
    value = data.get(key)
    if value is not None and not isinstance(value, dict):
        raise ValueError("Image metadata contains an unsupported object field.")
    return value


def metadata_list(data, key):
    value = data.get(key)
    if value is not None and not isinstance(value, list):
        raise ValueError("Image metadata contains an unsupported list field.")
    return value


def compatible(value, expected):
    return None if value is None else value == expected


def combine(*checks):
    return False if False in checks else None if None in checks else True


def disk_compatible(size, requested):
    if size is None:
        return None
    if isinstance(size, str) and re.fullmatch(r"[1-9][0-9]{0,18}", size):
        size = int(size)
    if type(size) is not int or size < 1:
        raise ValueError("Image metadata contains an unsupported disk size.")
    return requested >= size


def optional_boolean(data, key, expected):
    value = data.get(key)
    if value is not None and type(value) is not bool:
        raise ValueError("Image metadata contains an unsupported boolean field.")
    return None if value is None else value == expected


def purchase_plan_supported(data, key):
    plan = metadata_object(data, key)
    return True if plan is None else False if plan else None


def image_values(specification):
    values = {field["name"]: field["default"] for field in input_contract(specification.recipe)}
    values.update(specification.inputs)
    return values


def aws_catalog(image):
    return {
        "amazon-linux-2023": ("amazon", "al2023-ami-2023.*-x86_64"),
        "ubuntu-24.04": (
            "099720109477",
            "ubuntu/images/hvm-ssd-gp3/ubuntu-noble-24.04-amd64-server-*",
        ),
        "windows-server-2022": ("amazon", "Windows_Server-2022-English-Full-Base-*"),
        "windows-server-2022-core": ("amazon", "Windows_Server-2022-English-Core-Base-*"),
    }[image]


def azure_catalog(image):
    return {
        "ubuntu-22.04": ("Canonical", "0001-com-ubuntu-server-jammy", "22_04-lts-gen2"),
        "ubuntu-24.04": ("Canonical", "ubuntu-24_04-lts", "server"),
        "windows-server-2022": (
            "MicrosoftWindowsServer",
            "windowsserver2022",
            "2022-datacenter-g2",
        ),
        "windows-server-2022-core": (
            "MicrosoftWindowsServer",
            "windowsserver2022",
            "2022-datacenter-core-g2",
        ),
    }[image]


def gcp_catalog(image):
    return {
        "debian-12": ("debian-cloud", "debian-12", "debian-12-bookworm-v"),
        "ubuntu-24.04": ("ubuntu-os-cloud", "ubuntu-2404-lts-amd64", "ubuntu-2404-noble"),
        "windows-server-2022": ("windows-cloud", "windows-2022", "windows-server-2022-dc-v"),
        "windows-server-2022-core": (
            "windows-cloud",
            "windows-2022-core",
            "windows-server-2022-dc-core-v",
        ),
    }[image]


def aws_image_metadata(data, values, windows):
    images = metadata_list(data, "Images")
    if images is None or len(images) > 1:
        raise ValueError("Image selection must contain at most one image.")
    token = metadata_text(data, "NextToken")
    if token:
        return {"status": "selection_incomplete"}
    if not images:
        return {"status": "not_found", "available": False}
    image = images[0]
    if not isinstance(image, dict):
        raise TypeError("Selected image metadata must be an object.")
    identifier = metadata_text(image, "ImageId")
    if identifier and not re.fullmatch(r"ami-([0-9a-f]{8}|[0-9a-f]{17})", identifier):
        raise ValueError("Image identifier is unsupported.")
    custom = values.get("use_custom_image", False)
    requested = values["custom_image"] if custom else values["image_version"]
    source = (
        compatible(identifier, requested)
        if requested != "latest"
        else (True if identifier else None)
    )
    owner = metadata_text(image, "OwnerId")
    if owner is not None and not re.fullmatch(r"[0-9]{12}", owner):
        raise ValueError("Image ownership metadata is malformed.")
    if custom:
        source = combine(source, compatible(owner, values["custom_image_owner_account_id"]))
    else:
        expected_owner, pattern = aws_catalog(values["os_image"])
        owner_match = compatible(
            metadata_text(image, "ImageOwnerAlias") if expected_owner == "amazon" else owner,
            expected_owner,
        )
        name = metadata_text(image, "Name")
        source = combine(source, owner_match, fnmatch.fnmatchcase(name, pattern) if name else None)
    platform = image.get("Platform")
    if platform is not None and not isinstance(platform, str):
        raise TypeError("Image platform metadata must be text.")
    checks = {
        "available": compatible(metadata_text(image, "State"), "available"),
        "source_compatible": source,
        "architecture_compatible": compatible(metadata_text(image, "Architecture"), "x86_64"),
        "os_compatible": compatible(platform or None, "windows")
        if windows
        else platform in {None, ""},
        "deprecation_acceptable": not bool(metadata_text(image, "DeprecationTime")),
        "boot_type_compatible": combine(
            compatible(metadata_text(image, "RootDeviceType"), "ebs"),
            compatible(metadata_text(image, "VirtualizationType"), "hvm"),
        ),
    }
    root = metadata_text(image, "RootDeviceName")
    mappings = metadata_list(image, "BlockDeviceMappings")
    selected = []
    if mappings is not None:
        for mapping in mappings:
            if not isinstance(mapping, dict):
                raise TypeError("Image disk mappings must be objects.")
            device = metadata_text(mapping, "DeviceName")
            ebs = metadata_object(mapping, "Ebs")
            if root and device == root:
                selected.append(ebs)
        if len(selected) > 1:
            raise ValueError("Image root disk metadata is ambiguous.")
    checks["boot_disk_compatible"] = disk_compatible(
        selected[0].get("VolumeSize") if selected and selected[0] else None,
        values["boot_disk_size_gb"],
    )
    checks["additional_image_disks_supported"] = (
        None
        if mappings is None or root is None
        else not any(
            metadata_object(mapping, "Ebs") is not None and mapping.get("DeviceName") != root
            for mapping in mappings
        )
    )
    if "ImageAllowed" in image:
        checks["image_policy_compatible"] = optional_boolean(image, "ImageAllowed", True)
    if custom:
        public = image.get("Public")
        if public is not None and type(public) is not bool:
            raise ValueError("Image visibility metadata must be boolean.")
        codes = metadata_list(image, "ProductCodes")
        checks["private_image"] = compatible(public, False)
        checks["purchase_plan_supported"] = None if codes is None else not codes
    return image_result(checks, identifier)


def gcp_image_metadata(data, values, windows):
    custom = values.get("use_custom_image", False)
    if custom:
        parts = values["custom_image"].split("/")
        project, requested, family, prefix = parts[1], parts[-1], None, None
    else:
        project, family, prefix = gcp_catalog(values["os_image"])
        requested = values["image_version"]
    name = metadata_text(data, "name")
    if name is not None and not re.fullmatch(r"[a-z](?:[a-z0-9-]{0,61}[a-z0-9])?", name):
        raise ValueError("Image name metadata is malformed.")
    reference = metadata_text(data, "selfLink")
    if reference:
        uri = urlsplit(reference)
        if (
            uri.scheme != "https"
            or uri.netloc not in {"www.googleapis.com", "compute.googleapis.com"}
            or uri.query
            or uri.fragment
        ):
            raise ValueError("Image reference metadata is unsupported.")
        reference = uri.path.removeprefix("/compute/v1/")
    expected = f"projects/{project}/global/images/{name}" if name else None
    identity = compatible(reference, expected) if expected else None
    identity = combine(
        identity,
        compatible(name, requested)
        if requested != "latest"
        else (name.startswith(prefix) if name else None),
    )
    if not custom and requested == "latest":
        identity = combine(identity, compatible(metadata_text(data, "family"), family))
    features = metadata_list(data, "guestOsFeatures")
    feature_types = None
    if features is not None:
        if any(not isinstance(item, dict) or not metadata_text(item, "type") for item in features):
            raise ValueError("Image guest feature metadata is malformed.")
        feature_types = {item["type"] for item in features}
    deprecated = metadata_object(data, "deprecated")
    deprecation = metadata_text(deprecated, "state") if deprecated is not None else None
    if deprecated is not None and deprecation not in {None, "DEPRECATED", "OBSOLETE", "DELETED"}:
        raise ValueError("Image deprecation metadata is unsupported.")
    checks = {
        "available": compatible(metadata_text(data, "status"), "READY"),
        "source_compatible": identity,
        "architecture_compatible": compatible(metadata_text(data, "architecture"), "X86_64"),
        "os_compatible": None if feature_types is None else ("WINDOWS" in feature_types) == windows,
        "boot_disk_compatible": disk_compatible(
            data.get("diskSizeGb"), values["boot_disk_size_gb"]
        ),
        "deprecation_acceptable": True
        if deprecated is None
        else None
        if deprecation is None
        else False,
    }
    return image_result(checks, reference)


def azure_properties(data):
    properties = metadata_object(data, "properties")
    if properties is None:
        return data
    if any(
        key in data
        for key in (
            "architecture",
            "osType",
            "osState",
            "hyperVGeneration",
            "features",
            "replicationStatus",
            "provisioningState",
            "storageProfile",
            "purchasePlan",
            "plan",
            "osDiskImage",
            "dataDiskImages",
            "imageDeprecationStatus",
        )
    ):
        raise ValueError("Image metadata contains ambiguous property envelopes.")
    return properties


def azure_image_metadata(records, values, windows):
    custom = values.get("use_custom_image", False)
    if len(records) != (2 if custom else 1) or any(
        not isinstance(record, dict) for record in records
    ):
        raise ValueError("Image metadata records are incomplete.")
    version = records[0]
    props = azure_properties(version)
    os_type = "Windows" if windows else "Linux"
    if custom:
        definition = records[1]
        definition_props = azure_properties(definition)
        identifier = metadata_text(version, "id")
        definition_id = metadata_text(definition, "id")
        source = combine(
            None if identifier is None else identifier.lower() == values["custom_image"].lower(),
            None
            if definition_id is None
            else definition_id.lower() == values["custom_image"].rsplit("/versions/", 1)[0].lower(),
        )
        replication = metadata_object(props, "replicationStatus")
        summary = metadata_list(replication, "summary") if replication else None
        selected = []
        if summary is not None:
            for item in summary:
                if not isinstance(item, dict):
                    raise TypeError("Replication summaries must be objects.")
                region = metadata_text(item, "region")
                if region and region.replace(" ", "").lower() == values["location"]:
                    selected.append(metadata_text(item, "state"))
            if len(selected) > 1:
                raise ValueError("Image replication metadata is ambiguous.")
        features = metadata_list(definition_props, "features")
        security = []
        if features is not None:
            for item in features:
                if not isinstance(item, dict):
                    raise TypeError("Image feature metadata must contain objects.")
                if metadata_text(item, "name") == "SecurityType":
                    security.append(metadata_text(item, "value"))
            if len(security) > 1:
                raise ValueError("Image security type is ambiguous.")
        storage = metadata_object(props, "storageProfile")
        disk = metadata_object(storage, "osDiskImage") if storage else None
        checks = {
            "available": combine(
                compatible(metadata_text(props, "provisioningState"), "Succeeded"),
                compatible(selected[0], "Completed") if selected else None,
            ),
            "source_compatible": source,
            "architecture_compatible": compatible(
                metadata_text(definition_props, "architecture"), "x64"
            ),
            "os_compatible": compatible(metadata_text(definition_props, "osType"), os_type),
            "generalization_compatible": compatible(
                metadata_text(definition_props, "osState"), "Generalized"
            ),
            "boot_generation_compatible": compatible(
                metadata_text(definition_props, "hyperVGeneration"), "V2"
            ),
            "trusted_launch_compatible": compatible(security[0], "TrustedLaunchSupported")
            if security
            else None,
            "boot_disk_compatible": disk_compatible(
                disk.get("sizeInGB") if disk else None, values["boot_disk_size_gb"]
            ),
            "purchase_plan_supported": purchase_plan_supported(definition_props, "purchasePlan"),
            "additional_image_disks_supported": not bool(metadata_list(storage, "dataDiskImages"))
            if storage
            else None,
        }
    else:
        publisher, offer, sku = azure_catalog(values["os_image"])
        identifier = metadata_text(version, "id")
        prefix = f"/subscriptions/{values['subscription_id']}/providers/Microsoft.Compute/locations/{values['location']}/publishers/{publisher}/artifacttypes/vmimage/offers/{offer}/skus/{sku}/versions/"
        name = metadata_text(version, "name")
        if name is not None and not re.fullmatch(r"[0-9]{1,10}\.[0-9]{1,10}\.[0-9]{1,10}", name):
            raise ValueError("Image version metadata is malformed.")
        source = (
            None
            if identifier is None or name is None
            else identifier.lower() == (prefix + name).lower()
        )
        if values["image_version"] != "latest":
            source = combine(source, compatible(name, values["image_version"]))
        disk = metadata_object(props, "osDiskImage")
        deprecation = metadata_object(props, "imageDeprecationStatus")
        image_state = metadata_text(deprecation, "imageState") if deprecation is not None else None
        if image_state not in {None, "Active", "ScheduledForDeprecation", "Deprecated"}:
            raise ValueError("Image deprecation metadata is unsupported.")
        checks = {
            "available": True if name else None,
            "source_compatible": source,
            "architecture_compatible": compatible(metadata_text(props, "architecture"), "x64"),
            "os_compatible": compatible(metadata_text(disk, "operatingSystem"), os_type)
            if disk
            else None,
            "boot_generation_compatible": compatible(
                metadata_text(props, "hyperVGeneration"), "V2"
            ),
            "purchase_plan_supported": purchase_plan_supported(props, "plan"),
            "additional_image_disks_supported": not bool(metadata_list(props, "dataDiskImages")),
            "deprecation_acceptable": True
            if deprecation is None
            else compatible(image_state, "Active"),
            "boot_disk_compatible": None,
        }
    return image_result(checks, identifier)


def image_result(checks, identifier):
    return {
        "status": "incompatible"
        if False in checks.values()
        else "metadata_unknown"
        if None in checks.values()
        else "metadata_confirmed",
        **checks,
        "resolved_reference_sha256": hashlib.sha256(identifier.encode()).hexdigest()
        if identifier
        else None,
    }
