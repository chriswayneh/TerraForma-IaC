import json
import math
from typing import Any


def unique_object(pairs: list[tuple[str, Any]]) -> dict:
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("Duplicate JSON keys are unsupported.")
        result[key] = value
    return result


def reject_constant(value: str):
    raise ValueError("Non-finite JSON numbers are unsupported.")


def finite_float(value: str) -> float:
    number = float(value)
    if not math.isfinite(number):
        raise ValueError("Non-finite JSON numbers are unsupported.")
    return number


def bounded_json_depth(raw: str, maximum: int = 64) -> None:
    depth = 0
    quoted = False
    escaped = False
    for character in raw:
        if quoted:
            if escaped:
                escaped = False
            elif character == "\\":
                escaped = True
            elif character == '"':
                quoted = False
        elif character == '"':
            quoted = True
        elif character in "[{":
            depth += 1
            if depth > maximum:
                raise ValueError("JSON nesting exceeds the supported depth.")
        elif character in "]}":
            depth -= 1


def strict_json(raw: bytes | str, *, allow_bom: bool = True) -> Any:
    if isinstance(raw, bytes):
        raw = raw.decode("utf-8-sig" if allow_bom else "utf-8")
    bounded_json_depth(raw)
    return json.loads(
        raw,
        object_pairs_hook=unique_object,
        parse_constant=reject_constant,
        parse_float=finite_float,
    )
