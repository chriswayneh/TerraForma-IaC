import base64

import pytest
from pydantic import ValidationError

from terraforma.generator import WizardConfig
from terraforma.project import validate_input, validate_ssh_public_key


def public_key(algorithm: str, fields: list[bytes]) -> str:
    raw = b"".join(len(item).to_bytes(4, "big") + item for item in [algorithm.encode(), *fields])
    return algorithm + " " + base64.b64encode(raw).decode()


def rsa_integer(number: int) -> bytes:
    raw = number.to_bytes((number.bit_length() + 7) // 8, "big")
    return b"\x00" + raw if raw[0] & 128 else raw


def test_supported_public_key_structures_and_comments():
    validate_ssh_public_key(public_key("ssh-ed25519", [bytes(range(32))]) + " operator@example")
    validate_ssh_public_key(
        public_key("ssh-rsa", [rsa_integer(65537), rsa_integer((1 << 2047) + 1)])
    )


@pytest.mark.parametrize(
    "value",
    [
        "ssh-ed25519 AAAA",
        "ssh-ed25519 !!!",
        public_key("ssh-ed25519", [bytes(31)]),
        public_key("ssh-ed25519", [bytes(33)]),
        public_key("ssh-ed25519", [bytes(32), b"unexpected"]),
        public_key("ssh-ed25519", [bytes(32)]).replace("ssh-ed25519 ", "ssh-rsa "),
        public_key("ssh-rsa", [rsa_integer(65537), rsa_integer((1 << 1023) + 1)]),
        public_key("ssh-rsa", [rsa_integer(2), rsa_integer((1 << 2047) + 1)]),
        public_key("ssh-rsa", [rsa_integer(65537), b"\x80" + bytes(255)]),
        public_key("ssh-rsa", [b"\x00\x01\x00\x01", rsa_integer((1 << 2047) + 1)]),
        "ecdsa-sha2-nistp256 AAAA",
        "command=unsafe ssh-ed25519 AAAA",
    ],
)
def test_invalid_unsupported_or_weak_public_key_structure_is_rejected(value):
    with pytest.raises(ValueError) as error:
        validate_input("ssh_public_key", value, "ssh_public_key")
    assert value not in str(error.value)


@pytest.mark.parametrize("value", ["false", "true", 0, 1, None])
def test_recipe_booleans_do_not_coerce_values(value):
    with pytest.raises(ValidationError):
        WizardConfig(
            provider="aws", project_name="example", architecture_type="static_site", is_public=value
        )
