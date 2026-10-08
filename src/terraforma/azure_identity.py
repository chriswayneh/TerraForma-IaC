from terraforma.hcl import block, ref

AZURE_IDENTITY_PATTERN = r"/subscriptions/[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}/resourceGroups/[A-Za-z0-9](?:[A-Za-z0-9_.()-]{0,88}[A-Za-z0-9_])?/providers/Microsoft.ManagedIdentity/userAssignedIdentities/[A-Za-z0-9](?:[A-Za-z0-9_-]{0,126}[A-Za-z0-9_])?"


def declare_azure_identity_inputs(builder):
    builder.variable(
        "workload_identity_type",
        "System-assigned creates an identity tied to this VM. Existing user-assigned attaches one independently managed identity in the selected subscription. Review its effective access and assignment permissions before use; attaching it can expose its existing privileges to guest workloads. No role assignments or credentials are created. Changing or removing an identity can interrupt applications; existing user-assigned identities survive VM teardown.",
        "system_assigned",
        choices=("system_assigned", "existing_user_assigned"),
        visible_when={"enable_workload_identity": True},
    )
    builder.variable(
        "workload_identity_resource_id",
        "Full existing user-assigned managed identity resource ID in the selected subscription: /subscriptions/UUID/resourceGroups/GROUP/providers/Microsoft.ManagedIdentity/userAssignedIdentities/NAME. Client IDs, principal IDs, credentials, URLs and cross-subscription references are unsupported. Existence, tenant, effective permissions and attachment authorization remain unverified.",
        "",
        pattern=rf"^($|{AZURE_IDENTITY_PATTERN})$",
        visible_when={
            "enable_workload_identity": True,
            "workload_identity_type": "existing_user_assigned",
        },
        required_when={
            "enable_workload_identity": True,
            "workload_identity_type": "existing_user_assigned",
        },
    )


def azure_identity_precondition():
    return block(
        "precondition",
        condition=ref(
            'var.enable_workload_identity && var.workload_identity_type == "existing_user_assigned" ? '
            '(var.workload_identity_resource_id != "" && try(lower(split("/", var.workload_identity_resource_id)[2]), "") == lower(var.subscription_id)) : '
            '(var.workload_identity_resource_id == "" && (var.enable_workload_identity || var.workload_identity_type == "system_assigned"))'
        ),
        error_message="Existing user-assigned identity mode requires one resource ID in the selected subscription. Clear inactive identity choices when using system-assigned identity or disabling workload identity.",
    )
