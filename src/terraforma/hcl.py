import json
from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class Expression:
    value: str


def value_hcl(value: Any) -> str:
    if isinstance(value, Expression):
        return value.value
    if isinstance(value, dict):
        return (
            "{ "
            + ", ".join((f"{json.dumps(key)} = {value_hcl(item)}" for key, item in value.items()))
            + " }"
        )
    if isinstance(value, list):
        return "[" + ", ".join(value_hcl(item) for item in value) + "]"
    if isinstance(value, str):
        return json.dumps(value, ensure_ascii=False).replace("${", "$${").replace("%{", "%%{")
    return json.dumps(value)


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
        lines.extend(
            (f"{prefix}  {name} = {value_hcl(value)}" for name, value in self.attributes.items())
        )
        lines.extend(child.render(indent + 1) for child in self.children)
        lines.append(f"{prefix}}}")
        return "\n".join(lines)


def block(kind: str, *labels: str, children: list[Block] | None = None, **attributes: Any) -> Block:
    return Block(kind, labels, attributes, children or [])


def ref(value: str) -> Expression:
    return Expression(value)
