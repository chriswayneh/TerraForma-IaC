import json

import pytest

from terraforma.json_input import strict_json
from terraforma.plan_review import review_bytes


@pytest.mark.parametrize(
    "raw",
    [
        b'{"value":1e999}',
        b'{"value":-1e999}',
        b'{"value":NaN}',
        b'{"value":Infinity}',
        b'{"value":false,"value":true}',
        b'{"nested":{"value":1,"value":2}}',
        b"[" * 65 + b"0" + b"]" * 65,
        '{"value":"private-marker"}'.encode("utf-16"),
    ],
    ids=[
        "overflow",
        "negative-overflow",
        "nan",
        "infinity",
        "duplicate",
        "nested-duplicate",
        "depth",
        "utf16",
    ],
)
def test_strict_parser_rejects_ambiguous_numbers_objects_depth_and_encoding(raw):
    with pytest.raises((ValueError, UnicodeError)):
        strict_json(raw)


def test_utf8_bom_is_supported_for_local_files_but_not_api_requests():
    raw = b"\xef\xbb\xbf" + json.dumps({"label": "café", "count": 1.5}).encode()
    assert strict_json(raw) == {"label": "café", "count": 1.5}
    with pytest.raises(ValueError):
        strict_json(raw, allow_bom=False)


@pytest.mark.parametrize("value", ["1e999", "-1e999", "[" * 65 + "0" + "]" * 65])
def test_plan_parser_rejects_invalid_json_even_in_unused_metadata(value):
    raw = (
        '{"format_version":"1.2","planned_values":{},"configuration":{},"private-marker":'
        + value
        + "}"
    ).encode()
    with pytest.raises(ValueError, match="not valid JSON") as error:
        review_bytes(raw)
    assert "private-marker" not in str(error.value)
