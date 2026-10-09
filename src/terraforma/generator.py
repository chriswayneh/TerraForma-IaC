import os
from pathlib import Path
from typing import Any, Literal

from terraforma.aws_network_attachment import (
    aws_attachment_precondition,
    declare_aws_network_attachment,
)
from terraforma.azure_identity import declare_azure_identity_inputs
from terraforma.azure_network_attachment import declare_azure_network_attachment
from terraforma.configuration import (
    AWS_CPU_CREDIT_PREFIXES,
    AZURE_RESERVED_USERNAMES,
    LINUX_IMAGE_CHOICES,
    WizardConfig,
)
from terraforma.custom_images import custom_image_preconditions, declare_custom_image_inputs
from terraforma.gcp_network_attachment import (
    declare_gcp_network_attachment,
    gcp_attachment_precondition,
)
from terraforma.hcl import Block, Expression, block, ref, value_hcl
from terraforma.initialization import declare_initialization, initialization_precondition
from terraforma.machine_architecture import MACHINE_SIZE_FIELDS, machine_architecture_validation
from terraforma.network_inputs import private_ip_condition
from terraforma.outbound import declare_outbound_access, outbound_precondition
from terraforma.providers.aws import build_aws
from terraforma.providers.azure import build_azure
from terraforma.providers.gcp import build_gcp
from terraforma.resource_labels import declare_resource_labels

__all__ = [
    "AZURE_RESERVED_USERNAMES",
    "GENERATED_FILENAMES",
    "LINUX_IMAGE_CHOICES",
    "Block",
    "Expression",
    "TerraformGenerator",
    "WizardConfig",
    "block",
    "project_destination",
    "ref",
    "value_hcl",
    "write_configuration",
]


