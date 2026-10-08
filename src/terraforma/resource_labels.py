from terraforma.hcl import ref, value_hcl

LABEL_FIELDS = {
    "owner_label": ("owner", "Owner or team"),
    "application_label": ("application", "Application or service"),
    "cost_center_label": ("cost_center", "Cost center"),
}


def declare_resource_labels(builder):
    scope = {
        "aws": "Applied through provider default tags to new resources that support them.",
        "azure": "Applied to the new resource group and generated resources that support tags; existing infrastructure is not retagged.",
        "gcp": "Applied to the new VM and optional managed data disk; network tags, existing infrastructure and the boot disk are not changed.",
    }[builder.config.provider]
    for name, (_, label) in LABEL_FIELDS.items():
        builder.variable(
            name,
            f"Optional {label.lower()} label. Leave blank to omit it. Use 1–63 lowercase letters, digits, underscores or hyphens, starting with a letter or digit. "
            + (
                f"{scope} Labels are stored in project exports, cloud metadata and state; keep secrets and personal information external. Labels do not grant access or enforce budgets."
                if name == "owner_label"
                else "Uses the same resource scope and handling as Owner or team."
            ),
            "",
            pattern="^($|[a-z0-9][a-z0-9_-]{0,62})$",
        )


def resource_labels(base):
    fields = ", ".join(f"{key} = var.{name}" for name, (key, _) in LABEL_FIELDS.items())
    return ref(
        f'merge({value_hcl(base)}, {{for key, value in {{{fields}}} : key => value if value != ""}})'
    )
