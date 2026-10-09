import hcl2
import pytest

from terraforma.generator import TerraformGenerator, WizardConfig
from terraforma.web import generate_project


def aws_main(architecture, encryption=True, public=False):
    files = TerraformGenerator(
        WizardConfig(
            provider="aws",
            project_name="enc-test",
            architecture_type=architecture,
            is_public=public,
            enable_encryption=encryption,
        )
    ).generate()
    return files["main.tf"], hcl2.loads(files["main.tf"])


def resources(parsed, kind):
    return {
        name.strip('"'): body
        for entry in parsed["resource"]
        if f'"{kind}"' in entry
        for name, body in entry[f'"{kind}"'].items()
    }


@pytest.mark.parametrize(
    "architecture",
    [
        "virtual_machine",
        "windows_virtual_machine",
        "single_web_server",
        "load_balanced_tier",
    ],
)
@pytest.mark.parametrize("encryption", [True, False])
def test_aws_compute_storage_is_always_encrypted(architecture, encryption):
    text, parsed = aws_main(architecture, encryption)
    assert "encrypted = false" not in text
    assert "encrypted               = false" not in text
    disk_blocks = [
        disk
        for kind in ("aws_instance", "aws_launch_template")
        for body in resources(parsed, kind).values()
        for disk in body.get("root_block_device", [])
        + [
            mapping["ebs"][0]
            for mapping in body.get("block_device_mappings", [])
            if mapping.get("ebs")
        ]
    ]
    assert disk_blocks
    for disk in disk_blocks:
        assert disk["encrypted"] is True
        assert ("kms_key_id" in disk) is encryption
    assert bool(resources(parsed, "aws_kms_key")) is encryption


@pytest.mark.parametrize("encryption", [True, False])
def test_aws_database_storage_is_always_encrypted_and_version_pinned(encryption):
    _, parsed = aws_main("secure_database", encryption)
    database = resources(parsed, "aws_db_instance")["this"]
    assert database["storage_encrypted"] is True
    assert database["engine"] == '"postgres"'
    assert database["engine_version"] == '"16"'
    assert ("kms_key_id" in database) is encryption


def test_aws_kms_key_has_explicit_account_policy_and_alias():
    text, parsed = aws_main("secure_database", True)
    key = resources(parsed, "aws_kms_key")["this"]
    assert key["enable_key_rotation"] is True
    assert (
        "arn:${data.aws_partition.current.partition}:iam::${var.aws_account_id}:root"
        in (key["policy"])
    )
    alias = resources(parsed, "aws_kms_alias")["this"]
    assert alias["name"] == '"alias/terraforma-${var.project_name}"'
    assert alias["target_key_id"] == "${aws_kms_key.this.key_id}"
    assert 'data "aws_partition" "current"' in text


@pytest.mark.parametrize(
    "architecture,public,private_subnets,nat",
    [
        ("single_web_server", True, False, False),
        ("single_web_server", False, True, True),
        ("virtual_machine", True, False, False),
        ("virtual_machine", False, True, True),
        ("load_balanced_tier", True, True, True),
        ("secure_database", True, False, False),
        ("secure_database", False, True, False),
    ],
)
def test_aws_private_subnets_and_nat_note_only_when_used(
    architecture, public, private_subnets, nat
):
    text, parsed = aws_main(architecture, public=public)
    assert ("private" in resources(parsed, "aws_subnet")) is private_subnets
    assert ("aws_nat_gateway" in text) is nat
    config = WizardConfig(
        provider="aws",
        project_name="enc-test",
        architecture_type=architecture,
        is_public=public,
    )
    notes = " ".join(generate_project(config)["notes"])
    if architecture != "secure_database":
        assert ("outbound NAT" in notes) is nat