class TerraformGenerator:
    def __init__(self, config: WizardConfig):
        self.config = config
        self.main: list[Block] = []
        self.variables: list[Block] = []
        self.outputs: list[Block] = []
        self.input_constraints: dict[str, dict] = {}

    def variable(
        self,
        name: str,
        description: str,
        default: Any = None,
        *,
        sensitive: bool = False,
        type_name: str = "string",
        minimum: int | None = None,
        maximum: int | None = None,
        prefix_minimum: int | None = None,
        prefix_maximum: int | None = None,
        visible_when: dict[str, bool | str] | None = None,
        required_when: dict[str, bool] | None = None,
        choices: tuple[str, ...] | None = None,
        pattern: str | None = None,
        forbidden_values: tuple[str, ...] | None = None,
        network_policy: Literal[
            "database_cidr", "database_address", "administrator_cidr", "vm_network"
        ]
        | None = None,
    ) -> None:
        attributes = {"description": description, "type": ref(type_name)}
        if default is not None:
            attributes["default"] = default
        if sensitive:
            attributes["sensitive"] = True
        validations = []
        if name == MACHINE_SIZE_FIELDS[self.config.provider]:
            validations.append(machine_architecture_validation(self.config.provider))
            attributes["description"] += (
                " This recipe requires x86-64; known Arm families are rejected. Other sizes remain unverified until account-specific checks."
            )
        if minimum is not None and maximum is not None:
            validations.append(
                block(
                    "validation",
                    condition=ref(
                        f"var.{name} >= {minimum} && var.{name} <= {maximum} && floor(var.{name}) == var.{name}"
                    ),
                    error_message=f"Use a whole number between {minimum} and {maximum}.",
                )
            )
        if choices:
            validations.append(
                block(
                    "validation",
                    condition=ref(f"contains({value_hcl(list(choices))}, var.{name})"),
                    error_message="Use a supported value: " + ", ".join(choices),
                )
            )
        if pattern:
            pattern_condition = f"can(regex({value_hcl(pattern)}, var.{name}))"
            if required_when:
                pattern_condition = f'var.{name} == "" || {pattern_condition}'
            validations.append(
                block(
                    "validation",
                    condition=ref(pattern_condition),
                    error_message="Use the required identifier format for this field.",
                )
            )
        if forbidden_values:
            validations.append(
                block(
                    "validation",
                    condition=ref(f"!contains({value_hcl(list(forbidden_values))}, var.{name})"),
                    error_message="Choose an administrator username outside the provider's reserved-name list.",
                )
            )
        if network_policy:
            address = f"var.{name}"
            if network_policy == "vm_network":
                prefix = f'tonumber(split("/", {address})[1])'
                network = f"cidrhost({address}, 0)"
                private_172 = value_hcl(r"^172\.(1[6-9]|2[0-9]|3[01])\.")
                condition = (
                    f"can(cidrnetmask({address})) && try("
                    f"{prefix} >= {prefix_minimum} && {prefix} <= {prefix_maximum} && "
                    f'format("%s/%d", {network}, {prefix}) == {address} && '
                    f'(startswith({network}, "10.") || '
                    f"can(regex({private_172}, {network})) || "
                    f'startswith({network}, "192.168.")), false)'
                )
                message = f"Use a canonical RFC1918 private IPv4 network with a /{prefix_minimum} through /{prefix_maximum} prefix, without host bits."
            elif network_policy in {"database_cidr", "administrator_cidr"}:
                public_prefix = 32 if network_policy == "administrator_cidr" else 24
                prefix = f'tonumber(split("/", {address})[1])'
                network = f"cidrhost({address}, 0)"
                private_172 = value_hcl(r"^172\.(1[6-9]|2[0-9]|3[01])\.")
                condition = (
                    f"can(cidrnetmask({address})) && try("
                    f"{prefix} >= {public_prefix} || "
                    f'(startswith({network}, "10.") && {prefix} >= 8) || '
                    f"(can(regex({private_172}, {network})) && {prefix} >= 12) || "
                    f'(startswith({network}, "192.168.") && {prefix} >= 16), false)'
                )
                message = "Use an RFC1918 private network or an IPv4 /24 through /32 client network; prefer /32 for one client."
                if network_policy == "administrator_cidr":
                    message = "Use an RFC1918 private subnet or a single IPv4 /32 administrator address. Public network ranges are unsupported."
            else:
                octet = f'tonumber(split(".", {address})[0])'
                condition = (
                    f'can(cidrnetmask(format("%s/32", {address}))) && '
                    f"try({octet} > 0 && {octet} < 224 && {octet} != 127, false)"
                )
                message = "Use a client IPv4 address outside 0/8, loopback, multicast, and reserved 224/3; 0.0.0.0 broad Azure-service access is unsupported."
            description += " " + message
            attributes["description"] = description
            validations.append(block("validation", condition=ref(condition), error_message=message))
        self.input_constraints[name] = {
            "minimum": minimum,
            "maximum": maximum,
            "prefix_minimum": prefix_minimum,
            "prefix_maximum": prefix_maximum,
            "choices": list(choices) if choices else None,
            "pattern": pattern,
            "forbidden_values": list(forbidden_values) if forbidden_values else None,
            "network_policy": network_policy,
            "visible_when": visible_when,
            "required_when": required_when,
        }
        self.variables.append(block("variable", name, children=validations, **attributes))

    def resource(
        self,
        kind: str,
        label: str = "this",
        *,
        children: list[Block] | None = None,
        **attributes: Any,
    ) -> None:
        self.main.append(block("resource", kind, label, children=children, **attributes))

    def output(self, name: str, expression: str, description: str) -> None:
        self.outputs.append(block("output", name, value=ref(expression), description=description))

    def generate(self) -> dict[str, str]:
        if self.main:
            raise RuntimeError("Create a new generator for each configuration.")
        provider = {"aws": "aws", "azure": "azurerm", "gcp": "google"}[self.config.provider]
        versions = {"aws": "~> 6.0", "azure": "~> 4.0", "gcp": "~> 7.0"}
        if (
            self.config.provider == "azure"
            and self.config.architecture_type == "windows_virtual_machine"
        ):
            versions["azure"] = "~> 4.81"
        providers = {
            provider: {"source": f"hashicorp/{provider}", "version": versions[self.config.provider]}
        }
        if self.config.architecture_type == "static_site" and self.config.provider != "aws":
            providers["random"] = {"source": "hashicorp/random", "version": "~> 3.0"}
        self.main.append(
            block(
                "terraform",
                required_version=">= 1.6, < 2.0",
                children=[block("required_providers", **providers)],
            )
        )
        self.variable("project_name", "Resource name prefix.", self.config.project_name)
        self.variable(
            "environment",
            {
                "aws": "Environment tag applied through AWS provider default tags to supported resources.",
                "azure": "Environment tag applied explicitly to the new resource group and supported generated resources. Azure does not inherit resource-group tags.",
                "gcp": "Environment label on generated compute, database, or storage resources that support labels.",
            }[self.config.provider]
            + " Use a distinct project name per environment; this label does not isolate state or change resource names.",
            "development",
            pattern=r"^[a-z][a-z0-9\-]{1,18}[a-z0-9]$",
        )
        if self.config.architecture_type == "load_balanced_tier":
            self.variable(
                "instance_count",
                "Number of web VMs in the tier. Each VM adds compute and disk cost; this does not configure automatic scaling or multi-zone placement.",
                2,
                type_name="number",
                minimum=2,
                maximum=20,
            )
        if self.config.architecture_type in {"virtual_machine", "windows_virtual_machine"}:
            declare_custom_image_inputs(self)
        if self.config.architecture_type in {
            "virtual_machine",
            "windows_virtual_machine",
            "single_web_server",
            "load_balanced_tier",
        }:
            self.variable(
                "os_image",
                (
                    (
                        "Windows Server 2022 English Full Base or Core Base from Amazon, using x86_64. Full Base includes Desktop Experience; Core omits the standard desktop and needs compatible applications and administration tools. Switching installation options requires replacement rather than an in-place conversion. "
                        if self.config.provider == "aws"
                        else "Windows Server 2022 desktop or Core Gen2 from MicrosoftWindowsServer, using x86_64. Core omits the standard desktop; verify application and administration-tool compatibility. Switching installation options replaces the VM. "
                        if self.config.provider == "azure"
                        else "Windows Server 2022 desktop or Core from windows-cloud, using x86_64. Core omits the standard desktop; verify application and administration-tool compatibility. Switching installation options replaces the VM. "
                    )
                    if self.config.architecture_type == "windows_virtual_machine"
                    else "Linux image from the supported publisher catalog, using x86_64/AMD64. "
                )
                + "The image version can be pinned separately; latest resolves at planning time. "
                + "Region, VM-size compatibility and account policy need preflight. ARM64 is unsupported. "
                + (
                    "This catalog choice is inactive when custom-image mode is enabled."
                    if self.config.architecture_type
                    in {"virtual_machine", "windows_virtual_machine"}
                    else "Custom images are unsupported for this recipe."
                ),
                "windows-server-2022"
                if self.config.architecture_type == "windows_virtual_machine"
                else LINUX_IMAGE_CHOICES[self.config.provider][0],
                choices=("windows-server-2022", "windows-server-2022-core")
                if self.config.architecture_type == "windows_virtual_machine"
                else LINUX_IMAGE_CHOICES[self.config.provider],
            )
        if self.config.architecture_type in {"virtual_machine", "windows_virtual_machine"}:
            if self.config.provider == "gcp":
                declare_gcp_network_attachment(self)
            elif self.config.provider == "azure":
                declare_azure_network_attachment(self)
            elif self.config.provider == "aws":
                declare_aws_network_attachment(self)
            declare_resource_labels(self)
            declare_initialization(self)
            declare_outbound_access(self)
            self.variable(
                "network_cidr",
                (
                    "VM subnet address range. "
                    if self.config.provider == "gcp"
                    else "Address range for the new VM network. Check for overlap with networks you will connect. "
                )
                + {
                    "aws": "The recipe creates two public and two private subnets with eight additional prefix bits, in two available zones.",
                    "azure": "The recipe derives one workload subnet with eight additional prefix bits.",
                    "gcp": "For a new network this range creates one regional subnet. In existing-network mode, enter the actual primary CIDR of the selected subnet; Terraform later checks it against subnet metadata. The existing range is not modified. GCP VPC networks have no enclosing address range.",
                }[self.config.provider],
                "10.0.1.0/24" if self.config.provider == "gcp" else "10.0.0.0/16",
                network_policy="vm_network",
                prefix_minimum=16,
                prefix_maximum=28 if self.config.provider == "gcp" else 20,
                visible_when={"use_existing_network": False}
                if self.config.provider in {"aws", "azure"}
                else None,
            )
            self._data_disk_inputs()
            if self.config.provider in {"aws", "gcp"}:
                self.variable(
                    "delete_boot_disk_with_vm",
                    "Delete the boot disk when this VM is deleted. Enabled preserves the existing provider default and can permanently remove boot data during deletion or replacement. Disabled requests retention of the old disk, with ongoing storage charges and separate recovery/cleanup. Retention is not a backup, does not reattach the disk to a replacement VM and does not retain separately managed data disks, keys or network resources. "
                    + (
                        "AWS encrypted boot disks use a project-managed KMS key; destroying that key can make a retained disk unreadable. Arrange key preservation separately before teardown. "
                        if self.config.provider == "aws"
                        else "A retained GCP boot disk can conflict with a replacement disk of the same name. Resolve recovery and naming separately before replacement. "
                    )
                    + "Review the Terraform plan and recovery requirements before changing this setting; actual lifecycle behavior remains unverified.",
                    True,
                    type_name="bool",
                )
            octet = r"(25[0-5]|2[0-4][0-9]|1[0-9]{2}|[1-9]?[0-9])"
            self.variable(
                "private_ip_address",
                "Optional fixed private IPv4 address for this VM. Leave blank for cloud allocation. The address must be usable in the selected workload subnet; provider-reserved addresses are rejected. In new-network mode AWS public VMs use the first public subnet and private VMs use the first private subnet; Azure uses its derived workload subnet. Existing AWS/Azure subnet mode uses the declared existing range, and GCP uses the entered subnet directly. The address is not reserved independently and availability is not checked. Changing it can interrupt access or replace resources; review the plan.",
                "",
                pattern=rf"^($|{octet}\.{octet}\.{octet}\.{octet})$",
            )
            self._workload_identity_inputs()
            if self.config.provider == "gcp":
                self.variable(
                    "admin_access_method",
                    "Direct administrator network uses your IPv4 network; Google IAP tunnel restricts the administrator firewall to Google's IAP proxy range. IAP can reach a VM without a public IP. Configure tunnel IAM, Linux OS Login or Windows guest credentials separately; TerraForma does not grant access or open a connection. Changing this choice can interrupt existing access. Review the generated rule and plan.",
                    "administrator_network",
                    choices=("administrator_network", "iap_tunnel"),
                )
            self.variable(
                "allowed_cidr",
                (
                    "Administrator network permitted to connect on RDP port 3389. "
                    if self.config.architecture_type == "windows_virtual_machine"
                    else "Administrator network permitted to connect on SSH port 22. "
                )
                + "Use a private IPv4 network or one public IPv4 address with /32. "
                + "Public /32 input is supported for generation, but local plan review blocks administrator access from outside private ranges, including a single public address. "
                + "Valid input does not approve deployment. Private VMs require an existing routed access path; this recipe does not create a VPN or bastion.",
                None if self.config.is_public else "10.0.0.0/16",
                visible_when={"admin_access_method": "administrator_network"}
                if self.config.provider == "gcp"
                else None,
                network_policy="administrator_cidr",
            )
            if self.config.provider == "aws":
                self.variable(
                    "ssh_public_key",
                    "Existing RSA public key for Windows password recovery. Keep the matching private key outside TerraForma; recover the Administrator password separately through EC2 after provisioning."
                    if self.config.architecture_type == "windows_virtual_machine"
                    else "Existing administrator Ed25519 or RSA public key to import into EC2. Keep the matching private key outside this project.",
                    pattern=r"^ssh-rsa [A-Za-z0-9+/]+={0,2}( .*)?$"
                    if self.config.architecture_type == "windows_virtual_machine"
                    else None,
                )
        getattr(self, f"_{self.config.provider}")()
        if self.config.architecture_type in {"virtual_machine", "windows_virtual_machine"}:
            for name in ("os_image", "image_version"):
                self.input_constraints[name]["visible_when"] = {"use_custom_image": False}
        return {
            "main.tf": "\n\n".join(item.render() for item in self.main) + "\n",
            "variables.tf": "\n\n".join(item.render() for item in self.variables) + "\n",
            "outputs.tf": "\n\n".join(item.render() for item in self.outputs) + "\n",
        }

    def _workload_identity_inputs(self) -> None:
        self.variable(
            "enable_workload_identity",
            {
                "aws": "Attach an existing IAM instance profile for workload API access. Review its role policies and trust relationship; provisioning requires permission to pass its role. This recipe creates no IAM role or policy grant.",
                "azure": "Use a system-assigned identity or attach one existing user-assigned managed identity for workload API access. Review effective permissions and attachment authorization separately. This recipe creates no role assignment or credential.",
                "gcp": "Attach an existing user-managed service account for workload API access, using the cloud-platform OAuth scope with access controlled by its IAM roles. Review those roles and attachment permissions separately. This recipe creates no service account, key or IAM grant; changing the account requires a stopped VM.",
            }[self.config.provider],
            False,
            type_name="bool",
        )
        if self.config.provider == "azure":
            declare_azure_identity_inputs(self)
        else:
            self.variable(
                "workload_identity",
                "Existing IAM instance profile name, not a role name or ARN. Its permissions, account and trust configuration remain unverified."
                if self.config.provider == "aws"
                else "Existing user-managed service account email (name@project.iam.gserviceaccount.com). Compute default service accounts and credential keys are unsupported. Identity and permissions remain unverified.",
                "",
                pattern=r"^[A-Za-z0-9_+=,.@\-]{1,128}$"
                if self.config.provider == "aws"
                else r"^[a-z][a-z0-9\-]{4,28}[a-z0-9]@[a-z][a-z0-9\-]{4,28}[a-z0-9]\.iam\.gserviceaccount\.com$",
                visible_when={"enable_workload_identity": True},
                required_when={"enable_workload_identity": True},
            )

    def _identity_precondition(self) -> Block:
        return block(
            "lifecycle",
            children=[
                block(
                    "precondition",
                    condition=ref('!var.enable_workload_identity || var.workload_identity != ""'),
                    error_message="Supply the existing workload identity reference when workload identity is enabled.",
                ),
                self._private_ip_precondition(),
                outbound_precondition(),
                initialization_precondition(
                    self.config.architecture_type == "windows_virtual_machine"
                ),
                *custom_image_preconditions(
                    self.config.provider, self.config.architecture_type == "windows_virtual_machine"
                ),
                *([gcp_attachment_precondition()] if self.config.provider == "gcp" else []),
                *([aws_attachment_precondition()] if self.config.provider == "aws" else []),
                *(
                    [self._gp3_precondition("boot_disk"), self._cpu_credit_precondition()]
                    if self.config.provider == "aws"
                    else []
                ),
            ],
        )

    def _cpu_credit_precondition(self) -> Block:
        return block(
            "precondition",
            condition=ref(
                f'var.cpu_credit_mode == "provider_default" || anytrue([for family in {value_hcl(list(AWS_CPU_CREDIT_PREFIXES))} : startswith(var.instance_type, family)])'
            ),
            error_message="Explicit CPU credit modes are supported only for x86 T2, T3, T3a and T8i instances; choose provider_default for other families.",
        )

    def _private_ip_precondition(self) -> Block:
        return block(
            "precondition",
            condition=ref(private_ip_condition(self.config.provider, self.config.is_public)),
            error_message="Choose a usable private IPv4 address in the selected VM subnet, excluding provider-reserved addresses, or leave it blank for cloud allocation.",
        )

    def _data_disk_inputs(self) -> None:
        disk_types = {
            "aws": ("gp3", "gp2"),
            "azure": ("StandardSSD_LRS", "Standard_LRS", "Premium_LRS"),
            "gcp": ("pd-balanced", "pd-standard", "pd-ssd"),
        }[self.config.provider]
        self.variable(
            "enable_data_disk",
            "Attach one new empty data disk. It adds storage charges and is managed by this Terraform project, so teardown can delete it. No filesystem formatting, mounting, backup, or recovery policy is configured.",
            False,
            type_name="bool",
        )
        self.variable(
            "data_disk_size_gb",
            "Data disk size in GiB. Size affects billing and provider disk tiers; shrinking an existing disk is not supported by this recipe.",
            100,
            type_name="number",
            minimum=32,
            maximum=2048,
            visible_when={"enable_data_disk": True},
        )
        self.variable(
            "data_disk_type",
            "Data disk storage class. Review VM, region, performance and billing compatibility before provisioning.",
            disk_types[0],
            choices=disk_types,
            visible_when={"enable_data_disk": True},
        )
        if self.config.provider == "azure":
            self.variable(
                "data_disk_caching",
                "Azure data disk host cache mode. None is the default. ReadOnly caches reads; ReadWrite can acknowledge writes before they reach the managed disk. Choose only after reviewing application durability, flush behavior and supported VM/disk capabilities. Stop affected applications and follow Azure's safe cache-change procedure before changing an attached disk. No guest flush, backup or recovery is performed by this recipe.",
                "None",
                choices=("None", "ReadOnly", "ReadWrite"),
                visible_when={"enable_data_disk": True},
            )
        if self.config.provider == "aws":
            self._gp3_inputs("data_disk", {"enable_data_disk": True, "data_disk_type": "gp3"})

    def _gp3_inputs(self, prefix: str, conditions: dict[str, bool | str]) -> None:
        self.variable(
            f"{prefix}_iops",
            "Provisioned gp3 disk input/output operations per second. 3,000 IOPS is included with storage; additional IOPS adds charges. This regional recipe supports 3,000–80,000 IOPS and at most 500 IOPS per GiB; 80,000 requires at least 160 GiB. Outposts is unsupported and has lower limits. Instance EBS limits, workload behavior and account availability can reduce achieved performance; no performance or cost guarantee is made.",
            3000,
            type_name="number",
            minimum=3000,
            maximum=80000,
            visible_when=conditions,
        )
        self.variable(
            f"{prefix}_throughput",
            "Provisioned gp3 disk throughput in MiB/s. 125 MiB/s is included with storage; additional throughput adds charges. This regional recipe supports 125–2,000 MiB/s and at most one quarter of provisioned IOPS; 2,000 requires at least 8,000 IOPS. Outposts is unsupported and has lower limits. Confirm instance EBS bandwidth and review pricing before increasing it.",
            125,
            type_name="number",
            minimum=125,
            maximum=2000,
            visible_when=conditions,
        )

    def _gp3_precondition(self, prefix: str) -> Block:
        return block(
            "precondition",
            condition=ref(
                ("!var.enable_data_disk || " if prefix == "data_disk" else "")
                + f'var.{prefix}_type != "gp3" || '
                + f"(var.{prefix}_iops <= var.{prefix}_size_gb * 500 && var.{prefix}_throughput * 4 <= var.{prefix}_iops)"
            ),
            error_message="For gp3, choose no more than 500 IOPS per GiB and throughput no greater than one quarter of provisioned IOPS.",
        )

    def _aws(self) -> None:
        build_aws(self)

    def _azure(self) -> None:
        build_azure(self)

    def _gcp(self) -> None:
        build_gcp(self)


