import json
from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class Expression:
    value: str


def _literal_string(value: str) -> str:
    return json.dumps(value, ensure_ascii=False).replace("${", "$${").replace("%{", "%%{")


def value_hcl(value: Any) -> str:
    if isinstance(value, Expression):
        return value.value
    if isinstance(value, dict):
        return (
            "{ "
            + ", ".join(
                (f"{_literal_string(key)} = {value_hcl(item)}" for key, item in value.items())
            )
            + " }"
        )
    if isinstance(value, list):
        return "[" + ", ".join(value_hcl(item) for item in value) + "]"
    if isinstance(value, str):
        return _literal_string(value)
    return json.dumps(value)


def _aligned_attributes(prefix: str, attributes: dict[str, Any]) -> list[str]:
    """Render attributes with ``=`` aligned the way ``terraform fmt`` does.

    ``terraform fmt`` pads attribute names so the ``=`` signs line up across a run of
    consecutive attributes. A heredoc stays in the run, but any other multi-line value (such
    as an object or list spread over several lines) ends it: that attribute is rendered
    unpadded and the next attribute starts a new run. Generated values are normally single
    line; ``tests/test_hcl_format.py`` checks the output against ``terraform fmt``.
    """
    rendered = [(name, value_hcl(value)) for name, value in attributes.items()]
    lines: list[str] = []
    run: list[tuple[str, str]] = []

    def flush() -> None:
        width = max((len(name) for name, _ in run), default=0)
        lines.extend(f"{prefix}{name.ljust(width)} = {text}" for name, text in run)
        run.clear()

    for name, text in rendered:
        if "\n" in text and not text.startswith("<<"):
            flush()
            lines.append(f"{prefix}{name} = {text}")
        else:
            run.append((name, text))
    flush()
    return lines


@dataclass
class Block:
    kind: str
    labels: tuple[str, ...] = ()
    attributes: dict[str, Any] = field(default_factory=dict)
    children: list["Block"] = field(default_factory=list)

    def render(self, indent: int = 0) -> str:
        prefix = "  " * indent
        header = " ".join([self.kind, *(json.dumps(label) for label in self.labels)])
        lines = [f"{prefix}{header} {{"]
        lines.extend(_aligned_attributes(f"{prefix}  ", self.attributes))
        lines.extend(child.render(indent + 1) for child in self.children)
        lines.append(f"{prefix}}}")
        return "\n".join(lines)


def block(kind: str, *labels: str, children: list[Block] | None = None, **attributes: Any) -> Block:
    return Block(kind, labels, attributes, children or [])


def ref(value: str) -> Expression:
    return Expression(value)
