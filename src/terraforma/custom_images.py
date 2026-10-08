from terraforma.configuration import LINUX_IMAGE_CHOICES
from terraforma.hcl import block, ref

CUSTOM_IMAGE_PATTERNS = {
    "aws": r"ami-([0-9a-f]{8}|[0-9a-f]{17})",
    "azure": r"/subscriptions/[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}/resourceGroups/[A-Za-z0-9](?:[A-Za-z0-9_.()-]{0,88}[A-Za-z0-9_])?/providers/Microsoft.Compute/galleries/[A-Za-z0-9][A-Za-z0-9_.]{0,79}/images/[A-Za-z0-9][A-Za-z0-9_.-]{0,79}/versions/(?:0|[1-9][0-9]{0,9})\.(?:0|[1-9][0-9]{0,9})\.(?:0|[1-9][0-9]{0,9})",
    "gcp": r"projects/[a-z][a-z0-9-]{4,28}[a-z0-9]/global/images/[a-z](?:[a-z0-9-]{0,61}[a-z0-9])?",
}


def declare_custom_image_inputs(builder):
    builder.variable(
        "use_custom_image",
        "Use one existing organizational image instead of the publisher catalog. Only the selected VM operating-system family and x86_64 architecture are supported. Review the image's provenance, guest provisioning agents, licensing, disk minimum, boot/security features and administrator access before enabling. Changing images can replace a VM and destroy boot data. Generation does not inspect or authenticate the image.",
        False,
        type_name="bool",
    )
    builder.variable(
        "custom_image",
        {
            "aws": "Exact existing private EBS-backed HVM x86_64 AMI ID in the selected region. Enter its owner account separately. Public and Marketplace/product-code images are unsupported. Terraform later checks the ID, owner and declared platform; guest configuration and launch permissions still require verification.",
            "azure": "Exact existing Azure Compute Gallery image-version resource ID: /subscriptions/UUID/resourceGroups/GROUP/providers/Microsoft.Compute/galleries/GALLERY/images/IMAGE/versions/MAJOR.MINOR.PATCH. Use a generalized x86_64 Gen2 TrustedLaunchSupported image compatible with the selected Linux/Windows recipe and guest agents. Managed images, latest aliases, specialized images and Marketplace plans are unsupported. Location, access, image security type and guest compatibility remain unverified.",
            "gcp": "Exact existing image reference: projects/PROJECT/global/images/IMAGE. Use an approved x86_64 image matching the selected Linux/Windows recipe and guest provisioning agents. Families, snapshots and arbitrary URLs are unsupported. Image access, licenses, boot features and guest compatibility remain unverified.",
        }[builder.config.provider],
        "",
        pattern=rf"^($|{CUSTOM_IMAGE_PATTERNS[builder.config.provider]})$",
        visible_when={"use_custom_image": True},
        required_when={"use_custom_image": True},
    )
    if builder.config.provider == "aws":
        builder.variable(
            "custom_image_owner_account_id",
            "The 12-digit AWS account that owns the approved private AMI. This limits the later image lookup; it does not authenticate the image, grant launch access or verify guest behavior.",
            "",
            pattern=r"^($|[0-9]{12})$",
            visible_when={"use_custom_image": True},
            required_when={"use_custom_image": True},
        )
        if builder.config.architecture_type == "virtual_machine":
            builder.variable(
                "custom_image_admin_username",
                "Existing non-root SSH administrator username configured in your custom Linux image. This changes the connection guidance only; it does not create an account in the guest. Verify that the image imports the supplied launch public key for this account.",
                "",
                pattern=r"^($|[a-z_][a-z0-9_-]{0,31})$",
                forbidden_values=("root",),
                visible_when={"use_custom_image": True},
                required_when={"use_custom_image": True},
            )
    builder.variable(
        "confirm_custom_image_compatibility",
        "I have reviewed the custom image's provenance, Linux/Windows family, x86_64 architecture, guest agents, licensing, disk minimum, administrator access and selected boot/security features. This records a user declaration only; it does not verify compatibility or approve deployment.",
        False,
        type_name="bool",
        visible_when={"use_custom_image": True},
    )


def custom_image_preconditions(provider, windows=False):
    catalog_default = "windows-server-2022" if windows else LINUX_IMAGE_CHOICES[provider][0]
    conditions = [
        block(
            "precondition",
            condition=ref(
                'var.use_custom_image ? (var.custom_image != "" && var.confirm_custom_image_compatibility && var.image_version == "latest"'
                + f' && var.os_image == "{catalog_default}")'
                + ' : (var.custom_image == "" && !var.confirm_custom_image_compatibility)'
            ),
            error_message="Custom images require an exact reference, an explicit compatibility declaration and no catalog image pin. Disable custom-image mode before returning to catalog selection.",
        )
    ]
    if provider == "azure":
        conditions.append(
            block(
                "precondition",
                condition=ref(
                    '!var.use_custom_image ? true : try(alltrue([for part in split(".", element(reverse(split("/", var.custom_image)), 0)) : tonumber(part) <= 2147483647]), false)'
                ),
                error_message="Azure gallery image references require an exact Major.Minor.Patch version with each component no greater than 2147483647.",
            )
        )
    if provider == "aws":
        conditions.append(
            block(
                "precondition",
                condition=ref(
                    'var.use_custom_image ? var.custom_image_owner_account_id != "" : var.custom_image_owner_account_id == ""'
                ),
                error_message="Supply the existing AMI owner account only when custom-image mode is enabled.",
            )
        )
        if not windows:
            conditions.append(
                block(
                    "precondition",
                    condition=ref(
                        'var.use_custom_image ? var.custom_image_admin_username != "" : var.custom_image_admin_username == ""'
                    ),
                    error_message="Declare the existing non-root custom Linux image administrator username.",
                )
            )
    return conditions