GENERATED_FILENAMES = frozenset(
    {
        ".gitignore",
        "main.tf",
        "variables.tf",
        "outputs.tf",
        "terraforma.project.json",
        "terraforma.backend.json",
        "terraforma.receipt.json",
        "SHA256SUMS.txt",
    }
)


def project_destination(directory: str | Path) -> Path:
    destination = Path(directory).resolve()
    if any(
        any(destination.glob(pattern))
        for pattern in (
            "*.tf",
            "*.tf.json",
            "*.tfvars",
            "*.tfvars.json",
            "*.tfstate",
            "*.tfstate.*",
        )
    ) or any(
        (destination / name).exists() or (destination / name).is_symlink()
        for name in (".terraform", ".terraform.lock.hcl")
    ):
        raise ValueError(
            "The destination already contains Terraform configuration, state, variable files, or initialization data. Choose a fresh project directory."
        )
    if any(
        (destination / name).exists() or (destination / name).is_symlink()
        for name in GENERATED_FILENAMES
    ):
        raise FileExistsError(
            "The destination already contains generated artifacts. Choose a fresh project directory."
        )
    return destination


class ArtifactCleanupError(OSError):
    def __init__(self, filenames: list[str]):
        self.filenames = tuple(sorted(filenames))
        super().__init__(
            "Generation failed and cleanup was incomplete. Inspect these partial artifacts in "
            "the selected output directory before retrying: " + ", ".join(self.filenames) + "."
        )


def write_configuration(files: dict[str, str], directory: str | Path) -> Path:
    if not files or not set(files) <= GENERATED_FILENAMES:
        raise ValueError("Unexpected or empty generated filename set.")
    destination = project_destination(directory)
    destination.mkdir(mode=0o700, parents=True, exist_ok=True)
    created: list[Path] = []
    try:
        for name, content in files.items():
            path = destination / name
            with open(
                path,
                "x",
                encoding="utf-8",
                newline="\n",
                opener=lambda name, flags: os.open(name, flags, 0o600),
            ) as stream:
                created.append(path)
                stream.write(content)
                stream.flush()
                os.fsync(stream.fileno())
    except BaseException as failure:
        remaining = []
        for path in created:
            try:
                path.unlink(missing_ok=True)
            except OSError:
                remaining.append(path.name)
        if remaining:
            raise ArtifactCleanupError(remaining) from failure
        raise
    return destination
